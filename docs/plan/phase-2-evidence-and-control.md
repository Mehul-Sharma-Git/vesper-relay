# Phase 2 — Evidence and control

**Goal:** reviewers see the real evidence, only a human can approve, plans can't skip
required thinking, nothing risky gets lost, and Vesper respects the user's AI plan limits.

**Phase gate (P2-G):** two consecutive runs (Pocket Todo plus one bug-fix run) where:
estimates land inside their band; a seeded security advisory blocks acceptance until
decided; a plan missing a required section is refused at `review`; an AI-issued
`approve` without human confirmation is refused.

---

## P2-T1 — Gate logs, scripts and artifacts in the review copy

- **Why:** the reviewer said "the check logs listed in review.json are not in the review
  copy"; the tests evidence rested on one-line summaries (`appendix-b`, finding 3).
- **Read first:** `builder/runner.py` (`stage_review`, `review_candidate`, `read_tail`),
  `builder/review_gate.py` (`prompt`).
- **Change:** copy into the review workspace: `checks/` (the approved gate package,
  read-only), `logs/<CHECK>.log` (full, capped at 256 KB each), and `artifacts/<CHECK>/`
  (anything a gate writes to the directory named in env `VESPER_ARTIFACTS`, e.g. Playwright
  screenshots, capped at 20 MB). Include them in the review view digest. Tell the reviewer
  where they are in the prompt.
- **Acceptance:** a gate that writes a PNG to `$VESPER_ARTIFACTS` → the PNG is in the
  reviewer's copy; tampering with a copied log changes the view digest and is refused.

## P2-T2 — Human-only approvals and a plain-language approval sheet, in every door

- **Why:** the owner decided the AI can never approve on the owner's behalf. Today this is
  only text in the skill; an AI with shell access can type `vesper approve --digest …` itself.
- **Read first:** `build_local.py` (`approve`), `vesper.py` (`apply`, `repair-commit`),
  `builder/runner.py` (`approve`), `integrations/vesper-relay/SKILL.md`.
- **Change:**
  1. Protected actions: approving a plan, applying a patch to a repo, accepting a security
     or data risk (P2-T7), adding checks after approval (P2-T6), merging or committing a
     repair, promoting a release (P5), and **attesting that a report came from an
     independent reviewer** (`review-plan --report --attest-independent` and
     `review-candidate --report --attest-independent`). b7da4d1's own notes say declared
     session identities are not authentication; in supervised mode an AI could otherwise
     attest its own critique.
  2. A protected action needs a **human confirmation** from a pluggable confirmer:
     - `tty`: an interactive prompt that shows a short random code and the digest summary;
       refuses when stdin is not a terminal (AI tool calls run without one).
     - `macos-dialog`: a native dialog via `osascript`, so the owner can approve while
       working inside an AI chat.
     - `mcp-elicitation`: for the connector (P5-T1), a confirmation the host app shows
       directly to the human (verify the MCP elicitation feature at implementation time).
     - `dashboard`: a button in the later dashboard.
  3. The confirmation is recorded with the digest, the confirmer used, a timestamp, and the
     file list (path, hash, size) of what was confirmed. Configured in
     `[approvals] confirmer = "macos-dialog"` (personal config).
  4. **Approval sheet.** The owner must understand what they approve without reading
     JSON (during the P1-G gate run on 19 Nov 2026 the owner was shown the raw `review`
     bundle and could not tell what it meant). Every protected action shows a
     plain-language sheet built only from the program's own records for that action (the
     approved bundle, the reviewed patch, the report or finding), so it describes exactly
     what the confirmation will lock. Plan approval shows:
     - what will be delivered (`title`, `delivery`) and the mode (new build or change to a repo);
     - each requirement in plain words with the gate that proves it (`R1 … → G_API`);
     - each job: its role, its goal in one line, and the only files it may change;
     - the independent critique: verdict, blocker count, and the top advisory findings
       in one line each; at `skip` depth, "no critique (skip depth)" and the recorded reason;
     - what changed since the last **human confirmation** recorded for this run (files
       added, removed or edited, with line counts, against that confirmation's file list),
       or "first approval". Printing a sheet never moves this baseline, so an AI that runs
       `vesper review` itself cannot hide a change from the owner;
     - where to look further (the plan folder, wireframe files) and the short digest.
     The other protected actions show, in the same style:
     - patch apply: target repository and branch, each file touched with lines added and
       removed, the reviewed patch's short digest, and the review verdict;
     - risk acceptance (P2-T7): the finding in plain words, its severity and source, and
       exactly what is being accepted;
     - adding checks after approval (P2-T6): each new check's id and script, the jobs it is
       assigned to, and the reason given;
     - repair merge or commit: the failure id, the files changed, tests added, and the
       review verdict;
     - release promotion (P5): the candidate, its scorecard summary, and each release
       criterion with pass or fail;
     - attesting independence: the report's short digest, the reviewer session and adapter
       it claims, its verdict and blocker count, and the sentence the human is vouching
       for ("this report came from a separate reviewer session, not the author").
     `vesper review` prints the plan sheet by default; `vesper review --json` keeps today's
     bundle for tools. The `tty` and `macos-dialog` confirmers show the action's sheet (the
     dialog a shortened form with a "show full sheet" option) before asking.
  5. Update the skill: tell the assistant to run the command and tell the human to confirm.
- **Do not:** add any flag that skips confirmation, other than an explicit test-only
  environment variable that `vesper doctor` warns about.
- **Acceptance:** tests that each protected action is refused without a confirmer result;
  that `tty` refuses non-interactive stdin; that the recorded confirmation binds the digest.
  Approval sheet: for the Pocket Todo fixture, `vesper review` prints every requirement
  with its gate, each job with its allowed files, the critique verdict and blocker count,
  and no raw hashes beyond the short digest; after a recorded human confirmation, editing
  one check script makes the next sheet list that file as changed, even when `vesper
  review` was run in between; a run with no confirmation shows "first approval"; each
  protected action's sheet shows the fields listed for it; `--json` output is unchanged.

## P2-T3 — Usage ledger and plan-limit estimates

- **Why:** the owner pays a fixed fee and has session and weekly limits; estimates must be
  in % of those limits and wall time, never dollars. Anthropic does not publish exact Pro
  numbers, so Vesper calibrates from the owner's own runs.
- **Change:**
  1. Ledger at `<state_home>/usage.jsonl`: one line per AI call with run, job, role,
     brain, adapter, model, effort, start, end, and tokens when the adapter has the
     `usage_report` capability (e.g. Claude Code's `--output-format json` gives a `usage`
     block; the adapter keeps the human summary from its `result` field).
  2. `vesper usage record --account claude --session 42 --week 13` lets the owner (or a
     script reading Claude Code's statusline `rate_limits` fields) log observed plan %.
     Pairs of readings around runs calibrate "% per 1k tokens" per provider and model.
  3. `vesper --project RUN estimate` and the `review` output show: jobs, AI calls, expected
     session % and weekly % per provider as a low–high band, wall time, sessions needed,
     and a confidence level (low below 5 calibrated runs).
- **Acceptance:** tests with synthetic ledger data: the band contains the observed value in
  a held-out run; with no calibration the estimate says "uncalibrated" and shows tokens and
  time only.

## P2-T4 — Limit-aware scheduling

- **Change:** before starting each job, `run` compares the estimate with the last known
  usage plus the reserve. If the job would cross it: stop before the job with status
  `paused_for_limits`, print when the window should reset (from the last recorded reset
  time) and how to resume (`run` again). Add `run --start-after HH:MM` to wait for a reset.
  Never stop in the middle of a job.
- **Acceptance:** tests with a fake clock and ledger: pauses before the job that would
  cross the reserve; resumes from the accepted snapshot; never interrupts a running job.

## P2-T5 — Required plan sections by depth (extend `planning.json`)

- **Already done in b7da4d1:** `plan/planning.json` (manifest version 1) declares six
  impacts; `builder/planning.py` derives the depth (`full` for builds or any material
  impact, `focused` for cross-layer only, `skip` for a justified narrow fix), enforces the
  tech lead's architecture handoff and contract acknowledgements, and requires an
  independent `review-plan` critique before `approve` at `full` and `focused` depth. Use
  these depth names everywhere; there is no separate "tier".
- **Why more is needed:** the planner never asked about stack or system design, and nothing
  enforces the problem framing, assumptions, risks, options or the plan-limit estimate
  (`appendix-b`, finding 7).
- **Read first:** `builder/planning.py` (`validate_planning`, `validate_critique`),
  `builder/contracts.py` (`review_bundle`), `docs/PLANNER.md`, `tests/test_planning.py`.
- **Change:**
  1. Planning manifest version 2 (version 1 stays valid for existing runs; new runs write 2)
     adds sections:
     - every depth: `problem` (why, success measure, non-goals), `assumptions` (each with how
       and when it gets confirmed), `estimate` (from P2-T3);
     - `focused` and `full`: `risks` (pre-mortem items, each with a check or mitigation) and
       `stack` (choice + reason, or "existing repo");
     - `full`: `options` (2–3 approaches with trade-offs and the recommendation),
       `components` (cache, queue, CDN, realtime, search, storage → now / later + trigger /
       no) and `phases`.
  2. `review` refuses a version-2 manifest missing a section its depth requires, naming it.
  3. Add these sections to the `review-plan` critique prompt so the critic checks them.
- **Acceptance:** tests per depth for accept and refuse; version-1 manifests and already
  approved runs still validate; `tests/test_planning.py` keeps passing.

## P2-T6 — Additive checks after approval

- **Why:** QA must be able to add a check mid-build without weakening anything and
  without a full re-approval.
- **Change:** `vesper --project RUN add-check --id G_X --script x.py` (or `--command ...`)
  writes an amendment under `.builder/amendments/` with its own digest chained to the
  approval digest. Allowed: new checks and assigning them to unfinished jobs only.
  Refused: removing, editing or reassigning an existing check. `status` and the final
  summary list amendments for the owner.
- **Acceptance:** tests that an added check runs on the next verification; that editing an
  approved check file is still detected; that an amendment cannot touch an accepted job.

## P2-T7 — Advisory backlog and decision gate

- **Why:** the reviewer flagged that any website could change the owner's todos (CSRF), as
  an advisory; it shipped unfixed (`appendix-b`, finding 5).
- **Change:**
  1. Each finding gains `category`: `correctness | security | data | performance |
     maintainability | design | other` (add to the schema from P1-T2).
  2. All advisories are stored in `<run>/.builder/backlog.json` and shown in `status`.
  3. A security or data advisory moves the attempt to `awaiting_decision`.
     `vesper --project RUN decide FINDING_ID --fix` returns the job for correction (counts
     as a retry); `--accept-risk --reason "..."` records the owner's acceptance and
     continues.
- **Acceptance:** tests for each path; a run cannot reach `complete` with an undecided
  security advisory.
