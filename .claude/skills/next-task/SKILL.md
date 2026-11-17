---
name: next-task
description: Do the next upgrade-plan task end to end (branch, tests, PR into dev, review, merge), then stop.
disable-model-invocation: true
---

# Next plan task

Do exactly one task from the status board in `docs/plan/README.md`, end to end, then stop.
The merge rules and the independent review live in README "Branches, PRs and merging";
follow them exactly.

## 1. Sync

1. If you're on a `plan/` branch with uncommitted changes, that is an interrupted task:
   stay on it and go to step 2. Otherwise `git switch dev && git pull --ff-only`.
2. `sh scripts/dev-setup.sh --check`. If it fails, run `sh scripts/dev-setup.sh`.
3. `sh docs/plan/verify-facts.sh`. Handle every DRIFT line as README "When the code has
   changed" says.

Done when the environment is ready and every DRIFT line is explained or handled.

## 2. Pick the task

1. **Look for work in progress:** `plan/*` branches (local and
   `git branch -r --list 'origin/plan/*'`), open PRs into `dev`
   (`gh pr list --base dev --state open`), and `doing` rows on the board.
   - A phase gate (`plan/<id>-g-gate`, or a `-G` row that is `doing`): stop and tell the
     owner to run `/phase-gate`, which resumes it.
   - A plan sync (`plan/sync-*`): stop and tell the owner to run `/plan-sync`, which
     resumes it.
   - A board task (`plan/<id>-<slug>`, ID without `-G`): continue it from where it
     stopped. Read its commits, PR, CI and review comments before acting.
2. Otherwise pick the first `todo` task whose dependencies are all `done`.
3. If that task is a phase gate (ID ends in `-G`), stop and tell the owner to run
   `/phase-gate`.

## 3. Read

Read `docs/plan/00-context.md`, the task's section in its phase file, and every file under
its "Read first". For an L-size task, write out the approach (files, tests, order), then
proceed, unless it conflicts with `00-context.md`; then stop and ask.

## 4. Build

1. `git switch -c plan/<id>-<slug>` (lowercase, e.g. `plan/p1-t1-report-decoding`). Set
   the task to `doing` on the board, commit, and push, so the work can be resumed.
2. Write the failing tests named in "Acceptance". Run them and watch them go red.
3. Implement until they go green, staying inside the files the task names.
4. Run README step 6 (tests and the three replays with `.venv/bin/python3`) plus every
   command in the task's "Acceptance".

Done when every one of those passes. Keep the outputs for the PR.

## 5. Record

- Board: `done`, or `blocked (<reason>)`.
- Tick the task's steps in its phase file under `docs/superpowers/plans/` and
  `docs/plan/superpowers/`.
- `verify-facts.sh`: update any fact this task changed on purpose.
- `appendix-b-test-run-evidence.md`: add any new finding.

## 6. Ship

1. Commit, push, and `gh pr create --base dev`. The body gets what changed, the step-6
   and acceptance outputs, and the approach for L tasks.
2. `gh pr checks <n> --watch`. If it goes red, fix, push, and watch again.
3. Run the independent review from README. Fix blockers, re-run checks, and re-review, at
   most 2 rounds.
4. Merge with `gh pr merge <n> --squash --delete-branch` only when README's three
   conditions hold, then `git switch dev && git pull --ff-only`.

## When the owner is needed

Needs include a password, a login, a Mac dialog, a design choice, an approval, a conflict
with `00-context.md`, or a review still blocked after 2 rounds. First finish everything
that doesn't depend on the owner. Then commit and push the branch, leave the task
`doing`, and stop with exact instructions: what is needed, why, the exact commands or
clicks, and that `/next-task` resumes afterwards.

## Report

End with four lines: what was done, the PR link, the next task ID, and whether that task
needs the owner. Then stop; the next task gets a fresh session.
