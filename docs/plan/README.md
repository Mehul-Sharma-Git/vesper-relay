# Vesper Relay upgrade plan

This folder is the complete, ordered plan for upgrading Vesper Relay. It is written so
that an AI coding assistant (Claude Code, Codex or any other) can implement it one task at a time,
with no access to the conversations that produced it. Everything needed is in these files.

Drop this folder into the repository as `docs/plan/` and copy `CLAUDE.md` to the
repository root (merge it with an existing `CLAUDE.md` if there is one).

**Owner:** start with [GETTING-STARTED.md](GETTING-STARTED.md). The daily loop is `/clear`,
then `/next-task`.

## Files, in reading order

| File | What it holds | Read when |
| --- | --- | --- |
| `GETTING-STARTED.md` | The owner's guide: setup, `/next-task`, `/phase-gate`, `/plan-sync`, when you're needed | Owner, first |
| `README.md` | How to work through the plan, drift handling, rules, status board | Every session |
| `verify-facts.sh` | Checks the code facts the tasks rely on are still true | Every session |
| `superpowers/` | The same tasks as Superpowers `executing-plans` files, one per phase | When using Superpowers |
| `00-context.md` | What Vesper is, what was learned, every owner decision | Every session |
| `phase-1-reliable-runs.md` | Reviewer bug, any-language gates, toolchains, config, any-AI brain adapters, pluggable sandbox, setup wizard | Phase 1 |
| `phase-2-evidence-and-control.md` | Evidence to reviewers, human-only approvals, plan-limit tracking, plan validation | Phase 2 |
| `phase-3-verifying-agents.md` | Shared agent foundation, knowledge packs, QA and reviewer upgrades | Phase 3 |
| `phase-4-building-agents.md` | Designer (top priority), frontend, backend, planner, tech lead | Phase 4 |
| `phase-5-doors-repair-release.md` | Connector, packaging, automatic repair loop, bench, v1.0 release | Phase 5 |
| `SETUP-draft.md` | Draft user setup guide (Mac first; every door); becomes `docs/SETUP.md` in P5-T6 | Phase 1 setup tasks, P5-T6 |
| `archive/discussion-log.md` | The raw decision log and research notes these files were built from. Historical; the plan files win on any conflict | Rarely |
| `appendix-a-research.md` | Design libraries, hosting limits, Claude plan limits, sources | When a task links to it |
| `appendix-b-test-run-evidence.md` | Findings from the live Pocket Todo run | When a task links to it |
| `appendix-c-future-assistant.md` | The longer-term "personal assistant" direction. Do NOT implement yet | Only for context |
| `fixtures/pocket-todo/` | The real approved plan, gates and wireframes from the test run | Phase 1 acceptance, tests |
| `assets/wireframes/` | The wireframe generator used in the test run | Phase 4 designer tasks |

## How to work through the plan

1. **One task per session.** Pick the first task on the status board that is `todo`
   and whose dependencies are `done`. Do not start a second task in the same session.
   Run the drift check below first.
2. **Read before writing.** Read `00-context.md`, the task, and every file the task
   lists under "Read first".
3. **Branch per task.** From an up-to-date `dev` (`git switch dev && git pull`):
   `git switch -c plan/<task-id>-<short-name>`. Set the task to `doing` on the board.
4. **Tests first.** Write the failing test named in "Acceptance", watch it fail,
   then implement.
5. **Stay in scope.** Change only the files the task names, plus tests. If another file
   must change, stop and say why before touching it.
6. **Verify.** Run, and paste the results into the PR description:
   ```sh
   .venv/bin/python3 -B -m unittest discover -s tests -v
   .venv/bin/python3 -B examples/replay_repo_fix.py "$(mktemp -d)/repo-pilot"
   .venv/bin/python3 -B examples/replay_stockroom.py "$(mktemp -d)/build-pilot"
   .venv/bin/python3 -B examples/replay_repair.py "$(mktemp -d)/repair-pilot"
   ```
   plus any extra command in the task's "Acceptance".
7. **Update this board.** Set the task to `done` (or `blocked` with a reason) in the
   same PR. Add any new finding to `appendix-b-test-run-evidence.md`.
8. **PR and merge into `dev`.** Open the PR into `dev` with the step-6 results, then merge
   it yourself only as "Branches, PRs and merging" below allows.
9. **Stop and ask** when a task is ambiguous, when a decision in `00-context.md` seems
   wrong, or when finishing would need more than the task allows. Never guess on
   security, licensing, or anything the owner decided.

## Branches, PRs and merging

`dev` is the default branch and holds all plan work. `main` changes only at phase gates,
and only the owner merges into it.

- Branch every task from an up-to-date `dev`, and open every PR into `dev`.
- Merge into `dev` yourself only when all three are true:
  1. every step-6 check passes locally;
  2. the PR's CI is green: every check in `gh pr checks <n>` passes, except that
     `verify (macos-latest)` counts only when it actually ran (see "CI and macOS" below);
  3. an independent review passes.

  Then run `gh pr merge <n> --squash --delete-branch` (`--merge` only for a `/plan-sync`
  PR that merged `main` in; see that skill).
- **Independent review:** launch a fresh-context subagent (not a fork of the working
  session) that reads only the PR diff (`gh pr diff <n>`), the task's section in its phase
  file, and `00-context.md`, and reports blockers with evidence (file, line, and the
  failing input or broken rule). Fix the blockers and re-review, at most 2 rounds. If it
  is still blocked, stop and ask the owner. For a PR with no board task (`/plan-sync`,
  housekeeping), the reviewer gets the written request or the synced commits in place of
  the task section. Reviewer prompt:

  > You are reviewing PR #N in this repository. Read only: `gh pr diff N`, the section
  > `<task id>` in `docs/plan/<phase file>`, and `docs/plan/00-context.md`. Report only
  > blockers: a bug, an unmet "Change" or "Acceptance" item, a "Do not" broken, or an
  > owner decision in `00-context.md` contradicted. For each, give file:line and the
  > evidence (the input that fails, or the rule quoted). End with `VERDICT: APPROVE` if
  > there are none, else `VERDICT: BLOCK`.

  The review passes on `VERDICT: APPROVE`. Record each round's verdict in the PR as a
  comment.
- **CI and macOS:** the step-6 checks run locally on the owner's Mac, so they cover
  macOS. GitHub's macOS runners are often unavailable, so `verify (macos-latest)` counts
  only when it actually ran:
  - It passed: fine.
  - It ran and a test failed: CI is red. Read the log and fix it.
  - It is still queued, or ended `cancelled` or failed with no steps run (no runner;
    check with `gh run view <run> --json jobs`): ignore it and say so in the PR.

  Wait for the other checks, not for a queued macOS job: `gh pr checks <n> --watch` can
  sit 15 minutes on one.
- Never push to or merge into `main`. At each phase gate, `/phase-gate` opens a
  `dev` → `main` PR with the gate results; only the owner merges it.

## When the code has changed

This plan was written against commit `9d3b223` (2026-11-09) and updated for `b7da4d1`
(2026-11-17); `verify-facts.sh` checks against `b7da4d1`. The code may change before or
between tasks: a small fix by hand, an earlier task, or a merged repair. Tasks describe
**intent first** ("Why"), then specifics, so small changes don't break them. Handle drift
this way:

1. **Every session, before starting a task:** run `sh docs/plan/verify-facts.sh` and
   `git log --oneline b7da4d1..HEAD -- <files in the task's "Read first">`.
2. **DRIFT on a task already `done`** is expected: that task changed the code on purpose.
3. **The code moved, but the intent still applies** (a function renamed, a value already
   configurable, a file split): adapt the task to the current code, and update the task
   text and `verify-facts.sh` in the same PR so the plan stays true.
4. **Someone already did part of the task:** do only the missing part; mark what was
   already done in the PR description.
5. **The change conflicts with a decision in `00-context.md`** (for example, it removes a
   safety check or hard-wires one AI vendor): stop and ask the owner. Never silently
   follow either the plan or the code.
6. **A manual change outside the plan:** add a line to `appendix-b-test-run-evidence.md`
   section 3 or a new task on the board, so the plan keeps matching reality. For several
   such commits, run `/plan-sync`.

**Last plan sync:** `b7da4d1` (2026-11-17). Always a commit on `dev`. `/plan-sync` analyses
what landed on `dev` after it (first-parent), plus `main` commits `dev` lacks, skipping
merges of PRs whose head branch starts with `plan/` (the plan's own work). It sets this
line to the `dev` tip it analysed.

## Using Superpowers

The repo already uses the Superpowers `executing-plans` workflow (`docs/superpowers/plans/`).
`superpowers/` holds one Superpowers-format plan per phase, mirroring the status board with
checkbox steps. P0-T1 copies them to `docs/superpowers/plans/`. With Superpowers, run
"Use superpowers:executing-plans on docs/superpowers/plans/2026-11-17-vesper-upgrade-phase-1.md"
and it will still do one task at a time. The phase files in `docs/plan/` stay the spec, and
this status board stays the task-level source of truth: update both in the same PR.
Without Superpowers, follow "How to work through the plan" above; the result is the same.

## Non-negotiable rules

- The runner (`vesper.py`, `build_local.py`, `builder/`) stays **Python 3.11+ standard
  library only**. Projects Vesper *builds* may use Go, Node, React and so on; Vesper
  itself does not import third-party packages.
- Never push to or merge into `main`; merge into `dev` only as "Branches, PRs and
  merging" allows.
- Never weaken an existing safety property: plan digests, scope checks, read-only
  review copies, the Git bridge preserving unrelated edits, independent review.
- Keep `AGENTS.md` rules: worker code stays separate from accepted snapshots,
  learning and gate files; no broadened permissions; no auto-applied self-edits.
- Every new behaviour gets a test in `tests/`. Every new CLI command gets a line in
  `docs/USAGE.md`.
- Use only MIT or similarly permissive material from outside sources, with attribution
  in the file that uses it. Check `appendix-a-research.md` for known licences.

## Status board

Status values: `todo`, `doing`, `done`, `blocked (reason)`.
Size: S fits easily in one Claude Pro session, M fills one, L may need two (split if so).

| ID | Task | Depends on | Size | Status |
| --- | --- | --- | --- | --- |
| P0-T1 | Add plan folder and CLAUDE.md, confirm baseline is green | none | S | done |
| P1-T1 | Robust reviewer report decoding | P0-T1 | S | done |
| P1-T2 | Structured reviewer output (schema flags) | P1-T1 | S | done |
| P1-T3 | Configurable gate and reviewer limits | P0-T1 | S | done |
| P1-T4 | Gate environment pass-through | P0-T1 | S | done |
| P1-T5 | Command gates (any language) | P1-T3 | M | done |
| P1-T6 | Toolchain support: setup step and ignored build dirs | P1-T5 | L | done |
| P1-T7 | Config files: personal + project, `config show` | P0-T1 | M | done |
| P1-T8 | Brain adapter interface: Claude Code, Codex, Gemini CLI | P1-T2, P1-T7 | L | done |
| P1-T9 | Pluggable sandbox: Docker and Podman backends, selftest | P1-T5, P1-T8 | L | done |
| P1-T10 | Worker tool layer (shell only inside the sandbox) | P1-T9 | M | done |
| P1-T11 | `vesper setup` wizard and `vesper doctor` | P1-T9 | M | done |
| P1-G | Phase 1 gate: Pocket Todo unattended in the sandbox with one AI | P1-T1..T11 | M | done |
| P2-T1 | Gate logs, scripts and artifacts in the review copy | P1-G | S | done |
| P2-T2 | Human-only approvals and a plain-language approval sheet, in every door | P1-G | L | done |
| P2-T3 | Usage ledger and plan-limit estimates | P1-G | M | done |
| P2-T4 | Limit-aware scheduling (pause and resume) | P2-T3 | M | done |
| P2-T5 | Required plan sections by depth (extend `planning.json`) | P1-G | M | done |
| P2-T6 | Additive checks after approval | P1-G, P2-T2 | M | done |
| P2-T7 | Advisory backlog and decision gate (advisories and blockers) | P1-G, P2-T2 | L | done |
| P2-T8 | Review the code a change touches (P2-G finding 53) | P2-T7 | M | done |
| P2-T9 | Estimates you can check: marked readings and `usage check` (P2-G finding 54) | P2-T3 | M | done |
| P2-T10 | Codex reports its token counts (P2-G finding 57) | P2-T9 | S | done |
| P2-G | Phase 2 gate (rerun the two failed criteria; the 20 Nov run's other five stand) | P2-T1..T10 | S | done |
| P3-T1 | Shared agent foundation (reasoning note, claim labels, self-critique) | P2-G | M | done |
| P3-T2 | Knowledge pack structure and `vesper kb` search | P2-G | M | done |
| P3-T3 | QA owns checks; prove-it-fails self-test | P3-T1 | L | done |
| P3-T4 | Reviewer: evidence-backed, multi-lens, calibration | P3-T1 | L | doing |
| P3-T3b | Fold P2-G's accepted findings into the Pocket Todo gates | P3-T3, P3-T4 | L | todo |
| P3-T5 | Exploratory QA session | P3-T3, P1-T10 | M | todo |
| P3-G | Phase 3 gate | P3-T1..T5, P3-T3b | S | todo |
| P4-T1 | Designer knowledge pack (content) | P3-T2 | L | todo |
| P4-T2 | Designer tools and design artifacts | P4-T1 | M | todo |
| P4-T3 | Design gates (tokens, anti-patterns, accessibility, fidelity) | P4-T2 | L | todo |
| P4-T4 | Frontend role, skills and designer contract | P4-T2 | M | todo |
| P4-T5 | Backend (Go) role and skills | P3-G | M | todo |
| P4-T6 | Planner role, templates and estimates | P2-T3, P3-G | M | todo |
| P4-T7 | Tech lead role, templates and hosting pack | P3-G | M | todo |
| P4-T8 | Starter seeds: Vite app, Astro site, Go API | P1-T6 | M | todo |
| P4-G | Phase 4 gate | P4-T1..T8 | M | todo |
| P5-T1 | Local connector (MCP server) | P2-T2, P4-G | M | todo |
| P5-T2 | Packaging: Claude Code plugin, uv/pipx, sandbox image, `vesper open` | P4-G | M | todo |
| P5-T3 | Automatic repair loop up to a pull request | P2-T2, P4-G | L | todo |
| P5-T4 | Evaluation bench and scorecard | P5-T1, P5-T2 | L | todo |
| P5-T5 | Design bench with blind owner rating | P5-T4 | M | todo |
| P5-T6 | Release candidates, permission ladder, SETUP.md, v1.0 | P5-T3, P5-T5 | M | todo |
