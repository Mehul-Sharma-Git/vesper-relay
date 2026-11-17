# Vesper upgrade — Phase 4 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** The designer (top priority) produces distinctive, owner-directed design the frontend builds faithfully; backend, planner and tech lead work at senior level.
**Architecture:** Vesper's standard-library Python runner; changes follow `docs/plan/00-context.md`.
**Tech Stack:** Python 3.11+ standard library for the runner; projects Vesper builds use Go and React.
**Spec:** `docs/plan/phase-4-building-agents.md` (each task below names its section). The status board in `docs/plan/README.md` is the task-level source of truth; tick the steps here as you go and set the board status in the same PR.

## Global constraints
No third-party imports in the runner; never weaken plan digests, scope checks, read-only review copies, independent review, human-only approvals or the Git bridge; one task per session on its own branch; stop and ask on any conflict with `docs/plan/00-context.md`.

## Task P4-T1: Designer knowledge pack (content)
Depends on: P3-T2 · Size: L · Spec: `docs/plan/phase-4-building-agents.md`, section P4-T1

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P4-T1 and every file under its "Read first"
- [ ] Create branch `plan/p4-t1`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P4-T2: Designer tools and design artifacts
Depends on: P4-T1 · Size: M · Spec: `docs/plan/phase-4-building-agents.md`, section P4-T2

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P4-T2 and every file under its "Read first"
- [ ] Create branch `plan/p4-t2`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P4-T3: Design gates (tokens, anti-patterns, accessibility, fidelity)
Depends on: P4-T2 · Size: L · Spec: `docs/plan/phase-4-building-agents.md`, section P4-T3

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P4-T3 and every file under its "Read first"
- [ ] Create branch `plan/p4-t3`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P4-T4: Frontend role, skills and designer contract
Depends on: P4-T2 · Size: M · Spec: `docs/plan/phase-4-building-agents.md`, section P4-T4

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P4-T4 and every file under its "Read first"
- [ ] Create branch `plan/p4-t4`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P4-T5: Backend (Go) role and skills
Depends on: P3-G · Size: M · Spec: `docs/plan/phase-4-building-agents.md`, section P4-T5

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P4-T5 and every file under its "Read first"
- [ ] Create branch `plan/p4-t5`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P4-T6: Planner role, templates and estimates
Depends on: P2-T3, P3-G · Size: M · Spec: `docs/plan/phase-4-building-agents.md`, section P4-T6

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P4-T6 and every file under its "Read first"
- [ ] Create branch `plan/p4-t6`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P4-T7: Tech lead role, templates and hosting pack
Depends on: P3-G · Size: M · Spec: `docs/plan/phase-4-building-agents.md`, section P4-T7

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P4-T7 and every file under its "Read first"
- [ ] Create branch `plan/p4-t7`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P4-T8: Starter seeds: Vite app, Astro site, Go API
Depends on: P1-T6 · Size: M · Spec: `docs/plan/phase-4-building-agents.md`, section P4-T8

- [ ] Run `sh docs/plan/verify-facts.sh`; handle any DRIFT as `docs/plan/README.md` describes
- [ ] Read `docs/plan/00-context.md`, then task P4-T8 and every file under its "Read first"
- [ ] Create branch `plan/p4-t8`
- [ ] Write the failing tests listed under "Acceptance" and watch them fail
- [ ] Implement "Change"; respect "Do not"
- [ ] Run the README step-6 commands and the task's own acceptance commands; paste results in the PR
- [ ] Update the status board (and `verify-facts.sh` if a checked fact changed on purpose)

## Task P4-G: Phase 4 gate
Depends on: P4-T1..T8 · Size: M · Spec: `docs/plan/phase-4-building-agents.md`, section P4-G

- [ ] Confirm every task this gate depends on is `done` on the board
- [ ] Run the gate exactly as written in `docs/plan/phase-4-building-agents.md`
- [ ] Record results, elapsed time and plan usage in `docs/plan/appendix-b-test-run-evidence.md`
- [ ] Set the gate's board status (`done`, or `blocked` with the failing criterion)
