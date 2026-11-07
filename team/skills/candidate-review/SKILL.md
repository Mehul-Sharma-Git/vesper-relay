---
name: candidate-review
description: Use when an independent reviewer receives a code candidate, approved scope, baseline, or check evidence for a technical verdict.
---

# Candidate review

Review the identified candidate against the approved baseline, writable
scope, and observable contract. Stay read-only. Read the whole change,
then follow shared dependencies and affected callers outside the diff.

| Check | Question to answer |
| --- | --- |
| Correctness | What observable behavior changes on valid, boundary, and error input? |
| Security | What new inputs or permissions can reach privileged operations? |
| Blast radius | Can shared state, configuration, migration, or deployment alter an unchanged caller? |
| Maintainability | What change creates ambiguity about ownership, invariant enforcement, or recovery? |
| Evidence | Did the required gate exercise this candidate and the meaningful failure mode? |

Use the smallest counterexample for each material issue. A finding like
“src/orders.ts:84, Blocker: lookup uses the request ID without account
scope; an authenticated user can cancel another account's order. Bind the
update to both order and account and exercise a foreign ID” is actionable.
“Add more tests” without a missed scenario is not.

Report blockers before advisories. Include path and line, trigger, impact,
and corrective direction or evidence needed. Separate inspected,
reproduced, and inferred claims; identify unreviewed areas. Send findings
to the planner and writers. An incomplete review or unrun required gate
cannot be presented as approval.
