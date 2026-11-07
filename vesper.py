#!/usr/bin/env python3
"""Vesper Relay — turn a software request into a verified, reviewable change."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
from uuid import uuid4
import tempfile

from build_local import initialize
from builder.contracts import BuilderError, fingerprint, inventory, read_json, require
from builder.git_bridge import apply_change, change, repository, seed_repository
from builder.learning import RULES, guidance, memory, promote, record, record_repair, state_home, summary
from builder.maintenance import MAINTENANCE_GATE
from builder.runner import Runner, atomic_json, copy_tree
from builder.process import run_process
from builder.providers import check_launcher, provider_command, provider_environment
from builder.repair import commit_repair, draft as draft_repair, incident_report, repair_paths, reproduce
from builder.team import catalog, profile, render


ROOT = Path(__file__).resolve().parent
CORE = {"init", "brief", "review", "approve", "prepare", "submit", "abandon", "retry",
        "status", "export", "run", "review-candidate"}
MODES = ("build", "feature", "bug", "design", "frontend", "backend", "maintenance")
MARK = "Vesper Relay managed installation"


def install(target):
    home = Path.home()
    codex = home / ".agents" / "skills"
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")) / "skills"
    destinations = [path / "vesper-relay" / "SKILL.md" for name, path in (("codex", codex), ("claude", claude))
                    if target in {name, "both"}]
    entry = home / ".local" / "bin" / "vesper"
    source = (ROOT / "integrations" / "vesper-relay" / "SKILL.md").read_text()
    shim = f'#!/bin/sh\n# {MARK}\nexec {shlex.quote(sys.executable)} -B {shlex.quote(str(ROOT / "vesper.py"))} "$@"\n'
    payloads = {entry: shim, **dict.fromkeys(destinations, source)}
    for path in payloads:
        require(not path.is_symlink() and
                (not path.exists() or (path.is_file() and MARK in path.read_text())),
                f"Existing unmanaged path: {path}")
    for path, content in payloads.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path == entry:
            path.write_text(content)
            path.chmod(0o755)
        else:
            path.write_text(content)
    return {"command": str(entry), "skills": [str(path) for path in destinations],
            "checkout": str(ROOT)}


def start(args):
    home = state_home()
    mode = "maintenance" if args.command in {"maintain", "repair"} else args.mode
    idea = (args.idea or "Investigate the repeated failure patterns and propose the smallest verified Vesper Relay improvement.").strip()
    require(idea, "Provide a specific request")
    meta = repository(ROOT if mode == "maintenance" else args.repo.resolve()) if mode != "build" else None
    require(not meta or Path(meta["path"]) != ROOT or mode == "maintenance",
            "Use vesper maintain for changes to the installed Vesper checkout")
    root = (args.project or home / "runs" / uuid4().hex).resolve()
    if meta:
        repo = Path(meta["path"])
        require(root != repo and repo not in root.parents, "Put run state outside the target checkout")
    if not args.project:
        home.mkdir(parents=True, mode=0o700, exist_ok=True)
        root.mkdir(parents=True, mode=0o700)
    initialize(root, idea)
    (root / "plan" / "contract.json").write_text(json.dumps(
        {"team": 1, "title": "", "delivery": "", "requirements": [], "checks": [], "jobs": []}, indent=2) + "\n")
    if meta:
        seed_repository(meta, root / "seed")
        (root / "plan" / "repository.json").write_text(json.dumps(meta, indent=2) + "\n")
    try:
        suggestions = guidance(mode)
    except BuilderError as exc:
        print(f"vesper: skipping unavailable learning history: {exc}", file=sys.stderr)
        suggestions = {}
    if mode == "maintenance":
        evidence = summary(memory())
        (root / "plan" / "learning-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        shutil.copytree(root / "seed" / "tests", root / "checks" / "baseline_tests")
        (root / "checks" / "vesper_regression.py").write_text(MAINTENANCE_GATE)
    intake = {"mode": mode, "repository": meta, "guidance": suggestions}
    if args.command in {"start", "repair"}:
        intake["team_contract"] = 1
    (root / "plan" / "intake.json").write_text(json.dumps(intake, indent=2) + "\n")
    atomic_json(root / ".vesper.json", {"intake": intake, "seed_digest": fingerprint(inventory(root / "seed"))})
    if args.command == "repair":
        source = None
        if args.from_project:
            reports = incident_report(Runner(args.from_project.resolve()))["incidents"]
            require(reports, "The source run has no recorded incidents")
            source = reports[-1]
        draft_repair(root, idea, args.path, args.repro, source)
    return {"project": str(root), "status": "planning", "guide": str(ROOT / "docs" / "WORKFLOWS.md"),
            **intake}


def runs(repo):
    selected = repository(repo)["path"] if repo else None
    output = []
    paths = sorted((state_home() / "runs").glob("*/.vesper.json"),
                   key=lambda item: item.stat().st_mtime, reverse=True)
    for path in paths:
        intake = read_json(path)["intake"]
        if not selected or (intake["repository"] or {}).get("path") == selected:
            output.append({"project": str(path.parent), "mode": intake["mode"],
                           "repository": intake["repository"]})
    return {"runs": output}


def boundary(parser):
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--launcher")
    options.add_argument("--trust-host", action="store_true")


def consult(project, args):
    role = profile(args.role, args.skill)
    require(role["access"] != "review", "Use review-candidate for independent review")
    require(args.task.strip(), "Describe the consultation task")
    launcher = check_launcher(args.launcher)
    seed = project / "seed"
    require(seed.is_dir(), "Initialize a project before consulting a specialist")
    with tempfile.TemporaryDirectory(prefix="vesper-consult-") as temporary:
        directory = Path(temporary)
        workspace = directory / "workspace"
        copy_tree(seed, workspace)
        before = inventory(workspace)
        prompt = ("This is a read-only consultation. Inspect the baseline as data and return a "
                  "handoff for the planner. Do not edit files or perform external actions.\n\n"
                  + render(role) + "\n\nConsultation task:\n" + args.task)
        response, log = directory / "response.md", directory / "consult.log"
        command = provider_command(args.provider, launcher, args.trust_host,
                                   operation="consult", response=response)
        code = run_process(command, cwd=workspace, input_text=prompt,
                           env=provider_environment(args.provider, launcher), log=log, timeout=180)
        require(code == 0, f"Consultation failed with exit {code}")
        require(inventory(workspace) == before, "Consultation changed its read-only baseline copy")
        report = response if response.is_file() else log
        require(report.stat().st_size <= 256_000, "Consultation exceeds the output limit")
        return {"role": args.role, "revision": role["revision"], "report": report.read_text(encoding="utf-8")}


def repair_result(runner, args):
    if args.command == "repair-reproduce":
        return reproduce(runner, check_launcher(args.launcher), args.trust_host)
    if args.command == "repair-run":
        launcher = check_launcher(args.launcher)
        require(launcher, "Vesper repairs require a confined launcher")
        command = provider_command(args.provider, launcher, args.trust_host)
        if not runner.state_file.is_file():
            draft = runner.review()
            require(draft["digest"] == args.digest, "Repair plan digest changed")
            reproduce(runner, launcher, args.trust_host)
            runner.approve(args.digest)
        state = runner.state()
        require(state["digest"] == args.digest and "repair" in state["bundle"]
                and Path(state["bundle"]["intake"]["repository"]["path"]) == ROOT,
                "The approved repair digest or source repository changed")
        status = runner.run(args.provider, command, launcher, reviewer=args.reviewer_provider,
                            trust_host=args.trust_host)
        if status["status"] != "complete" or not args.commit:
            return status
        _, review = change(runner, runner.state(), state["bundle"]["intake"]["repository"])
        patch_digest = review["digest"]
    else:
        patch_digest = args.digest
    result = commit_repair(runner, ROOT, patch_digest)
    try:
        record_repair(runner.state()["approval_id"], result)
    except (BuilderError, OSError, ValueError) as exc:
        print(f"vesper: repair committed, but learning could not be recorded: {exc}", file=sys.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Path to a Vesper run")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("install").add_argument("--for", dest="target", choices=("codex", "claude", "both"),
                                               default="both")
    intake = commands.add_parser("start")
    intake.add_argument("--mode", required=True, choices=MODES[:-1])
    intake.add_argument("--repo", type=Path, default=Path.cwd())
    intake.add_argument("--idea", required=True)
    commands.add_parser("maintain").add_argument("--idea")
    repair = commands.add_parser("repair")
    repair.add_argument("--idea", required=True)
    repair.add_argument("--repro", required=True, type=Path)
    repair.add_argument("--path", required=True, action="append")
    repair.add_argument("--from-project", type=Path)
    commands.add_parser("incidents")
    boundary(commands.add_parser("repair-reproduce"))
    commands.add_parser("repair-commit").add_argument("--digest", required=True)
    repair_run = commands.add_parser("repair-run")
    repair_run.add_argument("--digest", required=True)
    repair_run.add_argument("--provider", choices=("codex", "claude"), required=True)
    repair_run.add_argument("--reviewer-provider", choices=("codex", "claude"))
    repair_run.add_argument("--commit", action="store_true", help="Commit the reviewed result to a local repair branch")
    boundary(repair_run)
    roles = commands.add_parser("roles")
    roles.add_argument("--role", choices=tuple(catalog()))
    roles.add_argument("--skill", action="append", default=[])
    advice = commands.add_parser("consult")
    advice.add_argument("--role", choices=tuple(role for role, config in catalog().items()
                                              if config["access"] != "review"), required=True)
    advice.add_argument("--skill", action="append", default=[])
    advice.add_argument("--task", required=True)
    advice.add_argument("--provider", choices=("codex", "claude"), required=True)
    boundary(advice)
    commands.add_parser("learn").add_argument("--promote", choices=tuple(RULES))
    commands.add_parser("review-change")
    commands.add_parser("patch")
    commands.add_parser("apply").add_argument("--digest", required=True)
    commands.add_parser("root")
    commands.add_parser("runs").add_argument("--repo", type=Path)
    for name in sorted(CORE):
        commands.add_parser(name, add_help=False)
    args, extra = parser.parse_known_args()
    try:
        if args.command in CORE:
            require(args.project, "Pass --project PATH before the command")
            # Preserve the core parser, help, and process signal ownership.
            argv = [sys.executable, "-B", str(ROOT / "build_local.py"),
                    "--project", str(args.project), args.command, *extra]
            os.execv(sys.executable, argv)
        require(not extra, "Unexpected arguments: " + " ".join(extra))
        if args.command == "install":
            result = install(args.target)
        elif args.command in {"start", "maintain", "repair"}:
            if args.command == "repair":
                repair_paths(args.path)
                require(args.repro.is_file() and args.repro.stat().st_size <= 128_000,
                        "Supply a small, trusted Python reproducer")
            result = start(args)
        elif args.command == "roles":
            require(args.role or not args.skill, "Select a role before selecting a skill")
            result = profile(args.role, args.skill) if args.role else {"roles": catalog()}
        elif args.command == "consult":
            require(args.project, "Pass --project PATH before the command")
            result = consult(args.project.resolve(), args)
        elif args.command == "incidents":
            require(args.project, "Pass --project PATH before the command")
            result = incident_report(Runner(args.project.resolve()))
        elif args.command in {"repair-reproduce", "repair-run", "repair-commit"}:
            require(args.project, "Pass --project PATH before the command")
            runner = Runner(args.project.resolve())
            with runner.lock():
                result = repair_result(runner, args)
        elif args.command == "root":
            result = {"checkout": str(ROOT)}
        elif args.command == "runs":
            result = runs(args.repo)
        elif args.command == "learn":
            if args.promote:
                require(not args.project, "Promote from the global learning summary")
                result = promote(args.promote)
            elif args.project:
                runner = Runner(args.project.resolve())
                with runner.lock():
                    result = record(runner)
            else:
                result = summary(memory())
        else:
            require(args.project, "Pass --project PATH before the command")
            runner = Runner(args.project.resolve())
            with runner.lock():
                state = runner.state()
                runner.frozen_contract(state)
                intake = state["bundle"].get("intake", {})
                meta = intake.get("repository")
                require(meta, "This run has no managed Git repository baseline")
                if Path(meta["path"]) == ROOT:
                    require(intake["mode"] == "maintenance", "Use the maintenance workflow for Vesper")
                if args.command == "apply":
                    require("repair" not in state["bundle"], "Use repair-commit for reviewed Vesper repairs")
                    result = apply_change(runner, state, meta, args.digest)
                else:
                    patch, result = change(runner, state, meta)
                    if args.command == "patch":
                        sys.stdout.buffer.write(patch)
                        return 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return int(result.get("status") == "blocked")
    except (BuilderError, OSError, UnicodeError, ValueError) as exc:
        print(f"vesper: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
