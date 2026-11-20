# Phase 2 — Evidence and control

**Goal:** reviewers see the real evidence, only a human can approve, plans can't skip
required thinking, nothing risky gets lost, and Vesper respects the user's AI plan limits.

**Phase gate (P2-G):** two consecutive runs (Pocket Todo plus one bug-fix run) where:
estimates land inside their band; a seeded security advisory blocks acceptance until
decided; a plan missing a required section is refused at `review`; an AI-issued
`approve` without human confirmation is refused. Then Pocket Todo again with
`[brains.reviewer] use = "codex"` (moved from P1-G on 19 Nov 2026): it reaches `complete`
with every blocker and every security or data advisory, from the plan critique and from
job reviews, either fixed or decided by the owner through P2-T7; every review parses the
first time; and the exported app's three gates pass.

**Rerun (owner, 20 Nov 2026):** the first P2-G run failed two criteria, the seeded security
advisory and the estimate bands (appendix B, "Gate P2-G — 2026-11-20 18:56", findings 53 and
54). After P2-T8, P2-T9 and P2-T10, rerun only those two; the other five passed on 20 Nov and
stand. (A rerun started 21 Nov 2026 stopped before its first run: Codex logged no tokens, so
`chatgpt` could never be inside its band; finding 57, now P2-T10.)
1. Seeded advisory: the bug-fix run on the run-2b seed (a reachable SQL injection inside the
   `delete_list` the fix touches), with the job's `max_attempts` set to 1. The owner's threat
   model for that plan is its decision D3: loopback by default, other websites refused,
   local programs trusted (a device on the Wi-Fi reaches the app only with `--host 0.0.0.0`,
   whose full access the owner accepted as A9). The injection is reachable only by such
   trusted callers, so under P2-T8's rule it is an advisory. Pass when the review reports
   the injection as a security advisory and acceptance waits for the owner's `decide`. If the
   reviewer files it as a blocker, the owner still decides (the single attempt is used up),
   but the criterion is recorded as not exercised.
2. Estimates: first one calibration run with marked readings and the same brain config as
   the checked runs (Claude workers, Codex reviewer, so both accounts calibrate), then two
   consecutive runs (Pocket Todo, then a bug fix) whose estimates come from marked readings
   only. Pass when `vesper usage check` reports inside for every account and limit of both
   runs.

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
  1. Protected actions: approving a plan, applying a patch to a repo, accepting a risk or a
     reviewer blocker (P2-T7), adding checks after approval (P2-T6), merging or committing a
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
     file list (path, hash, size, line count) of what was confirmed. Configured in
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
     - every risk the plan proposes to accept (P2-T5), each in plain words with its reason,
       and every critique finding marked "Accepted risk: owner must confirm", all listed
       in full: confirming the plan approval is the owner's acceptance of each;
     - what changed since the last **human confirmation of a plan approval** recorded for
       this run (files added, removed or edited, with line counts before and after, against
       that confirmation's file list), or "first approval". Printing a sheet never moves
       this baseline, so an AI that runs `vesper review` itself cannot hide a change from
       the owner;
     - where to look further (the plan folder, wireframe files) and the short digest.
     The other protected actions show the fields below in the same style. Each one's "what
     changed" compares with the last human confirmation of the same action for the same
     subject (the same repository, finding, run's amendments or release candidate), or
     says "first confirmation"; confirmations of other actions never serve as a baseline.
     This task builds the sheets for the actions that exist now (patch apply, repair merge
     or commit, attesting independence); P2-T6, P2-T7 and P5-T6 build theirs with their
     actions:
     - patch apply: target repository and branch, each file touched with lines added and
       removed, the reviewed patch's short digest, and the review verdict;
     - risk acceptance (P2-T7): the finding in plain words, its severity and source, and
       exactly what is being accepted;
     - adding checks after approval (P2-T6): each new check's id and its script or command,
       the jobs it is assigned to, and the reason given (both recorded in the amendment);
     - repair merge or commit: the failure id, the files changed, tests added, and the
       review verdict;
     - release promotion (P5): the candidate, its scorecard summary, and each release
       criterion with pass or fail;
     - attesting independence: the report's short digest, the reviewer session and adapter
       it claims, its verdict and blocker count, and the sentence the human is vouching
       for ("this report came from a separate reviewer session, not the author").
     `vesper review` prints the plan sheet by default; `vesper review --json` keeps today's
     bundle for tools. **Every confirmer presents the action's sheet before asking**: `tty`
     in full; `macos-dialog` as a shortened form with a "show full sheet" option;
     `mcp-elicitation` (P5-T1) and `dashboard` when they are built. A shortened form always
     keeps the "what changed" section and the short digest.
  5. Update the skill: tell the assistant to run the command and tell the human to confirm.
- **Do not:** add any flag that skips confirmation, other than an explicit test-only
  environment variable that `vesper doctor` warns about.
- **Acceptance:** tests that each protected action is refused without a confirmer result;
  that `tty` refuses non-interactive stdin; that the recorded confirmation binds the digest.
  Approval sheet: for the Pocket Todo fixture, `vesper review` prints every requirement
  with its gate, each job with its allowed files, the critique verdict and blocker count,
  and no raw hashes beyond the short digest; after a recorded human confirmation, editing
  one check script makes the next sheet list that file as changed, even when `vesper
  review` was run in between; a run with no confirmation shows "first approval"; plan
  approval, patch apply, repair commit and attesting independence each show the fields
  listed for them; a stand-in confirmer receives the sheet before it is asked, and the
  `macos-dialog` short form contains the "what changed" section and the short digest;
  `--json` output is unchanged.

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
     - `focused` and `full`: `risks` (pre-mortem items, each with a check or mitigation),
       `stack` (choice + reason, or "existing repo"), the owner's `threat_model` (who and what
       is trusted, which threats are in scope; P1-G finding 47), the tech lead's `reachability` and
       `concurrency` lists plus QA's `failure_paths` matrix (requirement or list item →
       scenario → assertion → the wrong implementation it catches). Every list item is
       mitigated with the gate that proves it, or proposed as a risk to accept with a reason.
       A proposed risk is accepted only by the owner's confirmed plan approval, never by a
       decision-log entry: `review` shows each in full, and the plan-approval sheet (P2-T2)
       lists each one. The roles and the
       critique already ask for these (P1-G, `appendix-b` finding 45); this makes `review`
       refuse a plan without them;
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
  with `--jobs J_X[,J_Y]` (unfinished jobs only) and `--reason "..."` writes an amendment
  under `.builder/amendments/` with its own digest chained to the approval digest; the
  amendment records the check, its jobs and the reason. Allowed: new checks and assigning them to unfinished jobs only.
  Refused: removing, editing or reassigning an existing check. `status` and the final
  summary list amendments for the owner. The amendment is a protected action: the human
  confirmer (P2-T2) shows the add-check approval sheet (P2-T2 item 4) before asking.
- **Acceptance:** tests that an added check runs on the next verification; that editing an
  approved check file is still detected; that an amendment cannot touch an accepted job;
  that the confirmer receives the add-check sheet (each new check's id, script or command,
  assigned jobs and reason); that `add-check` without `--jobs` or `--reason` is refused.

## P2-T7 — Advisory backlog and decision gate

- **Why:** the reviewer flagged that any website could change the owner's todos (CSRF), as
  an advisory; it shipped unfixed (`appendix-b`, finding 5). And at P1-G (19 Nov 2026) the
  reviewer alone decided what each finding meant: a Codex plan critique never approved in
  five rounds, and Codex job reviews outlasted the attempt budget (findings 47, 50, 51).
  The owner decided that every finding ends in the owner's decision (`00-context.md`).
- **Change:**
  1. Each finding gains `category`: `correctness | security | data | performance |
     maintainability | design | other` (add to the schema from P1-T2).
  2. All advisories are stored in `<run>/.builder/backlog.json` and shown in `status`.
  3. A security or data advisory moves the attempt to `awaiting_decision`.
     `vesper --project RUN decide FINDING_ID --fix` returns the job for correction (counts
     as a retry); `--accept-risk --reason "..."` records the owner's acceptance and
     continues. Accepting a risk is a protected action: the human confirmer (P2-T2) shows
     the risk-acceptance approval sheet (P2-T2 item 4) before asking.
  4. Blockers too. A plan-critique blocker no longer only refuses `approve`: the approval
     sheet lists each one, and the owner either sends the plan back
     (`decide FINDING_ID --fix`) or accepts it (`--accept-risk --reason "..."`); once every
     blocker is decided, `approve` can proceed. A job whose attempts are used up with
     review blockers still open moves to `awaiting_decision`, not `blocked`: the owner
     grants one more attempt (`--fix`) or accepts the open blockers (`--accept-risk`), which
     accepts the candidate with them recorded. The independent review still runs and every
     finding is kept; only the owner's protected decision overrides a blocker.
- **Acceptance:** tests for each path; a run cannot reach `complete` with an undecided
  security advisory; the confirmer receives the risk sheet (the finding in plain words, its
  severity and source, and what is accepted); a plan whose critique blockers the owner
  accepted can be approved and its sheet lists each acceptance; a job out of attempts with
  open blockers reaches `awaiting_decision`, and both decisions work; an AI-issued
  `--accept-risk` on a plan-critique blocker or a job-review blocker is refused without a
  human confirmation, and the confirmer shows the risk sheet for each.

## P2-T8 — Review the code a change touches

- **Why:** at P2-G (run 2b, finding 53) the seed's `delete_list` built its SQL from a raw
  path segment, a reachable injection that deleted every list. The worker added the
  missing check two lines below it; the candidate reviewer approved with no findings,
  because it judged only the changed lines. The owner decided (20 Nov 2026) that a review
  also checks the code around a change.
- **Read first:** `builder/review_gate.py` (`prompt`, `CANDIDATE_SWEEP`, `write_diff`),
  `builder/runner.py` (`stage_review`), `team/roles/reviewer.md`,
  `team/skills/candidate-review/SKILL.md`.
- **Change:**
  1. The review packet names the touched code: for each changed file, each enclosing
     definition (function, method or class) around the changed lines, with its line range,
     as `touched` in `review.json`; when no definition can be found (a language Vesper does
     not parse, top-level code), the whole file, up to the diff budget. The diff shows each
     touched definition in full.
  2. The candidate-review prompt asks for a sweep of the touched code, not only the changed
     lines: a reachable defect there is reported whether or not the candidate introduced
     it, with its category. It is blocking when the job may change that code (it is inside
     the job's paths) and the defect breaks a requirement or decision, or is a security
     defect a threat inside the owner's threat model can reach; otherwise it is an
     advisory, so a security or data one waits for the owner (P2-T7). The threat model is
     `planning.json`'s `threat_model` when the plan has one; at `skip` depth, the one the
     plan's decisions record; if neither records one, the threats its decisions defend
     against (as the candidate blocker rule already says).
- **Do not:** give the reviewer write access or widen the review copy; require reviewing
  files the candidate did not change; change the plan critique.
- **Acceptance:** tests that `touched` lists the enclosing Python function and the
  enclosing JavaScript function of a changed line, and the whole file when none is found;
  that the diff shows a touched function in full; that the prompt contains the sweep of
  touched code, its blocking rule and where the threat model comes from at each depth.
  P2-G's rerun is the real-reviewer check.

## P2-T9 — Estimates you can check

- **Why:** at P2-G (finding 54) no pair of runs could be checked against its band: `/usage`
  shows whole points, so a rise under one point reads 0; the assistant driving the runs
  spends the same account, so each reading pair also counts its usage; and nothing
  compared a run's observed usage with the band its plan was approved on.
- **Read first:** `builder/usage.py` (`record_reading`, `calibrate`, `estimate`,
  `limit_check`), `builder/runner.py` (`approve`), `vesper.py` (`usage`), `tests/test_usage.py`.
- **Change:**
  1. Readings can be marked as bracketing one stretch of Vesper's own work: `vesper usage
     record --account claude --session 42 --week 13 --before RUN` and `--after RUN`, taken
     right before and right after each `review-plan` or `run` invocation (a run that pauses
     for the owner's decisions or for limits gets a pair around each part), with the
     assistant otherwise idle. Bands come only from marked pairs: unmarked readings, which
     can include the host assistant's own use of the same account, no longer calibrate. An
     account with no marked pair is "uncalibrated" and shows tokens and time only.
  2. `approve` keeps the estimate it showed (per account and limit) in the run's state.
  3. `vesper --project RUN usage check` compares, per account and limit, the run's observed
     rise after approval (the sum over its marked pairs taken after `approve`; pairs around
     `review-plan` still calibrate but are not compared, because the estimate `approve` keeps
     no longer includes the critique) with that kept estimate: inside, below or above,
     where a rise within one reading step (1 point) of the band counts as inside because
     readings are whole points. A run whose kept estimate had no band, or with a part not
     bracketed by marked readings, is reported as unchecked. `status` of a complete run
     shows the result once its readings exist.
  4. `docs/USAGE.md` says how to take marked readings for every account a run uses
     (Claude: `/usage`; ChatGPT: Codex `/status`; `usage record --account chatgpt` already
     exists).
- **Do not:** add dollar figures; change the reserve rule or the pause before a job (P2-T4).
- **Acceptance:** tests with synthetic ledgers: a marked pair calibrates and unmarked pairs
  never do (an account with only unmarked readings is uncalibrated); a paused run's two
  marked parts are summed; a marked pair around `review-plan` calibrates but is left out of
  `usage check`; the approval keeps the estimate; `usage check` reports inside for a rise one
  step below the band and below for two steps below; a run with an unbracketed part, or
  approved without a band, is reported as unchecked.

## P2-T10 — Codex reports its token counts

- **Why:** the P2-G rerun (21 Nov 2026, finding 57) stopped before its first run: the Codex
  adapter declares `usage_report=False`, so every Codex call enters the usage ledger with
  `tokens: None`. `calibrate` skips a marked window holding a call without tokens, so the
  `chatgpt` account never gets a band and `usage check` reports it unchecked, whatever
  readings are taken. The rerun's estimate criterion uses a Codex reviewer and needs every
  account inside. The owner decided (21 Nov 2026) to fix this before rerunning the gate.
- **Read first:** `builder/brains/codex.py`, `builder/brains/claude_code.py` (`usage`),
  `builder/brains/base.py` (`Capabilities`, `usage`), `builder/brains/__init__.py`
  (`note_call`, `usage`), `builder/usage.py` (`record_call`, `total_tokens`), the four
  log fallbacks in item 3, `tests/test_brains.py`, `tests/test_usage.py`.
- **Change:**
  1. Every Codex command (worker, reviewer, consult) adds `--json` (in `codex exec --help`
     of the image's pinned codex-cli 0.170.0: "Print events to stdout as JSONL"), so its
     stdout, which the runner writes to the call's log, carries the event stream.
     `--output-last-message` stays the reviewer's and consultant's reply file, so
     `parse_result` and the tolerant decoder are unchanged.
  2. `Codex.usage(text)` reads that JSONL and sums the token counts of each turn's `usage`
     block (integer fields whose names end in `tokens`, as the Claude Code adapter keeps
     them); lines that are not JSON, and a stream with no usage, give `None`. The adapter
     declares `usage_report=True`. `note_call` already falls back to the log when the reply
     file has no usage; check that it does for Codex.
  3. Four places read the log when no reply file arrived (`response if response.is_file()
     else log`): `review_candidate` in `builder/runner.py`, the plan critique in
     `builder/planning.py`, `consult` in `vesper.py` and the probe in `builder/doctor.py`.
     A Codex event stream must not be decoded as the reply there: take the last agent
     message from the events, or treat a missing reply file from Codex as no reply.
- **Do not:** add dollar figures; change how a reviewer's reply is decoded; change other
  adapters; count a reading or calibrate from anything but marked pairs (P2-T9).
- **Acceptance:** tests that each Codex command carries `--json` and still writes the reply
  to `--output-last-message`; that `usage` sums the turns of a recorded `codex exec --json`
  stream (fixture text, two turns) and returns `None` for plain text and for a stream
  without usage; that a launched Codex reviewer's ledger row has tokens (stand-in program);
  that a marked pair around a Codex call now calibrates `chatgpt`; that a Codex reviewer
  with no reply file is not decoded from its event log; and that `vesper doctor`
  checks `--json` against the image's `codex exec --help`. P2-G's rerun is the real check.

