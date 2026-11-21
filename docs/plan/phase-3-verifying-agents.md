# Phase 3 — Agents that verify (shared foundation, QA, reviewer)

**Goal:** every agent thinks in writing before acting and labels its claims; QA owns
checks that are proven to fail; the reviewer's blockers come with evidence and nothing
risky gets lost.

**Why verifiers before builders:** stronger checks and reviews make every later upgrade
measurable. Phase 4 changes are judged by the tools built here.

**Phase gate (P3-G):** on the Pocket Todo fixture: every check fails against its broken
variant; reviewing `fixtures/pocket-todo/solution/` (which really shipped without CSRF/Origin
checks) with the multi-lens review yields a security blocker with a repro; reasoning notes
are present for every job.

---

## P3-T1 — Shared agent foundation

- **Read first:** `team/roles/*.md`, `team/skills/*/SKILL.md`, `builder/team.py`,
  `builder/providers.py` (`worker_prompt`), `builder/review_gate.py` (`prompt`).
- **Change:**
  1. New skill `team/skills/critical-thinking/SKILL.md`, always loaded for every role
     (add it as a core skill in `PROFILES` alongside each role's default). Content:
     - **Reasoning note** (required before the main output):
       ```
       ## Reasoning note
       Understanding: <the task in one or two sentences>
       Assumptions: <each marked how it will be confirmed>
       Options considered: <at least two, with the trade-off>
       Choice and why: <one paragraph>
       Pre-mortem: <how this could fail; what I did about each>
       How I'd know I'm wrong: <the observation that would disprove the choice>
       ```
     - **Claim labels:** every factual claim in hand-offs is tagged `[verified]` (I ran or
       read it; say how), `[inferred]`, or `[assumed]`. "Should work" is not allowed.
     - **Self-critique:** before finishing, re-read the diff or output as a hostile
       reviewer would, list what that reviewer would flag, fix it, then hand off.
  2. The runner stores the worker's reasoning note from its final message in
     `.builder/attempts/<id>/reasoning.md`. Missing note: warning on `skip` and `focused`
     depth, rejection (`failure_kind: "process"`) on `full`. The review packet gets only the
     labelled claims of the worker's hand-off (`claims` in `review.json`), never the note:
     reviewer independence includes no access to the worker's reasoning (`00-context.md`,
     "One AI is enough"; owner, 21 Nov 2026, on the review of PR #56).
  3. Reviewer prompt: check that `[verified]` claims have evidence; an unsupported
     `[verified]` claim is an advisory finding (category `other`).
- **Acceptance:** tests for note extraction, the depth rule, and that the critical-thinking
  skill appears in every frozen role (`freeze_team` output).

## P3-T2 — Knowledge packs and `vesper kb`

- **Why:** role files are 300–500 words and skills about 250; experts carry deep
  checklists, failure catalogues and examples.
- **Change:**
  1. `team/knowledge/<role>/*.md`. Each file starts with front matter: `title`, `tags`,
     `last_checked` (date), `sources` (URLs), `licence` (of anything quoted). Write in
     our own words; quote only permissive material, with attribution.
  2. `builder/knowledge.py`: a standard-library BM25 index over paragraphs.
     `vesper kb search --role ROLE "query"` prints the top passages with file and heading.
  3. The runner appends the top 5 passages for the job goal to the worker prompt, and the
     sandbox mounts `team/knowledge/` read-only at `/knowledge` so agents can search more
     (document the path in the prompt).
  4. Pack files are part of the frozen role fingerprint (`team.profile` revision), so a
     run's approval binds the exact knowledge used.
  5. A test fails if any pack file's `last_checked` is older than 180 days (warning
     only for now, so stale facts get rechecked).
- **First content (this task):** `team/knowledge/qa/` and `team/knowledge/reviewer/`:
  - QA: test-pyramid guide; scenario template; flaky-test policy; non-functional checklist
    (accessibility, visual, cross-browser, load, security scan, Core Web Vitals); test-data
    guide; "proving a check can fail" guide.
  - Reviewer: failure-mode catalogue by category (authz and object ownership, injection,
    CSRF/CORS/Origin, secrets in logs, race conditions, retries and idempotency, N+1
    queries, unbounded input, error leakage, stale UI state, accessibility regressions);
    a readability checklist for Go and for TypeScript, written in our own words with
    links to the Google Go Style Guide and the Google TypeScript Style Guide.
- **Acceptance:** tests for front-matter validation, search ranking on a tiny corpus,
  prompt inclusion, and fingerprint change when a pack file changes.

## P3-T3 — QA owns the checks and proves they can fail

- **Read first:** `team/roles/qa.md`, `team/skills/acceptance-evidence/SKILL.md`,
  `builder/contracts.py`, `builder/runner.py`, P1-T5 (command gates), P2-T6 (additive checks).
- **Change:**
  1. `team/roles/qa.md`: QA writes every acceptance check before approval, plus
     `checks/test-strategy.md` (risks → test level → check ID). Test pyramid: builders own
     unit tests; QA owns contract, integration and a few end-to-end journeys. Contract tests
     are generated from the Go OpenAPI spec, including malicious requests. Non-functional
     checks by depth: always accessibility, visual comparison, phone + laptop sizes; `full`
     depth adds Firefox and WebKit, load test, baseline security scan, Core Web Vitals.
  2. `vesper --project RUN draft-checks --brain NAME` runs QA as a writer over a copy of
     `plan/` and `checks/`; the result is shown to the owner like any plan change.
  3. **Prove-it-fails:** each check may have `checks/_broken/<CHECK_ID>/` holding a small
     patch or replacement files that break the behaviour it guards.
     `vesper --project RUN prove-checks` applies each broken variant to a copy of the seed
     (or the fixture solution when given) and requires the check to fail. `focused` and `full`
     depths must pass `prove-checks` before `approve`; results are stored in the approval.
     (Built in `builder/qa.py`: each check with a variant runs on the unbroken copy first, so
     a check that fails there too is reported as proving little rather than counted as proven;
     a variant that passes, or cannot be applied, refuses approval.)
  4. Mutation testing at `full` depth as optional command gates: evaluate Gremlins (Go) and
     StrykerJS (TypeScript); record the score, don't block on it yet. (Built as checks with
     `"blocking": false`, which record and never reject; no requirement may rest on one.)
- **Acceptance:** tests that `approve` is refused when a check passes against its broken
  variant; that a missing `_broken` entry is reported per check; that the Pocket Todo
  fixture's three checks all fail against their broken variants (add them under
  `fixtures/pocket-todo/checks/_broken/`).

## P3-T4 — Reviewer: evidence-backed, multi-lens, calibrated

- **Read first:** `team/roles/reviewer.md`, `team/skills/candidate-review/SKILL.md`,
  `team/skills/security-diff/SKILL.md`, `builder/review_gate.py`, `builder/runner.py`.
- **Change:**
  1. Schema (from P1-T2) gains `repro` (string) on findings and `confidence`
     (`high | medium | low`). A `blocking` finding without `repro` is downgraded to a
     `suspected` advisory automatically, and the owner sees it.
  2. With a sandbox backend, the reviewer may run commands in its read-only copy (P1-T10) to
     prove a finding; it may write a failing test into its own temp dir and quote it in `repro`.
  3. **Multi-lens at `full` depth:** the runner launches four lens reviews (correctness,
     security, performance, readability), each with its lens prompt and the matching
     knowledge passages, then merges deterministically: union of findings, dedupe by
     path + category + normalised text, verdict `request_changes` if any blocker remains.
     `focused` and `skip`: one combined review. Design is not a reviewer lens; the
     designer's gate covers it (phase 4).
  4. **Size guideline:** when a job's diff exceeds 400 changed lines, add a note to the
     review packet and to `status` suggesting the planner split future jobs. Do not refuse.
  5. **Calibration:** `.builder/calibration.jsonl` records each finding's outcome:
     `confirmed` (job returned and the fix changed that path), `dismissed`
     (owner `decide --dismiss`), `unknown`. `vesper learn` reports reviewer precision per lens.
- **Acceptance:** tests for blocker downgrade without repro, deterministic merge, the
  400-line note, and calibration records; a stand-in review of the Pocket Todo solution
  (no CSRF/Origin checks in `server.py`) yields a security blocker with a repro.

## P3-T5 — Exploratory QA session

- **Change:** after a frontend job passes its gates (`focused` and `full` depth), the runner
  may launch QA in exploratory mode with Playwright inside the sandbox against the
  candidate app: empty input, very long text, emoji, double clicks, back button, slow
  network, two tabs, keyboard only. QA writes `exploratory.md` with each bug's repro steps;
  findings enter the backlog (P2-T7) with category and severity. Bugs that matter become
  additive checks (P2-T6).
- **Acceptance:** stand-in test that exploratory findings land in the backlog; on the
  Pocket Todo fixture the session produces a report.
