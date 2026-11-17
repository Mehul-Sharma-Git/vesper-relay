# Getting started: running the upgrade plan

This is your guide to the upgrade plan. Claude Code does the work through three project
commands. You set things up once, start sessions, and step in only when the work needs
you. Everything else (rules, the status board, the tasks) is in [README.md](README.md).

## One-time Mac setup

1. Install [Claude Code](https://code.claude.com) and the GitHub CLI
   (`brew install gh`), then run `gh auth login`.
2. In the repository root, run:

   ```sh
   sh scripts/dev-setup.sh
   ```

   It finds a Python 3.11+ (or installs `python@3.12` with Homebrew), creates `.venv`,
   runs the tests and plan checks, and lists optional tools (Go, Node, pnpm,
   Docker/Colima) with the task that first needs each. Run it again any time; it only
   changes what's missing.
3. Open Claude Code in the repository. The first time, it asks you to trust the project's
   settings; accept, so the setup check runs at the start of every session and
   `/next-task`, `/phase-gate` and `/plan-sync` appear in the `/` menu.

You never need to activate the venv: every command calls `.venv/bin/python3` directly.

## The daily loop

```text
/clear
/next-task
```

`/next-task` does one task from the status board, end to end:

1. It updates `dev`, checks the environment, and runs the plan's fact checks.
2. It picks the task, or resumes one that's in progress.
3. It writes failing tests first, then implements.
4. It runs every check, opens a PR into `dev`, waits for CI, and gets an independent
   review.
5. It merges the PR into `dev`.

It ends with what was done, the PR link, the next task ID, and whether that task needs
you. Then it stops.

`/clear` first gives each task a fresh context. Repeat for as many tasks as your plan
limits allow.

## The other two commands

| Command | Use it when |
| --- | --- |
| `/phase-gate` | `/next-task` tells you the next task is a phase gate (`P1-G` … `P4-G`). It runs the gate, pauses for your steps, records the results, and opens the `dev` → `main` PR. |
| `/plan-sync` | You (or anyone) committed code outside the plan, such as a hand fix or a new feature, or `verify-facts.sh` reports DRIFT on tasks that aren't done yet. It analyses those commits, updates the plan to match, summarises the changes for you, and merges the update into `dev`. |

## Moments that need you

Claude does everything it can first, then stops with exact instructions.

| Moment | When | What you do |
| --- | --- | --- |
| Install prompts, Mac password | `dev-setup.sh` without Python 3.11+; Docker Desktop or Colima for P1-T9 | Follow the printed command; type your password in macOS dialogs |
| Logins for AI tools | P1-T8, P1-T11, gates: Claude Code (`claude setup-token` for the sandbox), Codex, Gemini | Run the login command it gives you |
| Keychain and Mac dialogs | `vesper setup` storing secrets (P1-T11); approval dialogs after P2-T2 | Click Allow or Approve when the dialog matches what it told you |
| Plan approvals | Every gate run: `vesper review`, then `approve --digest` | Read the plan summary and approve (only a human can, by design) |
| Plan usage readings | Start and end of each `/phase-gate` | Run `/usage` and paste the figures |
| Design choices | Phase 4: the designer's direction brief and its 3 directions; P5-T5 blind rating | Pick or mix a direction; rate the screenshots |
| Owner-OK decisions | Next.js or other stack exceptions, tech-lead prototypes (P4-T7), repair plans (P5-T3), release criteria and promotion (P5-T6) | Answer the question it asks |
| Plan conflicts | A task contradicts a decision in `00-context.md`, or is ambiguous | Decide which wins; it records your answer |
| Review stuck | The independent review still blocks after 2 fix rounds | Read the blockers in the PR and decide |
| Phase gate PR | End of every `/phase-gate` (marked PASSED or FAILED) | Review it and merge `dev` → `main` (below); for a failed gate, decide whether to merge or fix first |

## Resuming a stopped task

Run `/next-task` again (after `/clear` if you like). It finds the task's branch or open PR
and continues where it stopped: a session limit, a closed window, or a step that waited
for you. If it stopped for you, do that step first. You can also reply in the same session
with the result.

A stopped phase gate or plan sync resumes with its own command, `/phase-gate` or
`/plan-sync`. If you run `/next-task` instead, it tells you which one to use.

## Checking limits

Run `/usage` in Claude Code to see your current session and weekly usage. Size L tasks may
need most of a session (S fits easily, M fills one; see the board), so start those when
the session meter is low. If a limit hits mid-task, nothing is lost: the work is pushed
on its branch, and `/next-task` resumes it after the reset.

## How main gets updated

- All plan work merges into `dev`, the default branch, automatically, after local checks,
  green CI and an independent review.
- `main` changes only at phase gates, and only you merge into it. `/phase-gate` opens a
  `dev` → `main` PR with the gate report. Review it, then merge with
  **Create a merge commit**, not squash. A squash would make `main` and `dev` diverge, and
  the next gate PR would conflict.
- Claude never pushes to or merges into `main`.
