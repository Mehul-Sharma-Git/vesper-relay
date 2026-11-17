# Vesper Relay — instructions for Claude

@AGENTS.md

## Environment

At the start of every session, if .venv/bin/python3 is missing or sh scripts/dev-setup.sh --check fails, run sh scripts/dev-setup.sh before anything else.

## Current work: the upgrade plan

The ordered upgrade plan lives in `docs/plan/`. The owner drives it with three project
commands: `/next-task` (one board task, end to end), `/phase-gate` (run a phase gate and
open the `dev` → `main` PR) and `/plan-sync` (bring the plan up to date with commits made
outside it). The owner's guide is `docs/plan/GETTING-STARTED.md`.

Start every session with:

1. `docs/plan/README.md` (rules and the status board)
2. `docs/plan/00-context.md` (background and every owner decision)
3. The phase file that holds the task you are asked to do

Before the task, run `sh docs/plan/verify-facts.sh` and follow README's "When the code
has changed" for any DRIFT line. Work on exactly one task per session, on its own branch,
tests first. Follow the
"Read first", "Change", "Do not" and "Acceptance" parts of the task literally.
Update the status board in the same change. If a task is unclear or conflicts with
`00-context.md`, stop and ask instead of guessing.

## Commands

```sh
.venv/bin/python3 -B -m unittest discover -s tests -v
.venv/bin/python3 -B examples/replay_repo_fix.py "$(mktemp -d)/repo-pilot"
.venv/bin/python3 -B examples/replay_stockroom.py "$(mktemp -d)/build-pilot"
.venv/bin/python3 -B examples/replay_repair.py "$(mktemp -d)/repair-pilot"
```

## Branches, PRs and merging

- Branch every task from an up-to-date `dev` (`git switch dev && git pull`), and open
  every PR into `dev`.
- Merge into `dev` yourself only when all three are true:
  1. every README step-6 check passes locally;
  2. the PR's CI is green (`gh pr checks <n> --watch`);
  3. an independent review passes (below).

  Then run `gh pr merge <n> --squash --delete-branch`.
- **Independent review:** launch a fresh-context subagent (not a fork of this session)
  that reads only the PR diff (`gh pr diff <n>`), the task's section in its phase file,
  and `docs/plan/00-context.md`, and reports blockers with evidence (file, line, and the
  failing input or broken rule). Fix the blockers and re-review, at most 2 rounds. If it
  is still blocked, stop and ask the owner. The reviewer prompt is in
  `docs/plan/README.md`, "Branches, PRs and merging".
- Never push to or merge into `main`. At each phase gate, open a `dev` → `main` PR with
  the gate results; only the owner merges it.

## Hard rules

- The runner stays standard-library Python 3.11+. No third-party imports in
  `vesper.py`, `build_local.py` or `builder/`.
- Never weaken plan digests, scope checks, read-only review copies, independent
  review, or the Git bridge's protection of unrelated edits.
- Never enable `--trust-host` in defaults.
