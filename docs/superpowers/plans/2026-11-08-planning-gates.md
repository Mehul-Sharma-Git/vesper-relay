# Impact-based planning gates Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Enforce the user-approved architecture and critique policy for new runs without changing old approvals.
**Architecture:** A versioned planning manifest uses existing plan inventories and profile revisions. A separate reviewer receipt binds to the packet; the approval digest includes that receipt. Narrow fixes record a justified skip.
**Tech Stack:** Python standard library; optional external evaluation providers.
**Spec:** User approval recorded below.

## Approved scope
New systems and material data/security/integration/deployment changes require full architecture and critique. Routine cross-layer changes require a short note and focused critique. Narrow established-pattern fixes may justify skipping both. Retain technical-lead as architecture owner and separate reviewer. Material revisions require fresh review. Existing approvals remain resumable; local branch only.

## Global constraints
No runner dependencies, automatic publishing, permission expansion or edits to the old checkout. Model quality and launcher confinement must not be inferred from fixtures.

## Review focus
- Changed checks or seed invalidate critique (Task 1).
- Backend-only security changes cannot choose skip (Task 1).
- Author cannot attest their own plan review (Task 1).
- Legacy frozen approval resumes without new fields (Task 1).
- Product/setup failures must not become source commits (Task 3).

## Task 1: Planning enforcement
- [ ] Add failing tests for impact routing, missing handoff, independent critique, stale approval, narrow skip and legacy compatibility.
- [ ] Add builder/planning.py; integrate review_bundle, Runner.approve and review-plan CLI; mark new managed and init runs with planning version.
- [ ] Update existing fixture plans with explicit narrow scope; update role and entry-point docs.
- [ ] Run focused and complete suites and both replays; commit reviewed slice locally.

## Task 2: Isolated evaluations
- [ ] Generate catalog coverage, matched specialist/control trials and blind grading artifacts with optional provider execution.
- [ ] Exercise deterministic harness invariants; execute available live trials without claiming fixture scores as quality evidence.
- [ ] Record per-profile coverage and unavailable live/database/client evidence.

## Task 3: Controlled repair proof
- [ ] Reproduce specific diagnosis weakness before modifying repair code.
- [ ] Add typed reproduction evidence and negative controls with compatibility for approved runs.
- [ ] Inject a real coordinator defect in a disposable clone, review bounded fix, commit exact tree, replay original workflow in fresh checkout.
- [ ] Run full checks and fresh branch review, address blockers and report limitations.

## Ledger
Baseline: 28/28 tests passed (Python 3.9.6 on host; documented supported minimum is 3.11). Both replays and 4 Chromium tests passed outside restricted loopback environment. RC1 CI Ubuntu/browser pass; macOS readiness timeout remains unexplained.
Ruling: Use an explicit impact declaration rather than infer meaning from filenames; semantic truth is reviewed by critic/user. Declared session identities support independent-review checks, not authentication against a malicious operator.
