"""Turn a reproduced Vesper defect into an isolated, reviewed Git commit."""
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tempfile
from uuid import uuid4

from .contracts import fingerprint, inventory, read_json, require, review_bundle, safe_path
from .git_bridge import change, file_entries, git, git_file_entries


REPRO = "vesper_repro.py"
ALLOWED_SOURCE = re.compile(r"(?:vesper\.py|build_local\.py|builder/[a-z_]+\.py|"
                            r"team/roles/[a-z-]+\.md|team/skills/[a-z-]+/SKILL\.md|tests/test_[a-z_0-9]+\.py)")


def repair_paths(paths):
    require(isinstance(paths, list) and 0 < len(paths) <= 8, "Specify one to eight repair files")
    for path in paths:
        safe_path(path)
        require(ALLOWED_SOURCE.fullmatch(path), f"Repair path is outside Vesper source scope: {path}")
    require(len(paths) == len(set(paths)) and any(not path.startswith("tests/") for path in paths),
            "Repair needs distinct paths including Vesper source")
    return paths


def incident_report(runner):
    labels = {"scope": "worker scope", "check": "failed acceptance evidence", "review": "review finding",
              "integrity": "snapshot or workspace integrity", "environment": "environment or runner I/O",
              "provider": "provider or launcher", "interrupted": "interrupted execution"}
    incidents = []
    for attempt in runner.status().get("attempts", []):
        if attempt["outcome"] == "accepted":
            continue
        kind = attempt.get("failure_kind", {"worker_failed": "provider",
                                            "interrupted": "interrupted"}.get(attempt["outcome"], "unclassified"))
        incidents.append({"id": attempt["id"], "job": attempt["job"], "kind": kind,
                          "origin": labels.get(kind, "needs investigation"),
                          "failed_checks": [check["id"] for check in attempt.get("checks", []) if check["exit_code"]]})
    return {"incidents": incidents}


def draft(root, idea, paths, reproducer, source=None):
    paths = repair_paths(paths)
    require(reproducer.is_file() and reproducer.stat().st_size <= 128_000,
            "Supply a small, trusted Python reproducer")
    script = reproducer.read_text(encoding="utf-8")
    (root / "checks" / REPRO).write_text(script, encoding="utf-8")
    plan = root / "plan"
    packet = {"paths": paths, "source_incident": source}
    (plan / "repair.json").write_text(json.dumps(packet, indent=2), encoding="utf-8")
    notes = {
        "product": "Repair this Vesper-owned defect.\n\n" + idea,
        "design": "Preserve user-facing behavior outside the reproduced failure. Keep the fix small.",
        "architecture": "Use the pinned Vesper checkout. Reuse existing runner and Git boundaries. "
                        "Investigate the root cause before editing. Keep the reproducer and baseline tests unchanged.",
        "decisions": "The approved file scope and verified reproducer define this repair. "
                     "Escalate changes to product direction, data access, permissions, or material complexity. "
                     "Deliver the verified bytes as a separate local Git branch.",
    }
    for name, note in notes.items():
        (plan / f"{name}.md").write_text(note + "\n", encoding="utf-8")
    contract = {
        "team": 1, "title": "Repair Vesper Relay", "delivery": "Verified local Git repair branch",
        "requirements": [{"id": "REPAIR", "description": idea,
                          "checks": ["VESPER_REPRO", "VESPER_REGRESSION"]}],
        "checks": [{"id": "VESPER_REPRO", "script": REPRO},
                   {"id": "VESPER_REGRESSION", "script": "vesper_regression.py"}],
        "jobs": [{"id": "REPAIR", "role": "backend", "goal": idea, "paths": paths,
                  "depends_on": [], "checks": ["VESPER_REPRO", "VESPER_REGRESSION"], "review": "security"}],
    }
    (plan / "contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")


def validate_repair(contract, packet):
    require(isinstance(packet, dict), "Invalid repair metadata")
    paths = repair_paths(packet.get("paths"))
    checks = {item["id"]: item["script"] for item in contract["checks"]}
    require(checks.get("VESPER_REPRO") == REPRO and checks.get("VESPER_REGRESSION") == "vesper_regression.py",
            "Repair requires the independent reproducer and baseline regression gates")
    jobs = contract["jobs"]
    require(contract.get("team") == 1 and len(jobs) == 1 and jobs[0]["paths"] == paths
            and jobs[0]["role"] == "backend" and jobs[0].get("review") == "security"
            and {"VESPER_REPRO", "VESPER_REGRESSION"} <= set(jobs[0]["checks"]),
            "Repair needs one scoped writing job with both gates and independent security review")


def validate_git_candidate(base, proposed):
    files = [name for name, (digest, _) in proposed.items() if digest is not None]
    required_dirs = {parent.as_posix() for name in files for parent in Path(name).parents
                     if parent != Path(".")}
    directories = {name for name, (digest, _) in proposed.items() if digest is None}
    require(directories == required_dirs and all(name not in base or base[name] == proposed[name]
                                                for name in directories),
            "Repair candidate contains directory changes that Git cannot represent")
    require(all(proposed[name][1] in (0o644, 0o755) for name in files),
            "Repair candidate contains file modes that Git cannot represent")
    require(not any(name in directories for name, (digest, _) in base.items() if digest is not None),
            "Repair cannot replace a source file with a directory")


def check_proof(proof, digest, bundle):
    require(isinstance(proof, dict) and proof.get("digest") == digest
            and proof.get("baseline_exit_code") == 1 and proof.get("baseline_digest") == fingerprint(bundle["seed"])
            and proof.get("reproducer_digest") == bundle["checks"][REPRO][0],
            "Reproduce the defect on the frozen source baseline before approval")
    return proof


def reproduction_record(runner, digest, bundle):
    proof = runner.control / "repair-reproduction.json"
    data = check_proof(read_json(proof) if proof.is_file() else None, digest, bundle)
    log = Path(data["log"])
    require(log.parent == runner.control and log.is_file() and not log.is_symlink()
            and sha256(log.read_bytes()).hexdigest() == data.get("log_digest"),
            "Reproduction evidence changed")
    return data


def reproduce(runner, launcher=None, trust_host=False):
    from .runner import atomic_json, execute_check, read_tail

    require(launcher or trust_host, "Choose a launcher or explicitly trust the local reproducer")
    require(not runner.state_file.exists(), "This repair already has an approved baseline")
    _, bundle = review_bundle(runner.root)
    require("repair" in bundle, "This run is not a Vesper repair")
    source = bundle["intake"]["repository"]
    require(git_file_entries(Path(source["path"]), source["commit"]) == file_entries(bundle["seed"]),
            "Repair seed differs from the pinned Git baseline")
    digest = fingerprint(bundle)
    receipt = runner.control / "repair-reproduction.json"
    receipt.unlink(missing_ok=True)
    log = runner.control / f"repair-baseline-{uuid4().hex}.log"
    code, intact = execute_check(REPRO, runner.root / "checks", bundle["checks"],
                                 runner.root / "seed", bundle["seed"], log, launcher)
    require(intact, "Reproducer modified its input")
    require(code == 1, f"Expected a failing baseline check with exit 1, got {code}. "
                       f"See {log.name}.\n{read_tail(log, 800)}")
    result = {"digest": digest, "baseline_exit_code": code, "baseline_digest": fingerprint(bundle["seed"]),
              "reproducer_digest": bundle["checks"][REPRO][0], "log": str(log),
              "log_digest": sha256(log.read_bytes()).hexdigest()}
    atomic_json(receipt, result)
    return result


def commit_repair(runner, source, approved_digest):
    state = runner.state()
    runner.frozen_contract(state)
    intake = state["bundle"].get("intake", {})
    meta = intake.get("repository")
    require("repair" in state["bundle"] and intake.get("mode") == "maintenance"
            and meta and Path(meta["path"]) == source, "Only a Vesper repair can create a repair branch")
    check_proof(state.get("repair_reproduction"), state["digest"], state["bundle"])
    require(git_file_entries(source, meta["commit"]) == file_entries(state["bundle"]["seed"]),
            "Repair seed differs from the pinned Git baseline")
    _, summary = change(runner, state, meta)
    require(summary["digest"] == approved_digest, "Reviewed repair patch digest changed")
    accepted = [item for item in state["attempts"] if item["outcome"] == "accepted"]
    require(len(accepted) == 1 and accepted[0].get("review", {}).get("verdict") == "approve"
            and accepted[0]["review"].get("provider") in ("codex", "claude"),
            "An independent reviewer must approve the exact repair")
    snapshot = runner.snapshot(state)
    contents = runner.check_snapshot(state)
    validate_git_candidate(state["bundle"]["seed"], contents)
    manifest = file_entries(contents)
    require(set(summary["files"]) <= set(state["bundle"]["repair"]["paths"]),
            "Repair would commit files outside its approved scope")
    zero = "0" * len(meta["commit"])
    branch = "vesper/repair/" + state["approval_id"]
    ref = "refs/heads/" + branch
    with tempfile.TemporaryDirectory(prefix="repair-index-", dir=runner.control) as temporary:
        index = Path(temporary) / "index"
        git(source, "read-tree", meta["commit"], index_file=index)
        entries = []
        for name in summary["files"]:
            if name in manifest:
                digest, executable = manifest[name]
                payload = (snapshot / name).read_bytes()
                require(sha256(payload).hexdigest() == digest, "Repair changed while writing Git blobs")
                blob = git(source, "hash-object", "-w", "--stdin", data=payload).decode().strip()
                mode = "100755" if executable else "100644"
            else:
                mode, blob = "0", zero
            entries.append(f"{mode} {blob}\t{name}\0".encode())
        git(source, "update-index", "-z", "--index-info", index_file=index, data=b"".join(entries))
        tree = git(source, "write-tree", index_file=index).decode().strip()
    require(git_file_entries(source, tree) == manifest, "Git repair tree differs from the reviewed snapshot")
    require(not git(source, "symbolic-ref", "--quiet", ref, valid=(0, 1, 128)).strip(),
            "Repair branch cannot be a symbolic ref")
    previous = git(source, "rev-parse", "--verify", "--quiet", ref, valid=(0, 1)).decode().strip()
    if previous:
        objects = git(source, "show", "-s", "--format=%T %P", previous).decode().split()
        require(objects == [tree, meta["commit"]], "Existing repair branch points to different bytes")
        commit = previous
    else:
        message = f"Repair Vesper Relay\n\nVerified patch SHA-256: {summary['digest']}\n"
        commit = git(source, "-c", "user.name=Vesper Relay", "-c",
                     "user.email=vesper-relay@users.noreply.github.com", "-c", "commit.gpgsign=false",
                     "commit-tree", tree, "-p", meta["commit"], data=message.encode()).decode().strip()
        git(source, "-c", "core.hooksPath=/dev/null", "update-ref", "--no-deref", ref, commit, zero)
    return {**summary, "branch": branch, "commit": commit}
