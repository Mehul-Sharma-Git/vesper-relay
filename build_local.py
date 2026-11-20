#!/usr/bin/env python3
"""Local Builder command-line entry point."""
import argparse
import json
from pathlib import Path
import sys

from builder.brains import ADAPTERS, LEGACY, Selection, legacy, load_settings
from builder.contracts import BuilderError, read_json, require
from builder.providers import check_launcher
from builder.sandbox import BACKENDS, backend
from builder.runner import Runner
from builder.learning import record


def review_limit_options(parser):
    parser.add_argument("--review-timeout", type=int, default=180, metavar="SECONDS",
                        help="Reviewer wall-time limit, 1 to 1800 seconds (default %(default)s)")
    parser.add_argument("--review-max-turns", type=int, default=20, metavar="N",
                        help="Reviewer agent turn limit, 1 to 100 (default 20)")


def brain_options(parser, reviewer=False, group=None):
    """--brain NAME (and --reviewer-brain NAME), each with its deprecated --provider alias."""
    choice = group or parser.add_mutually_exclusive_group()
    choice.add_argument("--brain", metavar="NAME",
                        help="A brain named under [brains] in the config, or an adapter: " + ", ".join(ADAPTERS)
                        + " (default: [roles] in the config)")
    choice.add_argument("--provider", choices=tuple(LEGACY), help="Deprecated alias of --brain")
    if reviewer:
        second = parser.add_mutually_exclusive_group()
        second.add_argument("--reviewer-brain", metavar="NAME",
                            help="The reviewer's brain (default: [roles] reviewer, then the worker's brain)")
        second.add_argument("--reviewer-provider", choices=tuple(LEGACY), help="Deprecated alias of --reviewer-brain")


def chosen(args, reviewer=False):
    """The brain flag's value: a brain name, a Brain from a deprecated alias, or None."""
    prefix = "reviewer_" if reviewer else ""
    provider = getattr(args, prefix + "provider")
    if provider:
        return legacy(provider, "--reviewer-provider" if reviewer else "--provider")
    return getattr(args, prefix + "brain")


def boundary_options(parser, group=None):
    """Where brains and gates run: a sandbox backend, an external launcher, or this machine."""
    choice = group or parser.add_mutually_exclusive_group()
    choice.add_argument("--sandbox", choices=BACKENDS,
                        help="Sandbox backend (default: sandbox.backend in the config, which defaults to docker)")
    choice.add_argument("--launcher", help="An external launcher: absolute path to an executable")
    choice.add_argument("--trust-host", action="store_true", help="No sandbox, the same as --sandbox none (warns)")


def resolve_boundary(args, default=True):
    """(launcher or sandbox backend or None, trust_host). Without a flag the config's backend
    applies when ``default``; otherwise nothing is chosen."""
    if args.launcher:
        return check_launcher(args.launcher), False
    name = "none" if args.trust_host else args.sandbox
    if name is None and default:
        name = load_settings()["sandbox.backend"]
    if name is None:
        return None, False
    engine = backend(name)
    return (engine.check(), False) if engine else (None, True)


def clock_time(value):
    """--start-after HH:MM, checked while parsing, before any sandbox or state is touched."""
    import re
    if not re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value):
        raise argparse.ArgumentTypeError("takes a 24-hour time, for example 07:30")
    return value


def initialize(root, idea):
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise BuilderError("Initialize in an empty directory")
    for name in ("plan", "seed", "checks"):
        (root / name).mkdir()
    (root / "plan" / "idea.md").write_text(idea.strip() + "\n", encoding="utf-8")
    return {"project": str(root), "status": "planning"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("--idea", required=True)
    commands.add_parser("brief")
    commands.add_parser("review").add_argument(
        "--json", action="store_true", help="Print the review bundle as JSON for tools (default: the plan sheet)")
    commands.add_parser("approve").add_argument("--digest", required=True)
    commands.add_parser("prepare")
    submit = commands.add_parser("submit")
    submit.add_argument("attempt")
    boundary_options(submit)
    review_candidate = commands.add_parser("review-candidate")
    reviewer_input = review_candidate.add_mutually_exclusive_group()
    reviewer_input.add_argument("--report", type=Path)
    brain_options(review_candidate, group=reviewer_input)
    review_candidate.add_argument("--attest-independent", action="store_true")
    review_boundary = review_candidate.add_mutually_exclusive_group()
    boundary_options(review_candidate, group=review_boundary)
    review_limit_options(review_candidate)
    commands.add_parser("abandon").add_argument("attempt")
    commands.add_parser("retry").add_argument("--reason", required=True)
    decide = commands.add_parser("decide", help="Decide a finding: send it back, or accept it as a risk")
    decide.add_argument("finding", help="A finding ID from status, for example F3")
    decision = decide.add_mutually_exclusive_group(required=True)
    decision.add_argument("--fix", action="store_true", help="Send the plan back, or give the job another attempt")
    decision.add_argument("--accept-risk", action="store_true", help="Accept it as a risk (you confirm it)")
    decide.add_argument("--reason", help="Why (required with --accept-risk)")
    add_check = commands.add_parser("add-check", help="Add a check after approval (the owner confirms it)")
    add_check.add_argument("--id", required=True, help="The new check's ID, for example G_X")
    gate = add_check.add_mutually_exclusive_group(required=True)
    gate.add_argument("--script", type=Path, help="A Python gate script, copied into the run")
    gate.add_argument("--command", dest="gate_command", help='A command gate, for example "go test ./..."')
    add_check.add_argument("--jobs", help="Comma-separated unfinished jobs that must pass it")
    add_check.add_argument("--reason", help="Why the check is added (shown to the owner and recorded)")
    commands.add_parser("status")
    commands.add_parser("estimate").add_argument("--json", action="store_true", help="Print the estimate as JSON")
    commands.add_parser("export").add_argument("destination", type=Path)
    run = commands.add_parser("run")
    run.add_argument("--start-after", metavar="HH:MM", type=clock_time,
                     help="Wait for this local time first, for example after a plan window resets")
    brain_options(run, reviewer=True)
    boundary_options(run)
    review_limit_options(run)
    args = parser.parse_args()
    root = args.project.resolve()
    engine = Runner(root)
    try:
        if args.command == "init":
            result = initialize(root, args.idea)
        elif args.command == "brief":
            guide = Path(__file__).resolve().parent / "docs" / "PLANNER.md"
            print(f"Project: {root}\nIdea: {root / 'plan' / 'idea.md'}\n\n" + guide.read_text())
            return 0
        elif args.command == "estimate":
            from builder.usage import render
            result = engine.estimate()
            if not args.json:
                print(render(result) if "error" not in result else "Estimate unavailable: " + result["error"])
                return 0
        elif args.command == "review" and not args.json:
            print(engine.review_sheet(), end="")
            return 0
        elif args.command in {"status", "review"}:
            result = getattr(engine, args.command)()
        else:
            with engine.lock():
                if args.command == "approve":
                    result = engine.approve(args.digest)
                elif args.command == "submit":
                    # Supervised gates run sandboxed too: the config's backend unless a flag chooses.
                    result = engine.submit(args.attempt, resolve_boundary(args)[0])
                elif args.command == "review-candidate":
                    if args.report:
                        require(args.report.stat().st_size <= 256_000, "Review report exceeds the size limit")
                        result = engine.review_candidate(read_json(args.report), external_attested=args.attest_independent)
                    else:
                        brain = Selection(reviewer=chosen(args)).reviewer()
                        launcher, trust_host = resolve_boundary(args)
                        result = engine.review_candidate(brain=brain, launcher=launcher, trust_host=trust_host,
                                                         review_timeout=args.review_timeout,
                                                         review_max_turns=args.review_max_turns)
                elif args.command == "abandon":
                    result = engine.abandon(args.attempt)
                elif args.command == "retry":
                    result = engine.retry(args.reason)
                elif args.command == "decide":
                    result = engine.decide(args.finding, fix=args.fix, accept=args.accept_risk, reason=args.reason)
                elif args.command == "add-check":
                    result = engine.add_check(args.id, script=args.script, command=args.gate_command,
                                              jobs=args.jobs.split(",") if args.jobs is not None else None,
                                              reason=args.reason)
                elif args.command == "export":
                    result = engine.export(args.destination.resolve())
                elif args.command == "run":
                    selection = Selection(worker=chosen(args), reviewer=chosen(args, reviewer=True))
                    launcher, trust_host = resolve_boundary(args)
                    result = engine.run(selection, launcher, trust_host=trust_host,
                                        review_timeout=args.review_timeout,
                                        review_max_turns=args.review_max_turns, start_after=args.start_after)
                else:
                    result = engine.prepare()
                if args.command in {"submit", "run", "review-candidate", "decide"} and (
                    result.get("status") == "complete" or result.get("outcome") == "accepted"
                ):
                    state = engine.state()
                    if ("intake" in state["bundle"]
                            and engine.status()["status"] == "complete"):
                        try:
                            result["learning"] = record(engine)
                        except (BuilderError, OSError, ValueError) as exc:
                            print(f"vesper: change verified, but learning could not be recorded: {exc}",
                                  file=sys.stderr)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result.get("status") == "paused_for_limits":
            pause = result["pause"]
            print(f"builder: paused before {pause['job']}: {pause['account']} {pause['limit']} usage would reach "
                  f"{pause['projected']}% (limit {pause['threshold']}% with your reserve); {pause['resume']}.",
                  file=sys.stderr)
            return 3
        if "awaiting_decision" in (result.get("outcome"), result.get("status")):
            print("builder: waiting for the owner's decision on " + ", ".join(result.get("awaiting_decision") or
                  engine.status().get("awaiting_decision", [])) + ": run decide FINDING_ID --fix, or "
                  '--accept-risk --reason "..." (status lists each finding)', file=sys.stderr)
        return int(result.get("outcome") in ("rejected", "awaiting_decision")
                   or result.get("status") in ("blocked", "awaiting_decision"))
    except (BuilderError, OSError, UnicodeError) as exc:
        print(f"builder: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("builder: interrupted. See status for the active attempt.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
