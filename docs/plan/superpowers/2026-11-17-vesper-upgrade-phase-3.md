# Vesper upgrade — Phase 3 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Every agent reasons in writing; QA owns checks proven to fail; the reviewer's blockers come with evidence.
**Architecture:** Vesper's standard-library Python runner; changes follow `docs/plan/00-context.md`.
**Tech Stack:** Python 3.11+ standard library for the runner; projects Vesper builds use Go and React.
**Spec:** `docs/plan/phase-3-verifying-agents.md` (each task below names its section). The status board in `docs/plan/README.md` is the task-level source of truth; tick the steps here as you go and set the board status in the same PR.

## Global constraints
No third-party imports in the runner; never weaken plan digests, scope checks, read-only review copies, independent review, human-only approvals or the Git bridge; one task per session on its own branch; stop and ask on any conflict with `docs/plan/00-context.md`.

## Task P3-T1: Shared agent foundation (reasoning note, claim labels, self-critique)
Depends on: P2-G · Size: M · Spec: `docs/plan/phase-3-verifying-agents.md`, section P3-T1

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P3-T1 and every file under its "Read first"
- [x] Create branch `plan/p3-t1`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P3-T2: Knowledge pack structure and `vesper kb` search
Depends on: P2-G · Size: M · Spec: `docs/plan/phase-3-verifying-agents.md`, section P3-T2

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P3-T2 and every file under its "Read first"
- [x] Create branch `plan/p3-t2`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P3-T3: QA owns checks; prove-it-fails self-test
Depends on: P3-T1 · Size: L · Spec: `docs/plan/phase-3-verifying-agents.md`, section P3-T3

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P3-T3 and every file under its "Read first"
- [x] Create branch `plan/p3-t3`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P3-T4: Reviewer: evidence-backed, multi-lens, calibration
Depends on: P3-T1 · Size: L · Spec: `docs/plan/phase-3-verifying-agents.md`, section P3-T4

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P3-T4 and every file under its "Read first"
- [x] Create branch `plan/p3-t4`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P3-T3b: Fold P2-G's accepted findings into the Pocket Todo gates
Depends on: P3-T3, P3-T4 · Size: L · Spec: `docs/plan/phase-3-verifying-agents.md`, section P3-T3b

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P3-T3b and every file under its "Read first"
- [x] Create branch `plan/p3-t3b-fold-findings`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P3-T5: Exploratory QA session
Depends on: P3-T3, P1-T10 · Size: M · Spec: `docs/plan/phase-3-verifying-agents.md`, section P3-T5

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P3-T5 and every file under its "Read first"
- [x] Create branch `plan/p3-t5`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P3-G: Phase 3 gate
Depends on: P3-T1..T5, P3-T3b · Size: S · Spec: `docs/plan/phase-3-verifying-agents.md`, section P3-G

- [ ] Confirm every task this gate depends on is `done` on the board
- [ ] Run the gate exactly as written in `docs/plan/phase-3-verifying-agents.md`
- [ ] Record results, elapsed time and plan usage in `docs/plan/appendix-b-test-run-evidence.md`
- [ ] Set the gate's board status (`done`, or `blocked` with the failing criterion)
