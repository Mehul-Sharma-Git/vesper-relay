---
name: backend-delivery
description: Use when API behavior, access checks, state transitions, persistence, schema, or retry semantics change.
---

# Backend delivery

Write the boundary contract with a concrete request, authorized actor,
response and failure before implementing. Enumerate invariants that must
hold across all paths. Put enforcement where the invariant lives: validate
shape at the boundary, authorize the object or tenant in the service, and
use a constraint or transaction to prevent races in storage. Map errors
at the edge. Keep domain policy readable independently of HTTP details.

| Risk | Required probe |
| --- | --- |
| Caller can supply an object ID | Use a valid ID owned by another principal and check both response and unchanged data. |
| Write can race or retry | Exercise concurrent writes or replay the same request; assert final durable state. |
| Migration reads old records | Upgrade representative existing data and verify old/new compatibility and recovery order. |
| List can grow | Check bounds, ordering tie-breakers, pagination boundaries, and the real query plan if relevant. |

Example: when marking an order shipped, verify the actor may modify that
order, update only an order in the permitted prior state, and persist the
transition and its event atomically. A competing transition must not
write a duplicate event. Return a stable conflict result instead of
leaking database error text.

Report the invariant, changed interface, migration/recovery sequence,
and evidence for success and denial or conflict. Escalate any changed
user-facing semantics or operational burden to the planner.
