# Vesper upgrade — Phase 1 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Automatic runs finish without manual help, in a real sandbox, with whichever AI the user has, for Go and React projects.
**Architecture:** Vesper's standard-library Python runner; changes follow `docs/plan/00-context.md`.
**Tech Stack:** Python 3.11+ standard library for the runner; projects Vesper builds use Go and React.
**Spec:** `docs/plan/phase-1-reliable-runs.md` (each task below names its section). The status board in `docs/plan/README.md` is the task-level source of truth; tick the steps here as you go and set the board status in the same PR.

## Global constraints
No third-party imports in the runner; never weaken plan digests, scope checks, read-only review copies, independent review, human-only approvals or the Git bridge; one task per session on its own branch; stop and ask on any conflict with `docs/plan/00-context.md`.

## Task P0-T1: Add plan folder and CLAUDE.md, confirm baseline is green
Depends on: none · Size: S · Spec: `docs/plan/phase-1-reliable-runs.md`, section P0-T1

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P0-T1 and every file under its "Read first"
- [ ] Create branch `plan/p0-t1`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T1: Robust reviewer report decoding
Depends on: P0-T1 · Size: S · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T1

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P1-T1 and every file under its "Read first"
- [x] Create branch `plan/p1-t1` (used `plan/p1-t1-report-decoding`)
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T2: Structured reviewer output (schema flags)
Depends on: P1-T1 · Size: S · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T2

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P1-T2 and every file under its "Read first"
- [x] Create branch `plan/p1-t2` (used `plan/p1-t2-structured-review-output`)
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T3: Configurable gate and reviewer limits
Depends on: P0-T1 · Size: S · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T3

- [x] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [x] Read `docs/plan/00-context.md`, then task P1-T3 and every file under its "Read first"
- [x] Create branch `plan/p1-t3`
- [x] Write the failing tests listed under "Acceptance" and watch them fail
- [x] Implement "Change"; respect "Do not"
- [x] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [x] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T4: Gate environment pass-through
Depends on: P0-T1 · Size: S · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T4

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P1-T4 and every file under its "Read first"
- [ ] Create branch `plan/p1-t4`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T5: Command gates (any language)
Depends on: P1-T3 · Size: M · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T5

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P1-T5 and every file under its "Read first"
- [ ] Create branch `plan/p1-t5`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T6: Toolchain support: setup step and ignored build dirs
Depends on: P1-T5 · Size: L · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T6

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P1-T6 and every file under its "Read first"
- [ ] Create branch `plan/p1-t6`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T7: Config files: personal + project, `config show`
Depends on: P0-T1 · Size: M · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T7

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P1-T7 and every file under its "Read first"
- [ ] Create branch `plan/p1-t7`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T8: Brain adapter interface: Claude Code, Codex, Gemini CLI
Depends on: P1-T2, P1-T7 · Size: L · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T8

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P1-T8 and every file under its "Read first"
- [ ] Create branch `plan/p1-t8`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T9: Pluggable sandbox: Docker and Podman backends, selftest
Depends on: P1-T5, P1-T8 · Size: L · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T9

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P1-T9 and every file under its "Read first"
- [ ] Create branch `plan/p1-t9`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T10: Worker tool layer (shell only inside the sandbox)
Depends on: P1-T9 · Size: M · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T10

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P1-T10 and every file under its "Read first"
- [ ] Create branch `plan/p1-t10`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-T11: `vesper setup` wizard and `vesper doctor`
Depends on: P1-T9 · Size: M · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-T11

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P1-T11 and every file under its "Read first"
- [ ] Create branch `plan/p1-t11`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P1-G: Phase 1 gate: Pocket Todo unattended in the sandbox with one AI
Depends on: P1-T1..T11 · Size: M · Spec: `docs/plan/phase-1-reliable-runs.md`, section P1-G

- [ ] Confirm every task this gate depends on is `done` on the board
- [ ] Run the gate exactly as written in `docs/plan/phase-1-reliable-runs.md`
- [ ] Record results, elapsed time and plan usage in `docs/plan/appendix-b-test-run-evidence.md`
- [ ] Set the gate's board status (`done`, or `blocked` with the failing criterion)
