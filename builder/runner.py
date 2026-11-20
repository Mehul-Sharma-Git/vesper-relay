"""Single-writer state machine with frozen checks and verified snapshots."""
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from uuid import uuid4

from .contracts import (BuilderError, fingerprint, inventory, owned, read_json,
                        require, review_bundle, reviewed_contract, safe_path)
from .process import run_process
from .brains import command as brain_command, launch, parse_result, tools as brain_tools, usage
from .providers import GATES_DIR, review_limits, worker_prompt
from .review_gate import needs_security, prompt as review_prompt, report_schema, validate_report, write_diff
from .sandbox import Sandbox, check_job, command_job

# VESPER_REGRESSION runs Vesper's whole baseline suite; 300 s stopped fitting on a Mac at P1-G.
REGRESSION_TIMEOUT = 900
# The reviewer's copy of each gate's log and of what gates saved (P2-T1).
REVIEW_LOG_LIMIT = 256_000
REVIEW_ARTIFACTS_LIMIT = 20_000_000
# A retry's review lists the blockers earlier reviews of its job raised (newest kept).
EARLIER_BLOCKERS_LIMIT = 20
EARLIER_EVIDENCE_LIMIT = 600
# A retry's brief carries every earlier failure of its job, each cut to an equal share of this.
HISTORY_LIMIT = 12_000
FAILURE_LABELS = {"check": "failed a gate", "review": "rejected by the independent reviewer",
                  "provider": "the worker failed or timed out", "scope": "changed files outside the job's paths",
                  "integrity": "failed an integrity check", "environment": "hit a runner error"}


def scope_changes(base, proposed, paths):
    """Paths that differ from the base, and those of them outside the job's paths (a new
    directory is allowed when it holds an owned path)."""
    changed = sorted(path for path in base.keys() | proposed.keys() if base.get(path) != proposed.get(path))
    denied = [
        path for path in changed
        if not owned(path, paths)
        and not (path not in base and proposed[path][0] is None
                 and any(item.startswith(path + "/") and item in proposed
                         and owned(item, paths) for item in changed))
    ]
    return changed, denied


def drop_python_caches(root, ignore=()):
    """Remove the __pycache__ folders a worker's own runs leave in its workspace. They are
    never product files (safe_path refuses the name), and one stray cache would otherwise
    reject the whole attempt unchecked (finding 49). A linked one is unlinked, never followed;
    ignored top-level folders are left alone."""
    for directory, folders, _ in os.walk(root):
        if Path(directory) == root:
            folders[:] = [name for name in folders if name not in ignore]
        if "__pycache__" in folders:
            folders.remove("__pycache__")
            cache = Path(directory) / "__pycache__"
            if cache.is_symlink():
                cache.unlink()
            else:
                shutil.rmtree(cache)


def copy_log_tail(source, destination, limit=REVIEW_LOG_LIMIT):
    """A gate log for the reviewer: whole, or its last part from a line start, under a first
    line that says how much was left out (failures are reported at the end)."""
    size = source.stat().st_size
    with source.open("rb") as file:
        if size <= limit:
            data = file.read()
        else:
            keep = limit - 120
            file.seek(size - keep)
            data = file.read()
            start = data.find(b"\n")
            data = data[start + 1:] if 0 <= start < 4096 else data
            data = (f"[earlier output omitted: showing the last {len(data)} of {size} bytes]\n").encode() + data
    destination.write_bytes(data)


def copy_artifacts(source, destination, limit=REVIEW_ARTIFACTS_LIMIT):
    """Copy the regular files gates saved, under safe names, until the size limit. Links are
    never followed. Returns the paths left out."""
    omitted, used = [], 0
    for folder, folders, files in os.walk(source):
        folders.sort()
        for name in sorted(files):
            path = Path(folder) / name
            relative = path.relative_to(source).as_posix()
            info = path.lstat()
            try:
                safe_path(relative)
            except BuilderError:
                omitted.append(relative)
                continue
            if not stat.S_ISREG(info.st_mode) or used + info.st_size > limit:
                omitted.append(relative)
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_file(path, target)
            used += info.st_size
    return omitted


def attempt_history(previous, limit=HISTORY_LIMIT):
    """Every earlier failure of a job, oldest first; a long reason keeps its start and end."""
    if not previous:
        return None
    share = limit // len(previous)
    parts = []
    for number, item in enumerate(previous, 1):
        reason = (item.get("reason") or "").strip() or item["outcome"]
        if len(reason) > share:
            reason = reason[:share // 2] + "\n[...]\n" + reason[-(share // 2):]
        label = FAILURE_LABELS.get(item.get("failure_kind"), item["outcome"])
        parts.append(f"Attempt {number} ({label}):\n{reason}")
    return "\n\n".join(parts)


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(value, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
            os.replace(temporary, path)
            sync_dir(path.parent)
        finally:
            temporary.unlink(missing_ok=True)


def sync_tree(path):
    for directory, _, files in os.walk(path, topdown=False):
        for file in files:
            entry = Path(directory) / file
            # Only regular files: opening a link follows it, and opening a pipe blocks (P2-T1).
            if not stat.S_ISREG(entry.lstat().st_mode):
                continue
            with entry.open("rb") as stream:
                os.fsync(stream.fileno())
        sync_dir(Path(directory))
    sync_dir(path.parent)


def read_tail(path, limit=3500):
    with path.open("rb") as file:
        file.seek(max(0, path.stat().st_size - limit))
        return file.read().decode("utf-8", errors="replace").strip()


def copy_file(source, destination):
    shutil.copyfile(source, destination, follow_symlinks=False)
    if not Path(destination).is_symlink():
        shutil.copymode(source, destination, follow_symlinks=False)
    return destination


def copy_tree(source, destination, ignore=()):
    # copytree's directory copystat preserves extended attributes. Build the
    # tree from its recorded representation instead. Ignored top-level build
    # directories are left behind.
    destination.mkdir()
    entries = inventory(source, ignore)
    for name, (digest, _) in entries.items():
        if digest is None:
            (destination / name).mkdir()
        else:
            copy_file(source / name, destination / name)
    for name, (digest, mode) in reversed(list(entries.items())):
        if digest is None:
            (destination / name).chmod(mode)
    destination.chmod(stat.S_IMODE(source.stat().st_mode))


def gate_environment(temp, gate_env, path=os.defpath, dependencies=None):
    """The same fixed environment for every gate: home and tool caches live in the gate's temp dir.

    gate_env names approved host variables whose current values the gate also receives.
    dependencies is the run's shared dependency cache, given when the contract has build setup."""
    cache = Path(temp) / ".cache"
    env = {**{name: os.environ[name] for name in gate_env if name in os.environ},
           "PATH": path, "HOME": str(temp), "TMPDIR": str(temp),
           "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
           "XDG_CACHE_HOME": str(cache), "GOCACHE": str(cache / "go-build"), "GOPATH": str(Path(temp) / "go")}
    if dependencies is not None:
        # pnpm 10+ reads only pnpm_config_store_dir; older releases read npm_config_store_dir.
        store = str(dependencies / "pnpm-store")
        env.update(GOMODCACHE=str(dependencies / "go-mod"), PNPM_STORE_DIR=store,
                   pnpm_config_store_dir=store, npm_config_store_dir=store)
    return env


def launch_command(operation, command, work, temp, log, launcher, timeout, gate_env, dependencies=None,
                   extra_env=None, artifacts=None):
    """Run a bare-program argv in work: in the sandbox backend, through the launcher as
    `<operation> <work> -- argv`, or on the host with the program resolved on the runner's own PATH."""
    if isinstance(launcher, Sandbox):
        job = command_job(operation, command, work, dependencies=dependencies, gate_env=gate_env, extra=extra_env,
                          artifacts=artifacts)
        return launcher.run(job, input_text="", log=log, timeout=timeout)
    if launcher:
        argv, path = [launcher, operation, str(work), "--", *command], os.defpath
    else:
        program = shutil.which(command[0], path=os.environ.get("PATH", os.defpath))
        if not program:
            label = "Build setup" if operation == "setup" else "Command gate"
            log.write_text(f"{label} program not found on PATH: {command[0]}\n", encoding="utf-8")
            return 127
        argv = [program, *command[1:]]
        path = os.pathsep.join((os.path.dirname(program), os.defpath))
    env = gate_environment(temp, gate_env, path, dependencies)
    env.update(extra_env or {})
    if artifacts is not None:
        env["VESPER_ARTIFACTS"] = str(artifacts)
    return run_process(argv, cwd=work, input_text="", env=env, log=log, timeout=timeout)


def copy_build_dirs(source, target, ignore):
    """Copy what build setup left in ignored top-level entries, links kept as links."""
    for name in ignore:
        path = source / name
        if path.is_symlink():
            os.symlink(os.readlink(path), target / name)
        elif path.is_dir():
            shutil.copytree(path, target / name, symlinks=True)
        elif path.is_file():
            copy_file(path, target / name)


def execute_check(script_name, package_source, checks_manifest, candidate, candidate_manifest, log, launcher,
                  timeout=45, gate_env=(), artifacts=None):
    """Give every gate the same isolated input layout, including baseline reproducers."""
    with tempfile.TemporaryDirectory(dir=log.parent, prefix="gate-") as temp:
        home = Path(temp)
        package, isolated = home / "checks", home / "candidate"
        copy_tree(package_source, package)
        copy_tree(candidate, isolated)
        require(inventory(package) == checks_manifest and inventory(isolated) == candidate_manifest,
                "Gate inputs changed during preparation")
        script = package / script_name
        mode = stat.S_IMODE(isolated.stat().st_mode)
        if isinstance(launcher, Sandbox):
            code = launcher.run(check_job(home, script_name, gate_env, artifacts), input_text="", log=log,
                                timeout=timeout)
        else:
            command = ([launcher, "check", str(script), str(isolated)] if launcher
                       else [sys.executable, "-I", "-B", str(script), str(isolated)])
            env = gate_environment(temp, gate_env)
            if artifacts is not None:
                env["VESPER_ARTIFACTS"] = str(artifacts)
            code = run_process(command, cwd=home, input_text="", env=env, log=log, timeout=timeout)
        intact = (inventory(package) == checks_manifest and inventory(isolated) == candidate_manifest
                  and stat.S_IMODE(isolated.stat().st_mode) == mode)
        return code, intact


def merge_overlay(source, target):
    """Copy QA's overlay into the gate's work copy. Overlay files replace candidate files of the
    same name there; a file/directory clash is a candidate defect. Returns an error or None."""
    try:
        target.mkdir(parents=True, exist_ok=True)
        for name, (digest, _) in inventory(source).items():
            destination = target / name
            if digest is None:
                if destination.exists() and not destination.is_dir():
                    return f"Overlay directory {name} clashes with a candidate file"
                destination.mkdir(exist_ok=True)
            else:
                if destination.exists() and not destination.is_file():
                    return f"Overlay file {name} clashes with a candidate directory"
                destination.unlink(missing_ok=True)
                copy_file(source / name, destination)
    except OSError as exc:
        return f"Overlay could not be placed in the work copy: {exc}"
    return None


def execute_command_check(command, overlay, package_source, checks_manifest, candidate, candidate_manifest, log,
                          launcher, timeout=45, gate_env=(), prepared=None, ignore=(), dependencies=None,
                          artifacts=None):
    """Run an approved argv in a throwaway copy of the candidate, with QA's overlay copied in first.

    Tools may write caches and reports in that copy. The gate never gets checks/ or the verified
    candidate; intact reports whether both are unchanged afterwards. prepared is the copy build
    setup ran in: its ignored directories (node_modules and the like) are copied in too."""
    mode = stat.S_IMODE(candidate.stat().st_mode)

    def unchanged():
        return (inventory(package_source) == checks_manifest and inventory(candidate) == candidate_manifest
                and stat.S_IMODE(candidate.stat().st_mode) == mode)

    with tempfile.TemporaryDirectory(dir=log.parent, prefix="gate-") as temp:
        home = Path(temp)
        work = home / "work"
        copy_tree(candidate, work)
        require(inventory(work) == candidate_manifest, "Gate inputs changed during preparation")
        if prepared is not None:
            copy_build_dirs(prepared, work, ignore)
        if overlay:
            staging, prefix = home / "overlay", overlay["from"] + "/"
            copy_tree(package_source / overlay["from"], staging)
            require(inventory(staging) == {path.removeprefix(prefix): value for path, value
                                           in checks_manifest.items() if path.startswith(prefix)},
                    "Gate inputs changed during preparation")
            problem = merge_overlay(staging, work if overlay["to"] == "." else work / overlay["to"])
            shutil.rmtree(staging)
            if problem:
                log.write_text(problem + "\n", encoding="utf-8")
                return 1, unchanged()
        code = launch_command("check-command", command, work, temp, log, launcher, timeout, gate_env, dependencies,
                              artifacts=artifacts)
        return code, unchanged()


class Runner:
    def __init__(self, root):
        self.root = root
        self.control = root / ".builder"
        self.state_file = self.control / "state.json"

    @contextmanager
    def lock(self):
        require(self.root.is_dir() and (self.root / "plan").is_dir(), "Initialize a project first")
        self.control.mkdir(mode=0o700, exist_ok=True)
        sync_dir(self.root)
        with (self.control / "lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BuilderError("Another runner is active for this project") from exc
            yield

    def review(self):
        contract, bundle = review_bundle(self.root)
        return {"digest": fingerprint(bundle), "packet_digest": fingerprint({k: v for k, v in bundle.items() if k != "plan_critique"}), "contract": contract, "files": bundle}

    def review_sheet(self):
        """The plain-language plan sheet (P2-T2). Printing it never moves the "what changed" baseline."""
        from .approvals import run_store
        from .sheets import plan_sheet
        from .usage import for_project, render
        contract, bundle = review_bundle(self.root)
        sheet = plan_sheet(self.root, contract, bundle, fingerprint(bundle), run_store(self.root)).full
        estimate = for_project(contract, bundle)
        return sheet + "\n" + (render(estimate) if "error" not in estimate
                                else "Estimate: unavailable (" + estimate["error"] + ")") + "\n"

    def estimate(self):
        """Jobs, AI calls, tokens, wall time and % of plan limits for this plan (P2-T3)."""
        from .usage import for_project
        contract, bundle = review_bundle(self.root, estimating=True)
        return for_project(contract, bundle)

    def approve(self, digest):
        from .approvals import confirm, keep, run_store
        from .sheets import plan_sheet
        require(not self.state_file.exists(), "A contract is already approved for this run")
        contract, bundle = review_bundle(self.root)
        require(fingerprint(bundle) == digest, "Approval digest changed. Review the current draft again.")
        if bundle.get("planning", {}).get("depth") in ("full", "focused"):
            require(bundle.get("plan_critique", {}).get("report", {}).get("verdict") == "approve",
                    "Independent plan critique must approve this exact packet before implementation")
        proof = None
        if "repair" in bundle:
            from .repair import reproduction_record
            proof = reproduction_record(self, digest, bundle)
        # Human-only (P2-T2): the owner confirms on the plan sheet before anything is locked.
        confirmation = confirm("approve-plan", str(self.root), digest,
                               plan_sheet(self.root, contract, bundle, digest, run_store(self.root)))
        approval_id = uuid4().hex
        approved = self.control / "approvals" / approval_id
        initial = self.control / "snapshots" / approval_id
        approved.mkdir(parents=True)
        initial.parent.mkdir(exist_ok=True)
        for name in ("plan", "checks"):
            copy_tree(self.root / name, approved / name)
        copy_tree(self.root / "seed", initial)
        require(inventory(approved / "plan") == bundle["plan"]
                and inventory(approved / "checks") == bundle["checks"]
                and inventory(initial) == bundle["seed"], "Files changed during approval")
        sync_tree(approved)
        sync_dir(approved.parent.parent)
        sync_tree(initial)
        state = {"format": 1, "digest": digest, "approved_at": stamp(), "approval_id": approval_id,
                 "bundle": bundle, "snapshot_id": approval_id, "snapshot_digest": fingerprint(bundle["seed"]),
                 "completed": [], "active": None, "attempts": []}
        if proof:
            state["repair_reproduction"] = proof
        state["confirmation"] = {key: confirmation[key] for key in ("digest", "confirmer", "at")}
        self.save(state)
        keep(run_store(self.root), confirmation)
        return self.status()

    def save(self, state):
        atomic_json(self.state_file, state)

    def state(self):
        require(self.state_file.is_file(), "Approve the reviewed contract before starting work")
        data = read_json(self.state_file)
        require(data.get("format") == 1, "Unsupported state format")
        return data

    def approval(self, state):
        return self.control / "approvals" / state["approval_id"]

    def frozen_contract(self, state):
        approval = self.approval(state)
        bundle = state["bundle"]
        require(fingerprint(bundle) == state["digest"]
                and inventory(approval / "plan") == bundle["plan"]
                and inventory(approval / "checks") == bundle["checks"],
                "Frozen approval files have changed")
        return reviewed_contract(approval / "plan", bundle["plan"], bundle["checks"])

    def snapshot(self, state):
        return self.control / "snapshots" / state["snapshot_id"]

    def check_snapshot(self, state):
        contents = inventory(self.snapshot(state))
        require(fingerprint(contents) == state["snapshot_digest"], "Accepted snapshot has changed")
        return contents

    def ready(self, state, contract):
        done = set(state["completed"])
        return next((job for job in contract["jobs"]
                     if job["id"] not in done and set(job["depends_on"]) <= done), None)

    def attempts_for(self, state, job):
        return [item for item in state["attempts"] if item["job"] == job["id"]
                and item["outcome"] != "interrupted"]

    def budget_for(self, state, job):
        return job.get("max_attempts", 2) + sum(
            grant["job"] == job["id"] for grant in state.get("retry_grants", []))

    def retry(self, reason):
        state = self.state()
        job = self.ready(state, self.frozen_contract(state))
        require(reason.strip(), "Give a reason for granting another attempt")
        require(not state["active"] and job
                and len(self.attempts_for(state, job)) >= self.budget_for(state, job),
                "The next job must be blocked by its attempt budget")
        state.setdefault("retry_grants", []).append({"job": job["id"], "reason": reason.strip(), "at": stamp()})
        self.save(state)
        return self.status()

    def status(self):
        if not self.state_file.exists():
            return {"status": "planning", "project": str(self.root)}
        state = self.state()
        contract = self.frozen_contract(state)
        self.check_snapshot(state)
        job = self.ready(state, contract)
        if state["active"]:
            phase = "awaiting_review" if "review" in state["active"] else "active"
        elif job is None:
            phase = "complete"
        elif len(self.attempts_for(state, job)) >= self.budget_for(state, job):
            phase = "blocked"
        else:
            phase = "ready"
        return {"status": phase, "title": contract["title"], "delivery": contract["delivery"],
                "digest": state["digest"], "snapshot": str(self.snapshot(state)),
                "completed": state["completed"], "next_job": job and job["id"],
                "active": state["active"], "attempts": state["attempts"],
                "retry_grants": state.get("retry_grants", [])}

    def attempt_dir(self, attempt):
        return self.control / "attempts" / attempt["id"]

    def begin(self, state, contract, provider, adapter=None, shell=False):
        require(not state["active"], "An attempt is active. Submit or abandon it first.")
        job = self.ready(state, contract)
        require(job, "No jobs remain")
        previous = self.attempts_for(state, job)
        require(len(previous) < self.budget_for(state, job), f"Retry budget exhausted for {job['id']}")
        base = self.check_snapshot(state)
        require(GATES_DIR not in base, f"{GATES_DIR} is reserved for the workers' copy of the gates; "
                                       "rename it in the seed")
        attempt = {"id": uuid4().hex, "job": job["id"], "provider": provider,
                   **({"adapter": adapter} if adapter else {}),
                   "started_at": stamp(), "base": state["snapshot_id"], "checks": []}
        directory = self.attempt_dir(attempt)
        directory.mkdir(parents=True)
        workspace = directory / "workspace"
        carried = self.carried_candidate(state, job, previous, base)
        if carried:
            number, source, proposed = carried
            attempt["started_from"] = previous[number - 1]["id"]
            copy_tree(source, workspace)
            require(inventory(workspace) == proposed, "Earlier candidate changed while copying")
        else:
            copy_tree(self.snapshot(state), workspace)
            require(inventory(workspace) == base, "Accepted snapshot changed while copying")
        # Workers read and run the gates (owner decision 2026-11-19). The copy is ignored by
        # verify, so it is never checked for scope or promoted; Vesper runs the approved gates.
        gates_copy = workspace / GATES_DIR
        copy_tree(self.approval(state) / "checks", gates_copy)
        copied = inventory(gates_copy)
        require({path: record[0] for path, record in copied.items()}
                == {path: record[0] for path, record in state["bundle"]["checks"].items()},
                "Approved checks changed while copying")
        for path, (digest, mode) in copied.items():
            if digest is not None:
                (gates_copy / path).chmod(mode & ~0o222)  # read-only files; folders stay removable
        final = len(state["completed"]) + 1 == len(contract["jobs"])
        gates = [check for check in contract["checks"] if final or check["id"] in job["checks"]]
        origin = None
        if previous:
            origin = (f"Your workspace starts from attempt {carried[0]}'s files, not the accepted version: "
                      "keep what works and fix what failed." if carried else
                      "Your workspace starts from the accepted version: no earlier attempt left a checked "
                      "candidate that is still intact.")
        prompt = worker_prompt(contract, job, self.approval(state) / "plan", state["bundle"]["plan"],
                               attempt_history(previous),
                               state["bundle"].get("intake"),
                               state["bundle"].get("team", {}).get("jobs", {}).get(job["id"]),
                               state["bundle"].get("planning"), shell=shell, gates=gates, origin=origin)
        if "repair" in state["bundle"]:
            proof = state["repair_reproduction"]
            incident = state["bundle"]["repair"].get("source_incident")
            prompt += ("\n\nRepair evidence (data): "
                       + json.dumps({"baseline_reproducer_exit_code": proof["baseline_exit_code"],
                                     "source_incident": incident}))
        (directory / "job.md").write_text(prompt, encoding="utf-8")
        state["active"] = attempt
        self.save(state)
        return job, attempt, workspace, prompt

    def carried_candidate(self, state, job, previous, base):
        """The newest earlier candidate of this job that passed the scope check, as
        (attempt number, path, inventory), or None when there is none or it changed since."""
        for number in range(len(previous), 0, -1):
            item = previous[number - 1]
            record = item.get("candidate")
            if not record or item.get("base") != state["snapshot_id"]:
                continue
            source = self.root / record["path"]
            try:
                proposed = inventory(source)
            except (BuilderError, OSError):
                return None
            unchanged = (fingerprint(proposed) == record["digest"]
                         and not scope_changes(base, proposed, job["paths"])[1])
            return (number, source, proposed) if unchanged else None
        return None

    def prepare(self):
        state = self.state()
        _, attempt, workspace, _ = self.begin(state, self.frozen_contract(state), "manual")
        return {**attempt, "workspace": str(workspace), "brief": str(workspace.parent / "job.md")}

    def finish(self, state, outcome, reason=None, failure_kind=None):
        attempt = state["active"]
        attempt = {**attempt, "outcome": outcome, "finished_at": stamp()}
        if reason:
            attempt["reason"] = reason
        if failure_kind:
            attempt["failure_kind"] = failure_kind
        state["attempts"].append(attempt)
        state["active"] = None
        self.save(state)
        return attempt

    def manual_attempt(self, state, attempt_id):
        attempt = state["active"]
        require(attempt and attempt["provider"] == "manual" and "adapter" not in attempt
                and attempt["id"] == attempt_id,
                "No matching manual attempt is active")
        return attempt

    def abandon(self, attempt_id):
        state = self.state()
        attempt = state["active"]
        require(attempt and attempt["id"] == attempt_id, "No matching attempt is active")
        return self.finish(state, "interrupted", "Attempt abandoned by the operator")

    def submit(self, attempt_id, launcher=None):
        state = self.state()
        attempt = self.manual_attempt(state, attempt_id)
        contract = self.frozen_contract(state)
        job = next(item for item in contract["jobs"] if item["id"] == attempt["job"])
        require("review" not in attempt, "Candidate already awaits independent review")
        return self.verify(state, contract, job, self.attempt_dir(attempt) / "workspace", launcher)

    def verify(self, state, contract, job, workspace, launcher):
        if "repair" in state["bundle"]:
            require(launcher, "Vesper repair gates require a confined launcher")
        attempt = state["active"]
        attempt["checks"] = []
        attempt.pop("setup", None)
        self.save(state)
        ignore = (*contract.get("build", {}).get("ignore", ()), GATES_DIR)
        try:
            base = self.check_snapshot(state)
            # Worker workspaces may hold build output in ignored directories; it is never promoted.
            drop_python_caches(workspace, ignore)
            proposed = inventory(workspace, ignore)
            if "repair" in state["bundle"]:
                from .repair import validate_git_candidate
                validate_git_candidate(base, proposed)
            mode = stat.S_IMODE(self.snapshot(state).stat().st_mode)
            require(stat.S_IMODE(workspace.stat().st_mode) == mode, "Workspace root mode has changed")
            changed, denied = scope_changes(base, proposed, job["paths"])
            require(not denied, "Changes outside job scope: " + ", ".join(denied))
            directory = self.attempt_dir(attempt) / ("verify-" + uuid4().hex)
            directory.mkdir()
            candidate = directory / "candidate"
            copy_tree(workspace, candidate, ignore)
            require(inventory(candidate) == proposed, "Attempt changed while copying")
            # A retry of this job starts from this candidate (finding 48).
            attempt["candidate"] = {"path": str(candidate.relative_to(self.root)), "digest": fingerprint(proposed)}
            self.run_gates(state, contract, job, candidate, proposed, directory, launcher)
            self.frozen_contract(state)
            attempt["changed"] = changed
            if "team" in state["bundle"]:
                return self.stage_review(state, job, candidate, directory, proposed)
            return self.accept_candidate(state, job["id"], candidate, proposed)
        except BuilderError as exc:
            if any(item["exit_code"] or item.get("evidence_error")
                   for item in attempt["checks"] + attempt.get("setup", [])):
                kind = "check"
            elif str(exc).startswith("Changes outside job scope:"):
                kind = "scope"
            else:
                kind = "integrity"
            return self.finish(state, "rejected", str(exc), kind)
        except OSError as exc:
            return self.finish(state, "rejected", str(exc), "environment")

    def accept_candidate(self, state, job_id, candidate, manifest):
        # Leave the staged candidate intact until the new snapshot and state are durable.
        next_id = uuid4().hex
        target = self.control / "snapshots" / next_id
        copy_tree(candidate, target)
        require(inventory(target) == manifest, "Candidate changed during promotion")
        sync_tree(target)
        state["snapshot_id"] = next_id
        state["snapshot_digest"] = fingerprint(manifest)
        state["completed"].append(job_id)
        state["active"]["snapshot_id"] = next_id
        return self.finish(state, "accepted")

    def stage_review(self, state, job, candidate, directory, proposed):
        attempt = state["active"]
        packet = {"attempt_id": attempt["id"], "job": job["id"], "paths": attempt["changed"],
                  "base_digest": state["snapshot_digest"], "candidate_digest": fingerprint(proposed),
                  "root_mode": stat.S_IMODE(candidate.stat().st_mode),
                  "checks": [dict(check, evidence=read_tail(self.root / check["log"], limit=1800))
                             for check in attempt["checks"]]}
        role_key = "security_reviewer" if needs_security(job, attempt["changed"]) else "reviewer"
        profile = state["bundle"]["team"][role_key]
        packet["reviewer_revision"] = profile["revision"]
        earlier = [{"attempt": number, "path": finding["path"],
                    "evidence": finding["evidence"][:EARLIER_EVIDENCE_LIMIT],
                    "recommendation": finding["recommendation"][:EARLIER_EVIDENCE_LIMIT]}
                   for number, item in enumerate(self.attempts_for(state, job), 1)
                   for finding in (item.get("review") or {}).get("findings", [])
                   if finding.get("severity") == "blocking"]
        if earlier:
            # A retry's reviewer checks these first, so the bar does not move between versions.
            packet["earlier_blockers"] = earlier[-EARLIER_BLOCKERS_LIMIT:]
        if state["bundle"].get("design_review") and job["role"] == "frontend":
            packet["design_review"] = True
        workspace = directory / "review"
        workspace.mkdir()
        copy_tree(self.snapshot(state), workspace / "base")
        copy_tree(candidate, workspace / "candidate")
        copy_tree(self.approval(state) / "plan", workspace / "plan")
        require(fingerprint(inventory(workspace / "base")) == packet["base_digest"]
                and fingerprint(inventory(workspace / "candidate")) == packet["candidate_digest"]
                and inventory(workspace / "plan") == state["bundle"]["plan"],
                "Review copy changed during preparation")
        # Gate evidence (P2-T1): the approved scripts, each gate's log and what it saved. All of it
        # is inside the review view digest, so a changed copy is refused.
        copy_tree(self.approval(state) / "checks", workspace / "checks")
        require(inventory(workspace / "checks") == state["bundle"]["checks"], "Review copy changed during preparation")
        (workspace / "logs").mkdir()
        for check in attempt["checks"]:
            copy_log_tail(self.root / check["log"], workspace / "logs" / (check["id"] + ".log"))
        (workspace / "artifacts").mkdir()
        if (directory / "artifacts").is_dir():
            omitted = copy_artifacts(directory / "artifacts", workspace / "artifacts")
            if omitted:
                packet["artifacts_omitted"] = omitted[:50]
            # The gates' raw folder may hold links or pipes; only the checked copy stays. A folder a
            # gate left unremovable must not reject the candidate (sync_tree skips non-files anyway).
            shutil.rmtree(directory / "artifacts", ignore_errors=True)
        write_diff(workspace / "diff.patch", workspace / "base", workspace / "candidate", attempt["changed"])
        (workspace / "review.json").write_text(json.dumps(packet, indent=2), encoding="utf-8")
        (workspace / "review.schema.json").write_text(json.dumps(report_schema(packet), indent=2), encoding="utf-8")
        (workspace / "review.md").write_text(review_prompt(profile, packet), encoding="utf-8")
        # Native adapters request read-only access. A user-supplied launcher must
        # enforce its own sandbox; the review copy can never be promoted.
        attempt["review"] = {**packet, "workspace": str(workspace), "directory": directory.name}
        attempt["review_view_digest"] = fingerprint(inventory(workspace))
        sync_tree(directory)
        sync_dir(self.attempt_dir(attempt).parent)
        self.save(state)
        return {**attempt, "outcome": "awaiting_review"}

    def review_candidate(self, report=None, *, brain=None, launcher=None, trust_host=False,
                         external_attested=False, review_timeout=180, review_max_turns=20):
        """Accept or reject the staged candidate on an attested report or a launched reviewer brain."""
        review_limits(review_timeout, review_max_turns)
        state = self.state()
        attempt = state["active"]
        require(attempt and "review" in attempt, "No tested candidate awaits review")
        packet = attempt["review"]
        self.frozen_contract(state)
        require(state["snapshot_id"] == attempt["base"] and state["snapshot_digest"] == packet["base_digest"],
                "Accepted baseline changed before review")
        self.check_snapshot(state)
        directory = self.attempt_dir(attempt) / packet["directory"]
        candidate = directory / "candidate"
        workspace = directory / "review"
        require(fingerprint(inventory(workspace)) == attempt["review_view_digest"],
                "Staged review evidence changed")
        if "repair" in state["bundle"]:
            require(launcher and report is None, "A Vesper repair requires a confined, separately launched reviewer")
        if report is not None:
            require("repair" not in state["bundle"], "A Vesper repair requires a separately launched reviewer")
            require(external_attested, "Attest that the report came from an independent reviewer")
        launched = {"provider": "operator"}
        if report is None:
            require(brain, "Provide an independent JSON report or choose a reviewer brain")
            # Use a fresh copy so a prior reviewer invocation cannot supply a later reviewer's inputs.
            with tempfile.TemporaryDirectory(prefix="review-session-", dir=directory) as temp:
                session = Path(temp)
                view = session / "workspace"
                copy_tree(workspace, view)
                require(fingerprint(inventory(view / "base")) == packet["base_digest"]
                        and fingerprint(inventory(view / "candidate")) == packet["candidate_digest"]
                        and inventory(view / "plan") == state["bundle"]["plan"],
                        "Reviewer inputs changed before launch")
                # Rebuild the prompt and evidence from the frozen role and recorded packet.
                role_key = "security_reviewer" if packet["reviewer_revision"] == (
                    state["bundle"]["team"]["security_reviewer"]["revision"]) else "reviewer"
                profile = state["bundle"]["team"][role_key]
                (view / "review.json").write_text(json.dumps({key: value for key, value in packet.items()
                                                           if key not in ("workspace", "directory")}, indent=2))
                write_diff(view / "diff.patch", view / "base", view / "candidate", attempt["changed"])
                schema = report_schema(packet)
                (view / "review.schema.json").write_text(json.dumps(schema, indent=2))
                (view / "review.md").write_text(review_prompt(profile, packet))
                view_digest = fingerprint(inventory(view))
                response = session / "response.json"
                log = directory / ("reviewer-" + uuid4().hex + ".log")
                code = launch(brain, "reviewer", launcher, trust_host, work=view,
                              input_text=review_prompt(profile, packet), log=log, timeout=review_timeout,
                              response=response, schema=schema, max_turns=review_max_turns,
                              ledger={"run": self.root, "job": attempt["job"], "role": "reviewer"})
                require(code == 0, f"Reviewer exited {code}. Tested candidate remains pending.")
                require(fingerprint(inventory(view)) == view_digest, "Reviewer modified its read-only input copy")
                output = response if response.is_file() else log
                require(not output.is_symlink() and output.stat().st_size <= 256_000,
                        "Reviewer output was linked or exceeded the report limit")
                reply = output.read_text(encoding="utf-8")
                report = parse_result(brain, reply)
                launched = {"provider": brain.name, "adapter": brain.adapter.name}
                spent = usage(brain, reply)
                if spent:
                    launched["usage"] = spent
        require(len(json.dumps(report)) <= 256_000, "Reviewer output exceeded the report limit")
        blockers = validate_report(report, packet)
        attested = None
        if launched["provider"] == "operator":
            # Human-only (P2-T2): a person vouches that the supplied report is independent. The
            # candidate and contract checks below run after the confirmation.
            from .approvals import confirm, run_store
            from .sheets import attest_sheet
            sheet, report_digest = attest_sheet(
                run_store(self.root), f"{self.root}#{attempt['job']}",
                f"job {attempt['job']}, candidate {packet['candidate_digest'][:12]}", report)
            attested = confirm("attest-independence", f"{self.root}#{attempt['job']}", report_digest, sheet)
            require(fingerprint(inventory(workspace)) == attempt["review_view_digest"],
                    "Staged review evidence changed")
        self.frozen_contract(state)
        manifest = inventory(candidate)
        require(fingerprint(manifest) == packet["candidate_digest"]
                and stat.S_IMODE(candidate.stat().st_mode) == packet["root_mode"],
                "Tested candidate changed after verification")
        attempt["review"] = {**packet, **{key: report[key] for key in ("verdict", "summary", "evidence", "findings")},
                             **launched}
        if blockers:
            result = self.finish(state, "rejected", "Review blockers: " + "; ".join(
                f"{item['path']}: {item['recommendation']}" for item in blockers), "review")
        else:
            result = self.accept_candidate(state, attempt["job"], candidate, manifest)
        if attested:
            from .approvals import keep, run_store
            keep(run_store(self.root), attested)
        return result

    def run_gates(self, state, contract, job, candidate, proposed, directory, launcher):
        """The job's gates (every gate on the final job). Build setup runs once, before the
        first command gate, in a prepared copy that is removed afterwards."""
        build = contract.get("build", {})
        gate_env = contract.get("gate_env", ())
        dependencies = self.control / "cache" if build.get("setup") else None
        mode = stat.S_IMODE(candidate.stat().st_mode)
        final = len(state["completed"]) + 1 == len(contract["jobs"])
        with ExitStack() as cleanup:
            prepared = None
            for check in contract["checks"]:
                if not (final or check["id"] in job["checks"]):
                    continue
                if "command" in check and dependencies and prepared is None:
                    temp = cleanup.enter_context(tempfile.TemporaryDirectory(dir=directory, prefix="setup-"))
                    prepared = Path(temp) / "work"
                    self.run_setup(state, build, candidate, proposed, prepared, directory, launcher,
                                   gate_env, dependencies)
                self.run_check(state, check, candidate, directory, launcher, gate_env=gate_env,
                               prepared=prepared, ignore=build.get("ignore", ()), dependencies=dependencies)
                require(inventory(candidate) == proposed and stat.S_IMODE(candidate.stat().st_mode) == mode,
                        f"Check {check['id']} modified the candidate")

    def run_setup(self, state, build, candidate, manifest, prepared, directory, launcher, gate_env, dependencies):
        """Install toolchain dependencies (pnpm install, go mod download) into a copy of the
        candidate. The only gate-side step a launcher may give network access. It must leave
        tracked files, lockfiles included, exactly as the candidate has them."""
        require("repair" not in state["bundle"], "Vesper repairs cannot run build setup")
        logs = directory / "logs"
        logs.mkdir(exist_ok=True)
        for name in ("go-mod", "pnpm-store"):
            (dependencies / name).mkdir(mode=0o700, parents=True, exist_ok=True)
        copy_tree(candidate, prepared)
        require(inventory(prepared) == manifest, "Gate inputs changed during preparation")
        results = state["active"].setdefault("setup", [])
        for index, command in enumerate(build["setup"], 1):
            log = logs / f"setup-{index}.log"
            with tempfile.TemporaryDirectory(dir=directory, prefix="setup-home-") as temp:
                # -modcacherw keeps Go's module cache deletable along with the run.
                goflags = " ".join(filter(None, (os.environ.get("GOFLAGS") if "GOFLAGS" in gate_env else None,
                                                 "-modcacherw")))
                code = launch_command("setup", command, prepared, temp, log, launcher, build.get("timeout", 600),
                                      gate_env, dependencies, {"GOFLAGS": goflags})
            results.append({"command": command, "exit_code": code, "log": str(log.relative_to(self.root))})
            self.save(state)
            require(code == 0, f"Build setup {command[0]} exited {code}\n{read_tail(log)}")
        after = inventory(prepared, build.get("ignore", ()))
        changed = sorted(path for path in manifest.keys() | after.keys() if manifest.get(path) != after.get(path))
        require(not changed, "Build setup changed tracked files: " + ", ".join(changed))
        require(inventory(candidate) == manifest, "Build setup modified the candidate")

    def run_check(self, state, check, candidate, directory, launcher, gate_env=(), prepared=None, ignore=(),
                  dependencies=None):
        logs = directory / "logs"
        logs.mkdir(exist_ok=True)
        log = logs / (check["id"] + ".log")
        # Whatever the gate saves here (screenshots, traces) reaches the reviewer (P2-T1).
        artifacts = directory / "artifacts" / check["id"]
        artifacts.mkdir(parents=True, exist_ok=True)
        limit = check.get("timeout", REGRESSION_TIMEOUT if check["id"] == "VESPER_REGRESSION" else 45)
        if "command" in check:
            code, intact = execute_command_check(check["command"], check.get("overlay"),
                                                 self.approval(state) / "checks", state["bundle"]["checks"],
                                                 candidate, inventory(candidate), log, launcher,
                                                 timeout=limit, gate_env=gate_env, prepared=prepared,
                                                 ignore=ignore, dependencies=dependencies, artifacts=artifacts)
        else:
            code, intact = execute_check(check["script"], self.approval(state) / "checks",
                                         state["bundle"]["checks"], candidate, inventory(candidate), log, launcher,
                                         timeout=limit, gate_env=gate_env, artifacts=artifacts)
        result = {"id": check["id"], "exit_code": code, "log": str(log.relative_to(self.root))}
        state["active"]["checks"].append(result)
        self.save(state)
        require(intact, f"Check {check['id']} modified the candidate or check package")
        require(code == 0, f"Check {check['id']} exited {code}\n{read_tail(log)}")
        failure_id = state["bundle"].get("repair", {}).get("failure_id")
        if check["id"] == "VESPER_REPRO" and failure_id:
            from .repair import read_repro_result
            try:
                read_repro_result(log, failure_id, "fixed")
            except BuilderError as exc:
                result["evidence_error"] = str(exc)
                self.save(state)
                raise

    def run(self, selection, launcher=None, *, trust_host=False, review_timeout=180, review_max_turns=20,
            start_after=None, clock=None, sleep=None, reserve=None):
        """Run every ready job unattended. ``selection`` (brains.Selection) picks each job's
        worker brain by role and the reviewer brain (by default the job's worker brain).

        Before a job's first attempt the plan limits are checked (P2-T4): a job that would cross
        the reserve is not started and the run returns ``paused_for_limits``; a started job is
        never stopped. ``start_after`` ("HH:MM") waits for that local time first."""
        from . import usage as plan_usage
        review_limits(review_timeout, review_max_turns)
        if start_after:
            plan_usage.wait_until(start_after, clock=clock, sleep=sleep)
        if reserve is None:
            from .brains import load_settings
            try:
                reserve = load_settings().get("limits.reserve_percent", 25)
            except BuilderError:
                reserve = 25
        notes = []
        limits = {"review_timeout": review_timeout, "review_max_turns": review_max_turns}
        state = self.state()
        contract = self.frozen_contract(state)
        if "repair" in state["bundle"]:
            require(launcher, "Vesper repairs require a confined launcher")
        jobs = {job["id"]: job for job in contract["jobs"]}

        def reviewer_for(job):
            return selection.reviewer(lambda: selection.worker(job["role"]))

        if state["active"]:
            if "review" in state["active"]:
                self.review_candidate(brain=reviewer_for(jobs[state["active"]["job"]]), launcher=launcher,
                                      trust_host=trust_host, **limits)
                state = self.state()
            else:
                active = state["active"]
                require(active["provider"] != "manual" or "adapter" in active,
                        "Submit or abandon the active manual attempt first")
                self.finish(state, "interrupted", "Recovered after an interrupted runner", "interrupted")
        while self.ready(state, contract):
            if self.status()["status"] == "blocked":
                break
            # Choose and check every brain the job needs before it starts.
            ready = self.ready(state, contract)
            if not self.attempts_for(state, ready):
                current = ready
                pause, found = plan_usage.limit_check(
                    contract, state["bundle"], ready, plan_usage.entries(), reserve=reserve,
                    brains=lambda role: reviewer_for(current) if role == "reviewer" else selection.worker(role),
                    now=clock() if clock else datetime.now(timezone.utc))
                notes += found
                if pause:
                    return {**self.status(), "status": "paused_for_limits", "pause": pause,
                            **({"limit_notes": notes} if notes else {})}
            brain = selection.worker(ready["role"])
            brain_command(brain, "worker", launcher, trust_host, role=ready["role"])
            reviewer = reviewer_for(ready) if "team" in state["bundle"] else None
            if reviewer:
                brain_command(reviewer, "reviewer", launcher, trust_host, max_turns=review_max_turns)
            # Shell only inside a real sandbox backend (P1-T10); the prompt says so only then.
            shell = "shell" in brain_tools(brain, "worker", ready["role"], isinstance(launcher, Sandbox))
            job, attempt, workspace, prompt = self.begin(state, contract, brain.name, brain.adapter.name, shell)
            log = self.attempt_dir(attempt) / "worker.log"
            print(f"{job['id']} | {brain.name} | attempt {attempt['id'][:8]}", file=sys.stderr, flush=True)

            def record_child(pid):
                attempt["child_pid"] = pid
                self.save(state)

            code = launch(brain, "worker", launcher, trust_host, work=workspace, input_text=prompt, log=log,
                          timeout=job.get("timeout", 180), on_start=record_child, role=job["role"],
                          ledger={"run": self.root, "job": job["id"], "role": job["role"]})
            attempt["worker_log"] = str(log.relative_to(self.root))
            if code != 0:
                said = brain.adapter.summary(read_tail(log, limit=200_000))
                self.finish(state, "worker_failed",
                            f"Worker brain {brain.name} exited {code}\n{said[-3500:]}", "provider")
            else:
                result = self.verify(state, contract, job, workspace, launcher)
                if result["outcome"] == "awaiting_review":
                    self.review_candidate(brain=reviewer, launcher=launcher, trust_host=trust_host, **limits)
                    state = self.state()
        return {**self.status(), **({"limit_notes": notes} if notes else {})}

    def export(self, destination):
        state = self.state()
        self.frozen_contract(state)
        self.check_snapshot(state)
        require(destination != self.root and self.root not in destination.parents,
                "Export outside the project directory")
        require(not destination.exists(), "Export destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".builder-export-") as staging:
            copy = Path(staging) / "app"
            copy_tree(self.snapshot(state), copy)
            require(fingerprint(inventory(copy)) == state["snapshot_digest"], "Snapshot changed during export")
            require(not destination.exists(), "Export destination already exists")
            copy.rename(destination)
        return {"snapshot": state["snapshot_id"], "destination": str(destination),
                "completed": state["completed"]}
