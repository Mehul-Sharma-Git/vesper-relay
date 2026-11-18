#!/usr/bin/env python3
"""Local Builder command-line entry point."""
import argparse
import json
from pathlib import Path
import sys

from builder.brains import ADAPTERS, LEGACY, Selection, legacy
from builder.contracts import BuilderError, read_json, require
from builder.providers import check_launcher
from builder.runner import Runner
from builder.learning import record


def review_limit_options(parser):
    parser.add_argument("--review-timeout", type=int, default=180, metavar="SECONDS",
                        help="Reviewer wall-time limit, 1 to 1800 seconds (default 180)")
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
    commands.add_parser("review")
    commands.add_parser("approve").add_argument("--digest", required=True)
    commands.add_parser("prepare")
    submit = commands.add_parser("submit")
    submit.add_argument("attempt")
    submit.add_argument("--launcher")
    review_candidate = commands.add_parser("review-candidate")
    reviewer_input = review_candidate.add_mutually_exclusive_group()
    reviewer_input.add_argument("--report", type=Path)
    brain_options(review_candidate, group=reviewer_input)
    review_candidate.add_argument("--attest-independent", action="store_true")
    review_boundary = review_candidate.add_mutually_exclusive_group()
    review_boundary.add_argument("--launcher")
    review_boundary.add_argument("--trust-host", action="store_true")
    review_limit_options(review_candidate)
    commands.add_parser("abandon").add_argument("attempt")
    commands.add_parser("retry").add_argument("--reason", required=True)
    commands.add_parser("status")
    commands.add_parser("export").add_argument("destination", type=Path)
    run = commands.add_parser("run")
    brain_options(run, reviewer=True)
    trust = run.add_mutually_exclusive_group()
    trust.add_argument("--launcher")
    trust.add_argument("--trust-host", action="store_true")
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
        elif args.command in {"status", "review"}:
            result = getattr(engine, args.command)()
        else:
            with engine.lock():
                if args.command == "approve":
                    result = engine.approve(args.digest)
                elif args.command == "submit":
                    result = engine.submit(args.attempt, check_launcher(args.launcher))
                elif args.command == "review-candidate":
                    if args.report:
                        require(args.report.stat().st_size <= 256_000, "Review report exceeds the size limit")
                        result = engine.review_candidate(read_json(args.report), external_attested=args.attest_independent)
                    else:
                        brain = Selection(reviewer=chosen(args)).reviewer()
                        result = engine.review_candidate(brain=brain, launcher=check_launcher(args.launcher),
                                                         trust_host=args.trust_host,
                                                         review_timeout=args.review_timeout,
                                                         review_max_turns=args.review_max_turns)
                elif args.command == "abandon":
                    result = engine.abandon(args.attempt)
                elif args.command == "retry":
                    result = engine.retry(args.reason)
                elif args.command == "export":
                    result = engine.export(args.destination.resolve())
                elif args.command == "run":
                    selection = Selection(worker=chosen(args), reviewer=chosen(args, reviewer=True))
                    result = engine.run(selection, check_launcher(args.launcher), trust_host=args.trust_host,
                                        review_timeout=args.review_timeout,
                                        review_max_turns=args.review_max_turns)
                else:
                    result = engine.prepare()
                if args.command in {"submit", "run", "review-candidate"} and (
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
        return int(result.get("outcome") == "rejected" or result.get("status") == "blocked")
    except (BuilderError, OSError, UnicodeError) as exc:
        print(f"builder: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("builder: interrupted. See status for the active attempt.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
