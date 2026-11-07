---
name: acceptance-evidence
description: Use when drafting independent acceptance gates, reproducing a regression, or evaluating a candidate against approved checks.
---

# Acceptance evidence

Bind each required claim to one reproducible observation and keep the
verifier separate from the candidate. Set up controlled data, invoke a
supported user or service interface, and assert the actual result. A new
bug check should fail on the known baseline for the reported bug; capture
that failure independently of tool, fixture, and process errors.

Use these evidence fields: requirement ID, check ID, candidate identity,
environment, command, inputs, expected outcome, actual outcome,
pass/fail/blocked, and artifact or reproduction. For a UI scenario include
viewport, input mode, and state. Log environment or browser limitations
as such.

| Tempting shortcut | Better evidence |
| --- | --- |
| Assert a successful HTTP status | Read the resulting state; also show denied writes had no effect. |
| Wait a fixed interval for a local server | Poll the readiness condition under a bounded deadline; capture process errors. |
| Use a screenshot for keyboard behavior | Record the input sequence, actual focus target, and result. |
| Retry until green | Retain each outcome and investigate the intermittent failure. |

An approved gate is frozen. Run that gate or report blocked; never swap
fixtures, reduce scope, or change an assertion to accommodate a
candidate. Send a broken gate back to the planner with a proposed
correction and the effect on coverage. Resume after renewed approval.
