"""Additive checks after approval (P2-T6).

QA can add a check mid-build without weakening anything and without a full re-approval. Each
`add-check` writes an amendment under `.builder/amendments/NNN-<check id>/`:

    amendment.json   the check, the unfinished jobs it is assigned to, the reason, and the
                     inventory of the checks package below; its digest chains to the previous
                     amendment's digest, and the first one's to the approval digest
    checks/          the approved checks package plus every added script (each amendment's
                     package holds the previous one unchanged, plus at most one new script)

The run's state keeps each amendment's digest, so a changed, removed or reordered amendment is
refused like a changed approval. Only additions are possible: a new check id, a new script name,
and jobs that are not accepted yet and whose candidate is not awaiting review. Approved checks
keep running on their jobs; nothing is removed, edited or reassigned. Adding a check is a
protected action (P2-T2): a human confirms it on the add-check sheet.
"""
import json
from pathlib import Path
import shlex
import shutil
from uuid import uuid4

from .contracts import (BuilderError, fingerprint, id_list, inventory, read_json, require, safe_path,
                        validate_check, validate_command)

FOLDER = "amendments"
RECORD = "amendment.json"
SCRIPT_LIMIT = 256_000


def subject(root):
    """The confirmation subject: one run's amendments (P2-T2 "what changed" baseline)."""
    return f"{root}#amendments"


def verified(runner, state):
    """[(record, folder)] for the run's amendments, oldest first, each checked against the
    digest the state keeps and chained to the one before (the first to the approval)."""
    entries = state.get("amendments", [])
    previous_digest, manifest = state["digest"], state["bundle"]["checks"]
    found = []
    for number, entry in enumerate(entries, 1):
        folder = runner.control / FOLDER / entry["folder"]

        def changed(what, number=number):
            return BuilderError(f"Amendment {number} has changed since it was confirmed ({what})")

        try:
            record = read_json(folder / RECORD)
            package = inventory(folder / "checks")
        except BuilderError as exc:
            raise changed(str(exc)) from exc
        if fingerprint(record) != entry["digest"]:
            raise changed("its record")
        if record.get("sequence") != number or record.get("previous") != previous_digest:
            raise changed("its place in the chain")
        if package != record.get("checks"):
            raise changed("its checks package")
        added = set(package) - set(manifest)
        script = record["check"].get("script")
        if any(package.get(path) != value for path, value in manifest.items()) or added != (
                {script} if script else set()):
            raise changed("it edits or removes an approved check")
        found.append((record, folder))
        previous_digest, manifest = entry["digest"], package
    return found


def apply(runner, state, contract):
    """The approved contract with every confirmed amendment's check added to its jobs."""
    jobs = {job["id"]: job for job in contract["jobs"]}
    for record, _ in verified(runner, state):
        check = dict(record["check"])
        require(check["id"] not in {item["id"] for item in contract["checks"]}
                and set(record["jobs"]) <= jobs.keys(), "An amendment does not fit the approved contract")
        contract["checks"].append(check)
        for job in record["jobs"]:
            jobs[job]["checks"].append(check["id"])
    return contract


def package(runner, state):
    """(folder, inventory) of the checks package gates run from: the newest amendment's, or the
    approved one. frozen_contract verifies the whole chain; every user of the package also
    compares its copy with this inventory."""
    entries = state.get("amendments", [])
    if not entries:
        return runner.approval(state) / "checks", state["bundle"]["checks"]
    folder = runner.control / FOLDER / entries[-1]["folder"]
    record = read_json(folder / RECORD)
    require(fingerprint(record) == entries[-1]["digest"],
            f"Amendment {len(entries)} has changed since it was confirmed (its record)")
    return folder / "checks", record["checks"]


def listed(runner, state):
    """What `status` (and so the final summary) shows the owner about each amendment."""
    rows = []
    for entry, (record, _) in zip(state.get("amendments", []), verified(runner, state)):
        rows.append({"sequence": record["sequence"], "check": record["check"], "jobs": record["jobs"],
                     "reason": record["reason"], "digest": entry["digest"], "previous": record["previous"],
                     "at": record["at"], "confirmer": entry["confirmation"]["confirmer"]})
    return rows


def new_check(check_id, script, command, contract, manifest):
    """The check record for --script PATH or --command "ARGV", refused if it edits anything."""
    require(isinstance(check_id, str) and check_id, "add-check needs --id")
    id_list([check_id], "check ID: use a letter, then letters, digits, _ or -")
    require(check_id not in {item["id"] for item in contract["checks"]},
            f"Check {check_id} already exists: an approved check cannot be edited or reassigned")
    require((script is None) != (command is None), "add-check needs exactly one of --script or --command")
    if command is not None:
        try:
            argv = shlex.split(command) if isinstance(command, str) else list(command)
        except ValueError as exc:
            raise BuilderError(f"Invalid --command: {exc}") from exc
        return {"id": check_id, "command": argv}, None
    source = Path(script)
    require(source.is_file() and not source.is_symlink(), f"Check script not found: {script}")
    require(source.stat().st_size <= SCRIPT_LIMIT, f"Check script is larger than {SCRIPT_LIMIT} bytes: {script}")
    name = safe_path(source.name)
    require(name.endswith(".py"), f"A check script is a Python file: {name}")
    require(name not in manifest, f"{name} is already in the approved checks: "
                                  "an approved check file cannot be edited; give the new script another name")
    return {"id": check_id, "script": name}, source


def assigned_jobs(jobs, state, contract):
    """The unfinished jobs the check is assigned to."""
    names = [item.strip() for item in (jobs or []) if item.strip()]
    require(names, "add-check needs --jobs J_X[,J_Y]: the unfinished jobs that must pass the check")
    id_list(names, "--jobs: give distinct job IDs")
    known = {job["id"] for job in contract["jobs"]}
    active = state.get("active") or {}
    for name in names:
        require(name in known, f"Unknown job {name}")
        require(name not in state["completed"],
                f"{name} is already accepted: a check can be added only to unfinished jobs")
        require(not (active.get("job") == name and "review" in active),
                f"{name}'s candidate awaits independent review: finish that review first")
    return names


def add(runner, check_id, *, script=None, command=None, jobs=None, reason=None):
    """Record a confirmed amendment; return its summary. Run under the runner's lock."""
    from .approvals import changed_since, confirm, entry, keep, run_store
    from .runner import atomic_json, copy_file, copy_tree, stamp, sync_dir, sync_tree
    from .sheets import add_check_sheet
    state = runner.state()
    contract = runner.frozen_contract(state)
    require(isinstance(reason, str) and reason.strip(), "add-check needs --reason: say why the check is added")
    names = assigned_jobs(jobs, state, contract)
    source_package, manifest = package(runner, state)
    check, source = new_check(check_id, script, command, contract, manifest)
    if "command" in check:
        validate_command(check["command"], f"check {check_id}")
    entries = state.get("amendments", [])
    sequence = len(entries) + 1
    previous = entries[-1]["digest"] if entries else state["digest"]
    root = runner.control / FOLDER
    root.mkdir(mode=0o700, exist_ok=True)
    staging = root / (".staging-" + uuid4().hex)
    try:
        staging.mkdir()
        copy_tree(source_package, staging / "checks")
        require(inventory(staging / "checks") == manifest, "Approved checks changed while copying")
        if source is not None:
            copy_file(source, staging / "checks" / check["script"])
        checks = inventory(staging / "checks")
        validate_check(check, checks)
        require({path: value for path, value in checks.items() if path in manifest} == manifest
                and set(checks) - set(manifest) == ({check["script"]} if source else set()),
                "The new check package would edit an approved check")
        record = {"format": 1, "sequence": sequence, "previous": previous, "approval": state["digest"],
                  "check": check, "jobs": names, "reason": reason.strip(), "checks": checks, "at": stamp()}
        (staging / RECORD).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        digest = fingerprint(record)
        folder = f"{sequence:03d}-{check_id}"
        files = [entry(staging / "checks" / path, f"checks/{path}")
                 for path, (value, _) in sorted(checks.items()) if value is not None]
        files += [entry(root / item["folder"] / RECORD, f"{FOLDER}/{item['folder']}/{RECORD}") for item in entries]
        files.append(entry(staging / RECORD, f"{FOLDER}/{folder}/{RECORD}"))
        store = run_store(runner.root)
        changed, _ = changed_since(store, "add-check", subject(runner.root), files)
        sheet = add_check_sheet(contract, record, digest, folder, changed, len(entries), files, source)
        confirmation = confirm("add-check", subject(runner.root), digest, sheet)
        require(fingerprint(read_json(staging / RECORD)) == digest and inventory(staging / "checks") == checks,
                "The amendment changed while it was being confirmed")
        sync_tree(staging)
        target = root / folder
        if target.exists():  # left by an add-check that stopped before saving the state
            shutil.rmtree(target)
        staging.rename(target)
        sync_dir(root)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    state.setdefault("amendments", []).append(
        {"folder": folder, "digest": digest,
         "confirmation": {key: confirmation[key] for key in ("digest", "confirmer", "at")}})
    atomic_json(runner.state_file, state)
    keep(store, confirmation)
    return {"sequence": sequence, "digest": digest, "previous": previous, "check": check, "jobs": names,
            "reason": record["reason"]}
