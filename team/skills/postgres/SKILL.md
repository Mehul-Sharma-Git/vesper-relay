---
name: postgres
description: Use when an approved PostgreSQL application changes relational constraints, migrations, indexing, transactions, privileges, or tenant policies.
---

# PostgreSQL

Identify the target PostgreSQL version, deployment roles, table sizes,
and transaction boundaries. Use parameterized statements and explicit
constraints. Choose isolation and locking from the invariant; validate
races with separate connections and make whole-transaction retries
bounded where the operation permits them.

| Concern | Probe |
| --- | --- |
| Schema change on an active table | Determine lock and rewrite impact for the exact statement and version. Test the upgrade on representative data and plan progress, timeouts, and recovery. |
| Large backfill or index | Separate compatibility rollout from removal; make backfills resumable. Check migration tool transaction handling before using concurrent index creation. |
| Row-level security or tenant scope | Run as the production application role, including a cross-tenant input. Test pooled connection handling and avoid privileged-role evidence. |
| Query performance | Check the actual plan with representative parameters and cardinality. Use execution analysis only in an approved environment; it can execute writes. |

Example: for a new required field, add it in a compatible shape, deploy
writers, backfill existing rows in bounded batches, then validate and
enforce the constraint. Confirm old readers still work during rollout
and document whether a forward repair is safer than reversal.

Report migration order, roles, lock assumptions, validation results, and
recovery procedure. See [PostgreSQL documentation](https://www.postgresql.org/docs/).
