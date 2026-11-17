---
name: plan-sync
description: Bring the upgrade plan up to date with commits made outside it, then PR and merge into dev.
disable-model-invocation: true
---

# Plan sync

Make the plan match the code after commits made outside the plan (the owner's own fixes
or features). Those commits are the owner's decisions: the plan adopts them. Merging
follows README "Branches, PRs and merging".

## 1. Find the commits

1. `git switch dev && git pull --ff-only`, then `sh scripts/dev-setup.sh --check` (run
   `sh scripts/dev-setup.sh` if it fails).
2. Read the "Last plan sync" commit in `docs/plan/README.md` (call it `LAST`).
3. List the candidate commits: `git log --reverse --format='%h %s' LAST..origin/dev`, plus
   any commits on `main` that `dev` lacks: `git log --no-merges origin/dev..origin/main`.
4. Drop the plan's own work: squash merges of PRs whose head branch starts with `plan/`
   (`gh pr list --base dev --state merged --limit 200 --json number,headRefName,mergeCommit`).
   What remains is outside the plan. If nothing remains, update only the "Last plan sync"
   line and still ship it (step 4).

## 2. Analyse

For every remaining commit, read its message and full diff. Map it to plan effects: tasks
it completes, shrinks, changes or makes obsolete; facts in `verify-facts.sh`; fixtures;
owner decisions in `00-context.md`; new gaps.

Then run README step 6 (tests and the three replays with `.venv/bin/python3`) and
`sh docs/plan/verify-facts.sh`, and keep the outputs. Done when every commit has a
written effect, even "none".

## 3. Update the plan

1. `git switch -c plan/sync-<newest short sha>`. If `main` had commits `dev` lacks, merge
   `origin/main` into this branch.
2. Update the phase files, `00-context.md`, fixtures and `verify-facts.sh` so the plan
   matches the code. Follow README "When the code has changed": adapt task text to the
   code, keep each task's intent, and set a task `done` only when a commit fully meets its
   "Acceptance". Note the commit in either case.
3. In `appendix-b-test-run-evidence.md`, add a section like section 4: one row per commit
   and its effect on the plan.
4. Set "Last plan sync" in `docs/plan/README.md` to the newest analysed commit and today's
   date.
5. Re-run `sh docs/plan/verify-facts.sh`. Done when it reports no DRIFT, other than DRIFT
   on `done` tasks.

If a commit contradicts an owner decision in `00-context.md` and the right reading is
unclear, stop and ask the owner which wins.

## 4. Summarise and ship

1. Write the owner a summary: each commit, what changed in the plan, and why.
2. PR into `dev` with that summary and the step-6 outputs, then CI, independent review
   (the synced commits and this summary are the spec), and merge, as README says. If this
   branch merged `origin/main`, merge the PR with `gh pr merge <n> --merge --delete-branch`
   instead of `--squash`, so those `main` commits become part of `dev`'s history and the
   next sync doesn't list them again.
3. End with the summary and the PR link.
