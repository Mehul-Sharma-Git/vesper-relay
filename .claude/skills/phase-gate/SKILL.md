---
name: phase-gate
description: Run the next phase gate, record the results, and open the dev → main PR for the owner to merge.
disable-model-invocation: true
---

# Phase gate

Run one phase gate from the status board in `docs/plan/README.md`, record the result, and
hand `main` to the owner. Merging into `dev` follows README "Branches, PRs and merging".
`main` is the owner's: open the PR, never merge it.

## 1. Sync and pick the gate

1. If a `plan/<gate-id>-gate` branch or open PR exists, resume it. Otherwise
   `git switch dev && git pull --ff-only`, then check that the last gate run was handed
   over: take the last `## Gate ` heading in `docs/plan/appendix-b-test-run-evidence.md`.
   If no `dev` → `main` PR in any state has that exact line in its body
   (`gh pr list --base main --head dev --state all --limit 100 --json number,body`), that
   run stopped before handing over `main`: go straight to section 4.
2. `sh scripts/dev-setup.sh --check` (run `sh scripts/dev-setup.sh` if it fails), then
   `sh docs/plan/verify-facts.sh`.
3. The gate is the first `-G` row that isn't `done`. Check every task it depends on is
   `done`. If any isn't, stop and list them: the owner runs `/next-task` first.

## 2. Run the gate

1. `git switch -c plan/<gate-id>-gate` (e.g. `plan/p1-g-gate`), set the gate to `doing`,
   commit, and push.
2. Ask the owner to run `/usage` and paste the session and weekly figures. Note the start
   time.
3. Find the procedure: the gate's own section (e.g. "P1-G — Phase 1 gate") or the
   "Phase gate (Pn-G)" paragraph at the top of the phase file. Run every step you can.
4. For each step only the owner can do (an approval, a Mac dialog, a login, a design pick
   or rating), pause with exact instructions: the command or click, what they will see,
   and what to reply with. Continue when they reply. If the session ends first,
   `/phase-gate` resumes from the branch.
5. At the end, ask for `/usage` again and note the end time.

Done when every pass criterion has a measured result: pass or fail, with evidence.

## 3. Record

1. In `docs/plan/appendix-b-test-run-evidence.md`, add a section for this run headed
   `## Gate <gate-id> — <YYYY-MM-DD HH:MM>` (the start time, so every run's heading is
   unique; section 1 and 4 checks match this exact line). Include: the commit tested, each criterion with its result and evidence, elapsed time, and plan
   usage before and after.
2. Set the gate's board status: `done` if every criterion passed, else
   `blocked (<failed criteria>)` with the follow-up you recommend.
3. PR into `dev`, CI, independent review (the gate's section is the spec), and merge, as
   README says.

## 4. Hand over main

Whatever the result, deliver this run's report section from appendix B, starting with
its `## Gate ` heading line unchanged, in a `dev` → `main` PR:

- If one is already open (`gh pr list --base main --head dev --state open`), update it
  with `gh pr edit`: add `<gate-id> PASSED|FAILED` to its title and append the report to
  its body.
- Otherwise run
  `gh pr create --base main --head dev --title "<gate-id> PASSED|FAILED — <one line>"`
  with the report as the body.

Don't merge it.

End by telling the owner: the gate result, the `dev` → `main` PR link, and to review and
merge it with "Create a merge commit" (see `docs/plan/GETTING-STARTED.md`). If the gate
failed, also give the failed criteria and the recommended next step. Whether to merge a
failed gate is the owner's call.
