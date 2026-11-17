# Vesper upgrade — Phase 5 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Connector and packaging, automatic repair up to a pull request, the evaluation bench, and the v1.0 release.
**Architecture:** Vesper's standard-library Python runner; changes follow `docs/plan/00-context.md`.
**Tech Stack:** Python 3.11+ standard library for the runner; projects Vesper builds use Go and React.
**Spec:** `docs/plan/phase-5-doors-repair-release.md` (each task below names its section). The status board in `docs/plan/README.md` is the task-level source of truth; tick the steps here as you go and set the board status in the same PR.

## Global constraints
No third-party imports in the runner; never weaken plan digests, scope checks, read-only review copies, independent review, human-only approvals or the Git bridge; one task per session on its own branch; stop and ask on any conflict with `docs/plan/00-context.md`.

## Task P5-T1: Local connector (MCP server)
Depends on: P2-T2, P4-G · Size: M · Spec: `docs/plan/phase-5-doors-repair-release.md`, section P5-T1

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P5-T1 and every file under its "Read first"
- [ ] Create branch `plan/p5-t1`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P5-T2: Packaging: Claude Code plugin, uv/pipx, sandbox image, `vesper open`
Depends on: P4-G · Size: M · Spec: `docs/plan/phase-5-doors-repair-release.md`, section P5-T2

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P5-T2 and every file under its "Read first"
- [ ] Create branch `plan/p5-t2`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P5-T3: Automatic repair loop up to a pull request
Depends on: P2-T2, P4-G · Size: L · Spec: `docs/plan/phase-5-doors-repair-release.md`, section P5-T3

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P5-T3 and every file under its "Read first"
- [ ] Create branch `plan/p5-t3`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P5-T4: Evaluation bench and scorecard
Depends on: P5-T1, P5-T2 · Size: L · Spec: `docs/plan/phase-5-doors-repair-release.md`, section P5-T4

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P5-T4 and every file under its "Read first"
- [ ] Create branch `plan/p5-t4`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P5-T5: Design bench with blind owner rating
Depends on: P5-T4 · Size: M · Spec: `docs/plan/phase-5-doors-repair-release.md`, section P5-T5

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P5-T5 and every file under its "Read first"
- [ ] Create branch `plan/p5-t5`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P5-T6: Release candidates, permission ladder, SETUP.md, v1.0
Depends on: P5-T3, P5-T5 · Size: M · Spec: `docs/plan/phase-5-doors-repair-release.md`, section P5-T6

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P5-T6 and every file under its "Read first"
- [ ] Create branch `plan/p5-t6`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)
