# Vesper Relay — instructions for Claude

@AGENTS.md

## Current work: the upgrade plan

The ordered upgrade plan lives in `docs/plan/`. Start every session with:

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
python3 -B -m unittest discover -s tests -v
python3 -B examples/replay_repo_fix.py "$(mktemp -d)/repo-pilot"
python3 -B examples/replay_stockroom.py "$(mktemp -d)/build-pilot"
python3 -B examples/replay_repair.py "$(mktemp -d)/repair-pilot"
```

## Hard rules

- The runner stays standard-library Python 3.11+. No third-party imports in
  `vesper.py`, `build_local.py` or `builder/`.
- Never weaken plan digests, scope checks, read-only review copies, independent
  review, or the Git bridge's protection of unrelated edits.
- Never push to `main`, never merge your own PR, never enable `--trust-host` in
  defaults.
