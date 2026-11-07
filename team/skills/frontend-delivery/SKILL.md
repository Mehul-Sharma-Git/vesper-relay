---
name: frontend-delivery
description: Use when a browser flow changes its controls, async state, responsive layout, or interaction with an API.
---

# Frontend delivery

Trace one interaction from input to UI state to transport and back. Reuse
existing tokens, primitives, and data boundaries. Favor plain semantic
markup and components that describe the product. Keep request handling
out of presentation and derive UI values rather than duplicating them.

| Failure mode | Implementation and evidence |
| --- | --- |
| Rapid filter or route changes | Cancel an obsolete read or ignore its response; reverse completion order in a test. |
| Loading, empty, or failed results look the same | Represent each separately; preserve a visible retry or correction path. |
| Resubmission after slow writes | Guard repeated actions; reconcile state from the response; test ambiguous transport failure with the contract owner. |
| Popup traps or loses focus | Verify real keyboard movement, Escape behavior where appropriate, and focus return. |
| Layout works on a single fixture | Test narrow and wide, long labels, zoom, touch, and no hover. |

Example: for a search field, keep the submitted filter and returned
records paired. After search A starts and search B starts, resolve B,
then A; the visible results and announced count must still describe B.
A mock of the request function alone does not establish browser behavior.

Return the route, state and input matrix, changed paths, actual checks,
and screenshots with dimensions and data where they add evidence. Flag
contract disagreements before writing a frontend-only workaround.
