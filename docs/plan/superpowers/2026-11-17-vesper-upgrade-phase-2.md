# Vesper upgrade — Phase 2 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Reviewers see real evidence, only a human can approve, plans can't skip required thinking, nothing risky is lost, plan limits are respected.
**Architecture:** Vesper's standard-library Python runner; changes follow `docs/plan/00-context.md`.
**Tech Stack:** Python 3.11+ standard library for the runner; projects Vesper builds use Go and React.
**Spec:** `docs/plan/phase-2-evidence-and-control.md` (each task below names its section). The status board in `docs/plan/README.md` is the task-level source of truth; tick the steps here as you go and set the board status in the same PR.

## Global constraints
No third-party imports in the runner; never weaken plan digests, scope checks, read-only review copies, independent review, human-only approvals or the Git bridge; one task per session on its own branch; stop and ask on any conflict with `docs/plan/00-context.md`.

## Task P2-T1: Gate logs, scripts and artifacts in the review copy
Depends on: P1-G · Size: S · Spec: `docs/plan/phase-2-evidence-and-control.md`, section P2-T1

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P2-T1 and every file under its "Read first"
- [x] Create branch `plan/p2-t1`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P2-T2: Human-only approvals and a plain-language approval sheet, in every door
Depends on: P1-G · Size: L · Spec: `docs/plan/phase-2-evidence-and-control.md`, section P2-T2

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P2-T2 and every file under its "Read first"
- [x] Create branch `plan/p2-t2`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P2-T3: Usage ledger and plan-limit estimates
Depends on: P1-G · Size: M · Spec: `docs/plan/phase-2-evidence-and-control.md`, section P2-T3

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P2-T3 and every file under its "Read first"
- [x] Create branch `plan/p2-t3`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P2-T4: Limit-aware scheduling (pause and resume)
Depends on: P2-T3 · Size: M · Spec: `docs/plan/phase-2-evidence-and-control.md`, section P2-T4

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P2-T4 and every file under its "Read first"
- [x] Create branch `plan/p2-t4`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P2-T5: Required plan sections by depth (extend `planning.json`)
Depends on: P1-G · Size: M · Spec: `docs/plan/phase-2-evidence-and-control.md`, section P2-T5

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P2-T5 and every file under its "Read first"
- [x] Create branch `plan/p2-t5`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P2-T6: Additive checks after approval
Depends on: P1-G, P2-T2 · Size: M · Spec: `docs/plan/phase-2-evidence-and-control.md`, section P2-T6

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P2-T6 and every file under its "Read first"
- [x] Create branch `plan/p2-t6`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P2-T7: Advisory backlog and decision gate
Depends on: P1-G, P2-T2 · Size: M · Spec: `docs/plan/phase-2-evidence-and-control.md`, section P2-T7

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P2-T7 and every file under its "Read first"
- [x] Create branch `plan/p2-t7`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P2-G: Phase 2 gate
Depends on: P2-T1..T7 · Size: S · Spec: `docs/plan/phase-2-evidence-and-control.md`, section P2-G

- [x] Confirm every task this gate depends on is `done` on the board
- [x] Run the gate exactly as written in `docs/plan/phase-2-evidence-and-control.md`
- [x] Record results, elapsed time and plan usage in `docs/plan/appendix-b-test-run-evidence.md`
- [x] Set the gate's board status (`done`, or `blocked` with the failing criterion)
