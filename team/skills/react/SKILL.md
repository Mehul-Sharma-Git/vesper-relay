---
name: react
description: Use when an existing or approved React implementation changes state, hooks, async rendering, routing, or component composition.
---

# React

Identify who owns each piece of state: server or cache, URL, form,
or local view. Prefer a single owner. Compute values from current props
and state; use effects to synchronize with an external system. Put
mutation requests caused by a user action in the event handler or the
project's existing mutation API.

| Symptom | Check |
| --- | --- |
| Form unexpectedly resets | Inspect component position and keys; change a key only for an intentional identity change. |
| Reordered rows inherit wrong input | Key rows by durable identity, not position. |
| State displays a prior request | Confirm cancellation or request identity in the existing data layer; resolve two reads in reverse order. |
| Effect duplicates subscriptions or work | Verify cleanup on remount and dependency changes; run under the project's development Strict Mode when available. |
| Server and client markup diverge | Keep the initial render deterministic; move browser-only dependencies to the correct boundary. |

Follow the existing router, query cache, and error boundary conventions.
Place loading and error states where the surrounding UI stays useful.
Add memoization only for a measured bottleneck or an established
referential contract. Verify user-visible behavior through rendered
controls and actual results. Do not select React for an unrelated stack
or add a parallel cache to fix one view.

See [React: You Might Not Need an Effect](https://react.dev/learn/you-might-not-need-an-effect).
