# Pocket Todo fixture

The real artifacts from the 9 Nov 2026 test run.

- `plan/`: the approved plan (contract, product, design, design.json, architecture,
  decisions, intake, wireframes HTML + PNG), updated for b7da4d1: `intake.json` carries
  `planning_version: 1`, `planning.json` declares `full` depth with the technical-lead
  architecture handoff, and `api-contract.md` is the canonical contract. On b7da4d1 it passes
  `review`, and `approve` correctly waits for a `review-plan` critique. When the technical-lead
  role file changes, update `architecture.revision` (`verify-facts.sh` checks it). It predates
  P2-T5 (manifest v2 sections) and P4-T2 (`plan/design/*`); add those when a task needs them.
- `checks/`: the three approved gates (`api.py`, `ui.py`, `browser.py`). `browser.py`
  needs Python Playwright and contains a hardcoded browser-path fallback that P1-T4
  makes unnecessary.
- `solution/`: the app accepted and exported on 9 Nov (Go was not the stack then: this is
  stdlib Python + static files). It passed the 9 Nov checks only; it fails the checks
  revised during the P1-G gate (no `rev`, Host, Origin or security headers, ASCII-only
  case folding). Keep it as the app that really shipped with the CSRF hole (phase 3).
- `reference/`: a hand-written app that passes the current `checks/` (G_API, G_UI,
  G_BROWSER in the sandbox image, 19 Nov 2026). Use it as the known-good candidate for
  `prove-checks` (P3-T3); during P1-G each broken variant of it failed at the assertion
  `plan/acceptance.md` names for it. Update it with any change to `checks/`.
- `reviewer-replies/`: raw Claude reviewer outputs (`--output-format json`) whose
  `result` has a sentence before a fenced JSON block, which the current parser rejects;
  `approved-report.json` is the unwrapped verdict that was accepted.
