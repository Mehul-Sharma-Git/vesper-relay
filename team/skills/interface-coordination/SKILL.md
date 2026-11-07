---
name: interface-coordination
description: Use when several owners, deployment units, or jobs share an API, persisted state, schema migration, or integration invariant.
---

# Interface coordination

Define the seam before splitting work. Name the producer, consumers,
authoritative owner, and contract version. Include realistic examples
with absence and null where distinct, units, IDs, retry policy, and stable
error semantics. Have each side walk the same data through the flow.

| Seam | Decide together |
| --- | --- |
| Client and service | Does a conflict require correction, refresh, or safe retry? Who owns reconciliation? |
| Service and storage | Which invariant belongs in a transaction or constraint? What does old data look like? |
| Mixed deployment versions | Which order preserves reads and writes, when is the old field removed, and what can be rolled back? |
| Parallel implementation jobs | Which shared artifact is canonical? Which paths and checks does each job own? |

Example: for a money field, agree on integer minor units and currency,
and specify whether absent means unavailable or zero. Exercise a null
value and an old reader before changing writers. A signed-off JSON
example with a matching gate prevents each side from passing different
mocks.

Deliver one canonical contract, path and dependency ownership, an
end-to-end slice, integration evidence, and rollout and repair steps.
Escalate new services, data risk, cost, or user-visible tradeoffs to the
planner with the viable options.
