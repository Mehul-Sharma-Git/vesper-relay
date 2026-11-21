"""QA owns the checks and proves each one can fail (P3-T3).

A check that passes is evidence only if it would fail on broken code. QA keeps, for each check,
a small broken variant of the product under ``checks/_broken/<CHECK_ID>/``:

    note.md        optional: which promise the variant breaks (shown with the result)
    change.patch   a unified diff in Git's format (a/ and b/ paths), applied strictly, and/or
    files/         replacement files copied over the base first

`prove-checks` runs every check that has a variant twice, on a throwaway copy of the base (the
seed, or the known-good tree given with --against) and on the same copy with the variant applied:

    proven         passes on the base, fails on the broken copy
    passes_broken  passes on the broken copy: the check cannot catch what it guards (blocks)
    unusable       the variant could not be applied, or holds stray files (blocks)
    fails_on_base  fails on both: it proves little; give --against a known-good tree (reported)
    missing        no variant (reported per check)

The proof is bound to the plan packet's digest and to each log's digest. At focused and full
depth `approve` needs a proof for the exact packet with nothing blocking, and stores it in the
approval. `draft-checks` runs QA as a writer over a copy of plan/ and checks/ before approval;
what it changes reaches the run like any plan change, so the owner reviews it and the plan
critique and proof are redone.
"""
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from uuid import uuid4

from .contracts import BuilderError, fingerprint, inventory, read_json, require, reviewed_contract, safe_path

BROKEN = "_broken"
RECORD = "check-proof.json"
BLOCKING = ("passes_broken", "unusable")
PATCH_LIMIT = 256_000
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
DRAFT_LIMIT = 200_000


# --- broken variants -------------------------------------------------------------------------

def patch_path(label):
    """The tree path of a ``---``/``+++`` label: Git's a/ or b/ prefix, or None for /dev/null."""
    name = label.split("\t", 1)[0].strip()
    if name == "/dev/null":
        return None
    require(name[:2] in ("a/", "b/"), f"Patch paths need Git's a/ and b/ prefixes: {name!r}")
    return safe_path(name[2:])


def parse_patch(text):
    """[(old path or None, new path or None, [(old start, [lines])])] from a unified diff."""
    lines = text.splitlines(keepends=True)
    files, index = [], 0
    while index < len(lines):
        if not (lines[index].startswith("--- ") and index + 1 < len(lines) and lines[index + 1].startswith("+++ ")):
            index += 1
            continue
        old, new = patch_path(lines[index][4:]), patch_path(lines[index + 1][4:])
        require(old or new, "A patch file entry cannot be /dev/null on both sides")
        require(old is None or new is None or old == new, f"Patch renames are unsupported: {old} -> {new}")
        index += 2
        hunks = []
        while index < len(lines) and lines[index].startswith("@@"):
            found = HUNK.match(lines[index])
            require(found, f"Invalid hunk header: {lines[index].strip()}")
            start = int(found.group(1))
            old_count = int(found.group(2) if found.group(2) is not None else 1)
            new_count = int(found.group(4) if found.group(4) is not None else 1)
            index += 1
            body, seen_old, seen_new = [], 0, 0
            while index < len(lines) and (seen_old < old_count or seen_new < new_count
                                          or lines[index].startswith("\\")):
                line = lines[index]
                if line.startswith("\\"):
                    require(body, "A no-newline marker needs a line before it")
                    kind, content = body[-1]
                    body[-1] = (kind, content.removesuffix("\n"))
                else:
                    kind = line[:1]
                    require(kind in (" ", "-", "+"), f"Invalid patch line: {line.rstrip()!r}")
                    content = line[1:] if line.endswith("\n") else line[1:] + "\n"
                    body.append((kind, content))
                    seen_old += kind in " -"
                    seen_new += kind in " +"
                index += 1
            require(seen_old == old_count and seen_new == new_count, "A patch hunk is shorter than its header says")
            hunks.append((start, body))
        require(hunks, f"Patch entry for {new or old} has no hunks")
        files.append((old, new, hunks))
    require(files, "The patch holds no file changes")
    return files


def apply_patch(tree, text):
    """Apply a unified diff to ``tree`` exactly: every context and removed line must match where
    the hunk says (no fuzz). Nothing is written unless every file applies."""
    tree = Path(tree)
    results = {}
    for old, new, hunks in parse_patch(text):
        name = new or old
        path = tree / name
        if old is None:
            require(not path.exists(), f"The patch creates {name}, which already exists")
            source = []
        else:
            require(path.is_file() and not path.is_symlink(), f"The patch changes {name}, which is not a file")
            source = path.read_text(encoding="utf-8").splitlines(keepends=True)
        output, position = [], 0
        for start, body in hunks:
            at = max(start - 1, 0) if any(kind in " -" for kind, _ in body) else start
            expected = [content for kind, content in body if kind in " -"]
            require(at >= position and source[at:at + len(expected)] == expected,
                    f"The patch does not apply to {name} at line {start}")
            output += source[position:at]
            output += [content for kind, content in body if kind in " +"]
            position = at + len(expected)
        output += source[position:]
        require(new is not None or not output, f"The patch deletes {name} but leaves lines in it")
        results[name] = None if new is None else "".join(output)
    for name, content in results.items():
        path = tree / name
        if content is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


def variants(contract, checks_manifest):
    """{check ID: {"patch": path or None, "files": [paths], "note": path or None, "stray": [paths]}}
    for each variant in checks/_broken/; a folder that names no check is refused."""
    ids = {item["id"] for item in contract["checks"]}
    found = {}
    for path, (digest, _) in checks_manifest.items():
        parts = PurePosixPath(path).parts
        if parts[0] != BROKEN or len(parts) < 2:
            continue
        check = parts[1]
        require(check in ids, f"checks/{BROKEN}/{check} matches no check in the contract")
        entry = found.setdefault(check, {"patch": None, "files": [], "note": None, "stray": []})
        if digest is None or len(parts) == 2:
            if digest is not None:
                entry["stray"].append(path)
            continue
        rest = parts[2:]
        if rest == ("change.patch",):
            entry["patch"] = path
        elif rest == ("note.md",):
            entry["note"] = path
        elif rest[0] == "files" and len(rest) > 1:
            entry["files"].append(path)
        else:
            entry["stray"].append(path)
    return found


def apply_variant(variant, checks_dir, tree):
    """Break ``tree`` with one variant: replacement files first, then the patch. Returns a problem
    or None."""
    if variant["stray"]:
        return ("Only note.md, change.patch and files/ belong in a broken variant: "
                + ", ".join(variant["stray"]))
    if not variant["patch"] and not variant["files"]:
        return "The broken variant has neither change.patch nor files/"
    try:
        for path in variant["files"]:
            relative = PurePosixPath(path).relative_to(PurePosixPath(*PurePosixPath(path).parts[:3]))
            target = tree / relative.as_posix()
            if target.is_dir() and not target.is_symlink():
                return f"Replacement file {relative} clashes with a directory"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.unlink(missing_ok=True)
            shutil.copyfile(checks_dir / path, target)
        if variant["patch"]:
            patch = checks_dir / variant["patch"]
            require(patch.stat().st_size <= PATCH_LIMIT, "The patch exceeds the size limit")
            apply_patch(tree, patch.read_text(encoding="utf-8"))
    except (BuilderError, OSError, UnicodeError) as exc:
        return str(exc)
    return None


# --- proving -----------------------------------------------------------------------------------

def check_timeout(check):
    from .runner import REGRESSION_TIMEOUT
    return check.get("timeout", REGRESSION_TIMEOUT if check["id"] == "VESPER_REGRESSION" else 45)


def run_one(check, contract, checks_dir, checks_manifest, tree, logs, label, launcher, dependencies):
    """Run one check on ``tree`` (build setup first, for a command gate when the contract has
    some). Returns (exit code, log path); a setup failure returns (None, log path)."""
    from .runner import execute_check, execute_command_check, launch_command, read_tail
    log = logs / f"{check['id']}-{label}.log"
    build = contract.get("build", {})
    gate_env = contract.get("gate_env", ())
    manifest = inventory(tree, build.get("ignore", ()))
    if "script" in check:
        code, intact = execute_check(check["script"], checks_dir, checks_manifest, tree, manifest, log, launcher,
                                     timeout=check_timeout(check), gate_env=gate_env)
    else:
        with tempfile.TemporaryDirectory(dir=logs, prefix="setup-") as temp:
            prepared = None
            if build.get("setup"):
                prepared = Path(temp) / "work"
                from .runner import copy_tree
                copy_tree(tree, prepared, build.get("ignore", ()))
                for name in ("go-mod", "pnpm-store"):
                    (dependencies / name).mkdir(mode=0o700, parents=True, exist_ok=True)
                for number, command in enumerate(build["setup"], 1):
                    setup_log = logs / f"{check['id']}-{label}-setup-{number}.log"
                    with tempfile.TemporaryDirectory(dir=logs, prefix="setup-home-") as home:
                        status = launch_command("setup", command, prepared, home, setup_log, launcher,
                                                build.get("timeout", 600), gate_env, dependencies,
                                                {"GOFLAGS": "-modcacherw"})
                    if status != 0:
                        log.write_text(f"Build setup {command[0]} exited {status}\n{read_tail(setup_log)}\n",
                                       encoding="utf-8")
                        return None, log
            code, intact = execute_command_check(check["command"], check.get("overlay"), checks_dir,
                                                 checks_manifest, tree, manifest, log, launcher,
                                                 timeout=check_timeout(check), gate_env=gate_env, prepared=prepared,
                                                 ignore=build.get("ignore", ()), dependencies=dependencies)
    require(intact, f"Check {check['id']} modified its input while being proven")
    return code, log


def prove_tree(contract, checks_dir, checks_manifest, base, work, launcher=None, only=None, dependencies=None):
    """One result per check (in contract order, or only those named): each check's broken
    variant applied to a copy of ``base``, its control run on the unbroken copy first."""
    from .runner import copy_tree
    found = variants(contract, checks_manifest)
    ignore = contract.get("build", {}).get("ignore", ())
    logs = Path(work) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    dependencies = dependencies or Path(work) / "cache"
    results = []
    for check in contract["checks"]:
        if only is not None and check["id"] not in only:
            continue
        variant = found.get(check["id"])
        item = {"id": check["id"], "blocking": check.get("blocking", True)}
        if not variant:
            results.append({**item, "outcome": "missing", "reason": f"No checks/{BROKEN}/{check['id']}/ entry"})
            continue
        if variant["note"]:
            item["note"] = (checks_dir / variant["note"]).read_text(encoding="utf-8").strip()[:2000]
        trees = Path(tempfile.mkdtemp(dir=work, prefix=check["id"] + "-"))
        try:
            broken = trees / "broken"
            copy_tree(base, broken, ignore)
            problem = apply_variant(variant, checks_dir, broken)
            if problem:
                results.append({**item, "outcome": "unusable", "reason": problem})
                continue
            unbroken = trees / "base"
            copy_tree(base, unbroken, ignore)
            base_code, base_log = run_one(check, contract, checks_dir, checks_manifest, unbroken, logs, "base",
                                          launcher, dependencies)
            code, log = run_one(check, contract, checks_dir, checks_manifest, broken, logs, "broken",
                                launcher, dependencies)
        finally:
            shutil.rmtree(trees, ignore_errors=True)
        item.update(base_exit_code=base_code, broken_exit_code=code, logs={"base": base_log, "broken": log})
        if code is None:
            item.update(outcome="unusable", reason="Build setup failed on the broken copy: break the rule, not the build")
        elif code == 0:
            item.update(outcome="passes_broken",
                        reason=f"{check['id']} passed against its broken variant, so it cannot catch what it guards")
        elif base_code == 0:
            item["outcome"] = "proven"
        else:
            item.update(outcome="fails_on_base",
                        reason=f"{check['id']} fails on the unbroken base too, so this proves little; "
                               "prove it --against a known-good tree")
        results.append(item)
    return results


def packet_digest(bundle):
    """The plan packet's digest, as `review` reports it: the bundle without the plan critique."""
    return fingerprint({key: value for key, value in bundle.items() if key != "plan_critique"})


def boundary(launcher):
    from .sandbox import Sandbox
    if isinstance(launcher, Sandbox):
        return "sandbox " + (launcher.name or "backend")
    return "launcher" if launcher else "this machine"


def prove(runner, against=None, launcher=None):
    """`prove-checks`: prove every check of the current draft and keep the record for `approve`."""
    from .contracts import review_bundle
    from .runner import atomic_json, stamp
    require(not runner.state_file.exists(), "prove-checks runs before approval; this run is already approved")
    contract, bundle = review_bundle(runner.root)
    digest = packet_digest(bundle)
    ignore = contract.get("build", {}).get("ignore", ())
    base = Path(against).resolve() if against else runner.root / "seed"
    require(base.is_dir() and not base.is_symlink(), f"Not a directory: {base}")
    require(against is None or (base != runner.root and runner.root not in base.parents
                                and runner.control not in base.parents),
            "--against must be a tree outside the run folder (a known-good solution)")
    before = inventory(base, ignore)
    runner.control.mkdir(mode=0o700, exist_ok=True)
    (runner.control / RECORD).unlink(missing_ok=True)
    work = runner.control / "proofs" / uuid4().hex
    work.mkdir(parents=True)
    results = prove_tree(contract, runner.root / "checks", bundle["checks"], base, work, launcher,
                         dependencies=runner.control / "cache")
    require(inventory(base, ignore) == before, "The base tree changed while the checks were proven")
    require(packet_digest(review_bundle(runner.root)[1]) == digest, "The plan changed while the checks were proven")
    for item in results:
        if "logs" in item:
            item["logs"] = {key: str(path.relative_to(runner.root)) for key, path in item["logs"].items()}
            item["log_digests"] = {key: sha256((runner.root / path).read_bytes()).hexdigest()
                                   for key, path in item["logs"].items()}
    record = {"packet_digest": digest, "at": stamp(), "boundary": boundary(launcher),
              "against": {"path": str(base) if against else None, "digest": fingerprint(before)},
              "checks": results, "passed": not any(item["outcome"] in BLOCKING for item in results),
              "missing": [item["id"] for item in results if item["outcome"] == "missing"],
              "inconclusive": [item["id"] for item in results if item["outcome"] == "fails_on_base"]}
    atomic_json(runner.control / RECORD, record)
    return record


def current_proof(runner, bundle):
    """The proof record for this exact packet, its logs checked, or None."""
    path = runner.control / RECORD
    if not path.is_file():
        return None
    require(not path.is_symlink(), "Linked check proof is unsupported")
    record = read_json(path)
    if not isinstance(record, dict) or record.get("packet_digest") != packet_digest(bundle):
        return None
    for item in record.get("checks", []):
        for key, name in item.get("logs", {}).items():
            log = runner.root / name
            require(runner.control in log.parents and log.is_file() and not log.is_symlink()
                    and sha256(log.read_bytes()).hexdigest() == item.get("log_digests", {}).get(key),
                    f"Check proof evidence changed: {name}")
    return record


def approval_proof(runner, bundle):
    """The proof `approve` stores. Focused and full depth need one for this packet in which no
    check passes against its broken variant and every variant applies."""
    record = current_proof(runner, bundle)
    if bundle.get("planning", {}).get("depth") not in ("full", "focused"):
        return record
    require(record, "Run prove-checks on this exact plan before approval (focused and full depth): each check "
                    "must fail against its broken variant in checks/_broken/")
    refused = [item for item in record["checks"] if item["outcome"] in BLOCKING]
    require(not refused, "prove-checks did not pass: " + "; ".join(
        f"{item['id']} passes against its broken variant" if item["outcome"] == "passes_broken"
        else f"{item['id']}'s broken variant is unusable ({item['reason']})" for item in refused))
    return record


def sheet_lines(runner, bundle):
    """The plan sheet's lines about the proof (P3-T3)."""
    try:
        record = current_proof(runner, bundle)
    except BuilderError as exc:
        return [f"Checks proven to fail: the proof cannot be used ({exc})"]
    depth = bundle.get("planning", {}).get("depth")
    if not record:
        needed = " (required before approval)" if depth in ("full", "focused") else ""
        return [f"Checks proven to fail: not run yet{needed}"]
    results = record["checks"]
    proven = sum(item["outcome"] == "proven" for item in results)
    against = record["against"]["path"] or "the seed"
    lines = [f"Checks proven to fail: {proven} of {len(results)} (against {against}, on {record['boundary']})"]
    words = {"passes_broken": "passes against its broken variant", "unusable": "broken variant unusable",
             "fails_on_base": "fails on the unbroken base too, so proves little", "missing": "no broken variant"}
    lines += [f"  {item['id']}: {words[item['outcome']]}" for item in results if item["outcome"] != "proven"]
    return lines


# --- draft-checks -------------------------------------------------------------------------------

DRAFT_TASK = """You are QA, drafting this plan's acceptance checks before the owner approves it.

Your working folder holds plan/, checks/ and seed/. Edit only plan/ and checks/; seed/ is read-only
data (the baseline). Vesper copies what you change in plan/ and checks/ into the run as a plan
change: the owner reviews it, and the plan critique and prove-checks run again.

1. Write every acceptance check: a Python gate script in checks/ or a command gate, listed in
   plan/contract.json, named by the requirements it proves and assigned to the jobs that must pass it.
2. Write checks/test-strategy.md: a table of each risk, the test level that covers it (unit is the
   builders'; contract, integration and end-to-end are yours), and the check ID.
3. For each check write checks/_broken/<CHECK_ID>/: change.patch (a unified diff in Git's format
   with a/ and b/ paths, against seed/ or the known-good solution the owner names) or files/
   (replacement files), plus note.md naming the promise it breaks. It must break the rule, not the
   build, and the check must fail against it.
4. Hand off with a short summary whose claims carry [verified], [inferred] or [assumed] labels.
"""


def draft_checks(runner, brain, launcher, trust_host, timeout=600):
    """`draft-checks`: QA writes the checks over a copy of plan/ and checks/ (seed/ read-only), and
    what it changed replaces the run's plan/ and checks/ once the contract still validates."""
    from .brains import launch
    from .runner import copy_tree, drop_python_caches, read_tail
    from .team import profile, render
    require(not runner.state_file.exists(), "draft-checks runs before approval; this run is already approved")
    require(type(timeout) is int and 1 <= timeout <= 1800, "--timeout must be 1 to 1800 seconds")
    areas = ("plan", "checks", "seed")
    for name in areas:
        require((runner.root / name).is_dir(), f"Initialize a project first: {name}/ is missing")
    runner.control.mkdir(mode=0o700, exist_ok=True)
    originals = {name: inventory(runner.root / name) for name in areas}
    with tempfile.TemporaryDirectory(prefix="draft-checks-", dir=runner.control) as temporary:
        directory = Path(temporary)
        workspace = directory / "workspace"
        workspace.mkdir()
        for name in areas:
            copy_tree(runner.root / name, workspace / name)
        prompt = render(profile("qa")) + "\n\n" + DRAFT_TASK
        log = directory / "qa.log"
        # QA writes here, so it runs as a worker with the default writer tools (shell only in a
        # sandbox); its catalogue entry stays read-only for consultations.
        code = launch(brain, "worker", launcher, trust_host, work=workspace, input_text=prompt, log=log,
                      timeout=timeout, ledger={"run": runner.root, "job": None, "role": "qa"})
        said = brain.adapter.summary(read_tail(log, limit=DRAFT_LIMIT))
        require(code == 0, f"QA brain {brain.name} exited {code}\n{said[-3500:]}")
        drop_python_caches(workspace)
        require(sorted(path.name for path in workspace.iterdir()) == sorted(areas),
                "QA may change only plan/ and checks/: it added top-level entries")
        require(inventory(workspace / "seed") == originals["seed"],
                "QA changed seed/, which is read-only; nothing was copied into the run")
        drafted = {name: inventory(workspace / name) for name in ("plan", "checks")}
        reviewed_contract(workspace / "plan", drafted["plan"], drafted["checks"])
        changed = sorted(f"{area}/{path}" for area in drafted
                         for path in originals[area].keys() | drafted[area].keys()
                         if originals[area].get(path) != drafted[area].get(path)
                         and (drafted[area].get(path) or originals[area].get(path))[0] is not None)
        for area in drafted:
            require(inventory(runner.root / area) == originals[area],
                    f"{area}/ changed in the run while QA drafted; nothing was copied")
        if changed:
            for area in drafted:
                if originals[area] == drafted[area]:
                    continue
                staged = directory / ("staged-" + area)
                copy_tree(workspace / area, staged)
                require(inventory(staged) == drafted[area], "The draft changed while it was copied")
                old = directory / ("old-" + area)
                os.replace(runner.root / area, old)
                os.replace(staged, runner.root / area)
    return {"role": "qa", "brain": brain.name, "changed": changed, "report": said[-DRAFT_LIMIT:],
            "next": "Run review to see what changed on the plan sheet, then review-plan and prove-checks"
            if changed else "QA changed nothing"}


__all__ = ["apply_patch", "approval_proof", "draft_checks", "prove", "prove_tree", "sheet_lines", "variants"]
