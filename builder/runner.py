"""Single-writer state machine with frozen checks and verified snapshots."""
from contextlib import contextmanager
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
                        require, review_bundle, reviewed_contract)
from .process import run_process
from .providers import provider_command, provider_environment, worker_prompt
from .review_gate import decode_provider_report, needs_security, prompt as review_prompt, validate_report, write_diff


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
            with (Path(directory) / file).open("rb") as stream:
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


def copy_tree(source, destination):
    # copytree's directory copystat preserves extended attributes. Build the
    # tree from its recorded representation instead.
    destination.mkdir()
    entries = inventory(source)
    for name, (digest, _) in entries.items():
        if digest is None:
            (destination / name).mkdir()
        else:
            copy_file(source / name, destination / name)
    for name, (digest, mode) in reversed(list(entries.items())):
        if digest is None:
            (destination / name).chmod(mode)
    destination.chmod(stat.S_IMODE(source.stat().st_mode))


def execute_check(script_name, package_source, checks_manifest, candidate, candidate_manifest, log, launcher, timeout=45):
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
        command = ([launcher, "check", str(script), str(isolated)] if launcher
                   else [sys.executable, "-I", "-B", str(script), str(isolated)])
        env = {"PATH": os.defpath, "HOME": temp, "TMPDIR": temp,
               "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        code = run_process(command, cwd=home, input_text="", env=env, log=log, timeout=timeout)
        intact = (inventory(package) == checks_manifest and inventory(isolated) == candidate_manifest
                  and stat.S_IMODE(isolated.stat().st_mode) == mode)
        return code, intact


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
        return {"digest": fingerprint(bundle), "contract": contract, "files": bundle}

    def approve(self, digest):
        require(not self.state_file.exists(), "A contract is already approved for this run")
        _, bundle = review_bundle(self.root)
        require(fingerprint(bundle) == digest, "Approval digest changed. Review the current draft again.")
        proof = None
        if "repair" in bundle:
            from .repair import reproduction_record
            proof = reproduction_record(self, digest, bundle)
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
        self.save(state)
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

    def begin(self, state, contract, provider):
        require(not state["active"], "An attempt is active. Submit or abandon it first.")
        job = self.ready(state, contract)
        require(job, "No jobs remain")
        previous = self.attempts_for(state, job)
        require(len(previous) < self.budget_for(state, job), f"Retry budget exhausted for {job['id']}")
        base = self.check_snapshot(state)
        attempt = {"id": uuid4().hex, "job": job["id"], "provider": provider,
                   "started_at": stamp(), "base": state["snapshot_id"], "checks": []}
        directory = self.attempt_dir(attempt)
        directory.mkdir(parents=True)
        workspace = directory / "workspace"
        copy_tree(self.snapshot(state), workspace)
        require(inventory(workspace) == base, "Accepted snapshot changed while copying")
        prompt = worker_prompt(contract, job, self.approval(state) / "plan", state["bundle"]["plan"],
                               previous[-1].get("reason") if previous else None,
                               state["bundle"].get("intake"),
                               state["bundle"].get("team", {}).get("jobs", {}).get(job["id"]))
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
        require(attempt and attempt["provider"] == "manual" and attempt["id"] == attempt_id,
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
        self.save(state)
        try:
            base = self.check_snapshot(state)
            proposed = inventory(workspace)
            if "repair" in state["bundle"]:
                from .repair import validate_git_candidate
                validate_git_candidate(base, proposed)
            mode = stat.S_IMODE(self.snapshot(state).stat().st_mode)
            require(stat.S_IMODE(workspace.stat().st_mode) == mode, "Workspace root mode has changed")
            changed = sorted(path for path in base.keys() | proposed.keys() if base.get(path) != proposed.get(path))
            denied = [
                path for path in changed
                if not owned(path, job["paths"])
                and not (path not in base and proposed[path][0] is None
                         and any(item.startswith(path + "/") and item in proposed
                                 and owned(item, job["paths"]) for item in changed))
            ]
            require(not denied, "Changes outside job scope: " + ", ".join(denied))
            directory = self.attempt_dir(attempt) / ("verify-" + uuid4().hex)
            directory.mkdir()
            candidate = directory / "candidate"
            copy_tree(workspace, candidate)
            require(inventory(candidate) == proposed, "Attempt changed while copying")
            final = len(state["completed"]) + 1 == len(contract["jobs"])
            for check in contract["checks"]:
                if final or check["id"] in job["checks"]:
                    self.run_check(state, check, candidate, directory, launcher)
                    require(inventory(candidate) == proposed and stat.S_IMODE(candidate.stat().st_mode) == mode,
                            f"Check {check['id']} modified the candidate")
            self.frozen_contract(state)
            attempt["changed"] = changed
            if "team" in state["bundle"]:
                return self.stage_review(state, job, candidate, directory, proposed)
            return self.accept_candidate(state, job["id"], candidate, proposed)
        except BuilderError as exc:
            if any(item["exit_code"] for item in attempt["checks"]):
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
        write_diff(workspace / "diff.patch", workspace / "base", workspace / "candidate", attempt["changed"])
        (workspace / "review.json").write_text(json.dumps(packet, indent=2), encoding="utf-8")
        (workspace / "review.md").write_text(review_prompt(profile, packet), encoding="utf-8")
        # Native adapters request read-only access. A user-supplied launcher must
        # enforce its own sandbox; the review copy can never be promoted.
        attempt["review"] = {**packet, "workspace": str(workspace), "directory": directory.name}
        attempt["review_view_digest"] = fingerprint(inventory(workspace))
        sync_tree(directory)
        sync_dir(self.attempt_dir(attempt).parent)
        self.save(state)
        return {**attempt, "outcome": "awaiting_review"}

    def review_candidate(self, report=None, *, provider=None, launcher=None, trust_host=False,
                         external_attested=False):
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
        if report is None:
            require(provider, "Provide an independent JSON report or select a reviewer provider")
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
                (view / "review.md").write_text(review_prompt(profile, packet))
                view_digest = fingerprint(inventory(view))
                response = session / "response.json"
                command = provider_command(provider, launcher, trust_host, operation="reviewer", response=response)
                log = directory / ("reviewer-" + uuid4().hex + ".log")
                code = run_process(command, cwd=view, input_text=review_prompt(profile, packet),
                                   env=provider_environment(provider, launcher), log=log, timeout=180)
                require(code == 0, f"Reviewer exited {code}. Tested candidate remains pending.")
                require(fingerprint(inventory(view)) == view_digest, "Reviewer modified its read-only input copy")
                output = response if response.is_file() else log
                require(not output.is_symlink() and output.stat().st_size <= 256_000,
                        "Reviewer output was linked or exceeded the report limit")
                report = decode_provider_report(output.read_text(encoding="utf-8"))
        require(len(json.dumps(report)) <= 256_000, "Reviewer output exceeded the report limit")
        blockers = validate_report(report, packet)
        self.frozen_contract(state)
        manifest = inventory(candidate)
        require(fingerprint(manifest) == packet["candidate_digest"]
                and stat.S_IMODE(candidate.stat().st_mode) == packet["root_mode"],
                "Tested candidate changed after verification")
        attempt["review"] = {**packet, **{key: report[key] for key in ("verdict", "summary", "evidence", "findings")},
                             "provider": provider or "operator"}
        if blockers:
            return self.finish(state, "rejected", "Review blockers: " + "; ".join(
                f"{item['path']}: {item['recommendation']}" for item in blockers), "review")
        return self.accept_candidate(state, attempt["job"], candidate, manifest)

    def run_check(self, state, check, candidate, directory, launcher):
        logs = directory / "logs"
        logs.mkdir(exist_ok=True)
        log = logs / (check["id"] + ".log")
        code, intact = execute_check(check["script"], self.approval(state) / "checks",
                                     state["bundle"]["checks"], candidate, inventory(candidate), log, launcher,
                                     timeout=120 if check["id"] == "VESPER_REGRESSION" else 45)
        result = {"id": check["id"], "exit_code": code, "log": str(log.relative_to(self.root))}
        state["active"]["checks"].append(result)
        self.save(state)
        require(intact, f"Check {check['id']} modified the candidate or check package")
        require(code == 0, f"Check {check['id']} exited {code}\n{read_tail(log)}")

    def run(self, provider, command, launcher=None, *, reviewer=None, trust_host=False):
        state = self.state()
        contract = self.frozen_contract(state)
        if "repair" in state["bundle"]:
            require(launcher, "Vesper repairs require a confined launcher")
        if state["active"]:
            if "review" in state["active"]:
                self.review_candidate(provider=reviewer or provider, launcher=launcher, trust_host=trust_host)
                state = self.state()
            else:
                require(state["active"]["provider"] != "manual", "Submit or abandon the active manual attempt first")
                self.finish(state, "interrupted", "Recovered after an interrupted runner", "interrupted")
        while self.ready(state, contract):
            if self.status()["status"] == "blocked":
                break
            job, attempt, workspace, prompt = self.begin(state, contract, provider)
            log = self.attempt_dir(attempt) / "worker.log"
            print(f"{job['id']} | {provider} | attempt {attempt['id'][:8]}", file=sys.stderr, flush=True)

            def record_child(pid):
                attempt["child_pid"] = pid
                self.save(state)

            code = run_process(command, cwd=workspace, input_text=prompt,
                               env=provider_environment(provider, launcher),
                               log=log, timeout=job.get("timeout", 180), on_start=record_child)
            attempt["worker_log"] = str(log.relative_to(self.root))
            if code != 0:
                self.finish(state, "worker_failed", f"Provider exited {code}\n{read_tail(log)}", "provider")
            else:
                result = self.verify(state, contract, job, workspace, launcher)
                if result["outcome"] == "awaiting_review":
                    self.review_candidate(provider=reviewer or provider, launcher=launcher, trust_host=trust_host)
                    state = self.state()
        return self.status()

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
