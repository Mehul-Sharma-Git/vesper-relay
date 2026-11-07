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

from build_local import initialize
from builder.contracts import BuilderError, fingerprint, inventory, read_json, require
from builder.git_bridge import apply_change, change, repository, seed_repository
from builder.learning import RULES, guidance, memory, promote, record, state_home, summary
from builder.maintenance import MAINTENANCE_GATE
from builder.runner import Runner, atomic_json


ROOT = Path(__file__).resolve().parent
CORE = {"init", "brief", "review", "approve", "prepare", "submit", "abandon", "retry",
        "status", "export", "run"}
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
    mode = "maintenance" if args.command == "maintain" else args.mode
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
    (root / "plan" / "intake.json").write_text(json.dumps(intake, indent=2) + "\n")
    atomic_json(root / ".vesper.json", {"intake": intake, "seed_digest": fingerprint(inventory(root / "seed"))})
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
        elif args.command in {"start", "maintain"}:
            result = start(args)
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
                    result = apply_change(runner, state, meta, args.digest)
                else:
                    patch, result = change(runner, state, meta)
                    if args.command == "patch":
                        sys.stdout.buffer.write(patch)
                        return 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (BuilderError, OSError, UnicodeError, ValueError) as exc:
        print(f"vesper: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
