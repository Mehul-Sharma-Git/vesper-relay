---
name: sqlite
description: Use when an approved SQLite application changes queries, schema, transactions, concurrent writes, or database-file handling.
---

# SQLite

Verify the deployed SQLite version and connection settings, not just the
development machine. Use bound parameters. Enable and check foreign-key
enforcement for each relevant connection before its transactions. Express
invariants in constraints and transactions so they hold across callers.

| Concern | Probe |
| --- | --- |
| Write contention | Use separate connections against the same temp file. Keep transactions short, bound busy waits or retries, and check the durable final state. |
| Constraint or schema change | Test an upgrade with populated legacy data, indexes and triggers. Check integrity and foreign-key violations after migrating. |
| WAL or database backup | Consider reader lifetime, checkpoints, sidecar files, and the actual filesystem. Use a supported backup path rather than copying only an active database file. |
| Query or pagination | Use representative cardinality, deterministic order with a tie-breaker, and inspect the query plan. |

Example: two writers try to reserve the last unit. Make the update
conditional on the remaining count inside the transaction, then confirm
one success and a clean conflict or bounded contention result. Testing
two independent in-memory connections would not exercise shared state.

Report engine and connection settings, migration or rollback order,
failure behavior, and actual results. See [SQLite documentation](https://sqlite.org/docs.html).
