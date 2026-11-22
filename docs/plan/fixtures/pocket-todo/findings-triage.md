# Pocket Todo: P2-G's accepted findings, triaged (P3-T3b)

The owner accepted 169 findings as risks in the four P2-G Pocket Todo runs (`p2g-accepted-findings.json`). Each is decided once, by group, as one of:

- **check**: the plan already promises the behaviour (api-contract.md, design.md, architecture.md, acceptance.md, decisions.md), or it is a threat the plan defends (decisions.md threat model), and a plausible wrong build passed every gate. The gate now fails on it; the cited message is the assertion's failure message (a tests/ path names a unit test).
- **covered**: an existing assertion already failed on it.
- **risk**: the actor is trusted or outside the threat model (A9, A11-A13, C5, C6, C8, physical access), or the plan does not specify the behaviour, so it needs an owner decision first. It stays an accepted risk; the reason cites the item.

Result: 92 findings in 27 groups became checks, 77 in 23 groups stay risks. `tests/test_pocket_todo_triage.py` checks that every exported finding appears exactly once below, that each group is decided once, and that every cited message is in its gate.

## Groups

| Group | What the findings say | Decision | Assertion (gate: failure message) or reason | Notes |
| --- | --- | --- | --- | --- |
| T01 | Phone mode: the default bind, `--host 0.0.0.0`, and a LAN address as Host | check | G_API: "the default bind must be loopback only (127.0.0.1)"; G_API: "--host 0.0.0.0 must listen beyond loopback"; G_API: "a LAN address Host must be served"; G_API: "a same-origin write from the phone's LAN address must succeed" | The bind checks probe 127.0.0.2, which Linux (the sandbox) routes to loopback and macOS does not; there they are skipped. The owner's own laptop runtime and phone are T12. |
| T02 | Which interfaces `--host 0.0.0.0` exposes (VPN, Ethernet, guest network, forwarded port) | risk | A9: with --host 0.0.0.0 every device that can reach the laptop is trusted (decisions.md threat model); the network boundary is the owner's setup, not the app's |  |
| T03 | Owner must confirm A9 (home Wi-Fi devices have full access) | risk | A9: a proposed risk the owner accepts by approving the plan (architecture.md, decisions.md threat model) |  |
| T04 | Owner must confirm A11 (local programs and accounts on the loopback port); A10 covers only the file | risk | A11: local programs and accounts using the loopback port are trusted (decisions.md threat model); A10 defends the database file |  |
| T05 | Owner must confirm A12 (watching, altering or flooding home-network traffic) | risk | A12: outside the threat model (decisions.md); no TLS in v1 |  |
| T06 | Owner must confirm A13 (old content on the same origin) | risk | A13: outside the threat model (decisions.md); give Pocket Todo its own port |  |
| T07 | Owner must confirm C5 (last write wins for renames and ticks) | risk | C5: a proposed risk (architecture.md): one owner, only a name or a tick is overwritten |  |
| T08 | Owner must confirm C6 (a retried Add after a lost reply makes a duplicate) | risk | C6: a proposed risk (architecture.md): the UI never retries by itself (gated in T25); a duplicate is visible and deletable |  |
| T09 | Owner must confirm C8 (two servers on one database) | risk | C8: not supported, run one server per database file (product.md, architecture.md) |  |
| T10 | Physical access, trusted browser and devices, one copy with no backup, no undo | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted; D3: the data lives on the laptop; D4: a confirmed list delete removes its todos |  |
| T11 | Where the database lives (relative `--db`, re-exports, backups) | risk | product.md: the owner runs python3 server.py --db todos.sqlite3 from the exported folder; where the data lives and its backup are the owner's (D3) |  |
| T12 | The owner's devices: Python, firewall, Wi-Fi isolation, the phone's browser | risk | planning.json assumptions: the owner opens http://<laptop IP>:8080 on the phone at first use; decisions.md Open/risks: phone access depends on the firewall |  |
| T13 | Who runs the final gates and checks the export | risk | Outside the fixture's gates (contract.json): Vesper runs every gate on the last job and exports that accepted snapshot; J_API's goal says the static files may be absent, and G_API accepts a 404 for them |  |
| T14 | Drawer (wireframe) or panel under the bar (handoff) | risk | design.md is the handoff J_UI builds from (contract.json: the exact ids and labels in design.md); the wireframe is illustrative, and focus containment or outside dismissal is not specified |  |
| T15 | Two failure-path matrices (acceptance.md, planning.json) drift apart; C1 names the wrong record | check | tests/test_pocket_todo_triage.py: "acceptance.md and failure_paths have different rows"; tests/test_pocket_todo_triage.py: "renames the list" | planning.json's failure_paths now mirror acceptance.md row for row (a unit test, not a gate). |
| T16 | The gate harness: assertions on, exact READY line, no redirects or proxies, server output drained | check | G_API: "assertions are disabled"; G_API: "Startup failed"; G_API: "Unexpected redirect" | Recording the gate sources, candidate and command is Vesper's (plan digests, gate logs in the review copy, P2-T1). |
| T17 | The page loads only local assets, has no inline script or style, and has the filters (R4) | check | G_UI: "Only local assets"; G_UI: "No inline script"; G_UI: "No inline style or handlers"; G_UI: "Filters need"; G_UI: "#rename-list (design.md)"; G_BROWSER: "Only local assets: the page requested" |  |
| T18 | Accessibility on the phone: visible labels, keyboard menu, focus ring, 44px targets, closed menu | check | G_BROWSER: "the New todo label is visible"; G_BROWSER: "the menu opens from the keyboard"; G_BROWSER: "Keyboard focus must be visible"; G_BROWSER: "Touch targets must be at least 44px"; G_BROWSER: "the phone menu starts closed" |  |
| T19 | The laptop layout and the 720px breakpoint: filters, reopen, rename, delete | check | G_BROWSER: "below 720px the list toggle shows"; G_BROWSER: "from 720px the sidebar shows"; G_BROWSER: "laptop: the Active filter hides done todos"; G_BROWSER: "laptop: reopening a todo must reach the server"; G_BROWSER: "laptop: a rename must reach the server"; G_BROWSER: "laptop: Cancel must not send a delete"; G_BROWSER: "laptop: deleting a todo must not ask for confirmation" |  |
| T20 | List controls: Enter submits New list, Add list keeps the list and menu, Inbox hides Rename, an empty title | check | G_BROWSER: "Enter in New list adds the list"; G_BROWSER: "Add list keeps the current list"; G_BROWSER: "Add list keeps the phone menu open"; G_BROWSER: "Inbox shows no Rename list"; G_BROWSER: "An empty title must not be sent" | design.md names no wording for an empty filter result, so only an empty title's message is checked. |
| T21 | Acting on what another device deleted: Delete todo, choosing a list, ticking in a deleted list, rename drafts | check | G_BROWSER: "a todo another device deleted disappears when its Delete is clicked"; G_BROWSER: "the recovery reloads the list"; G_BROWSER: "choosing a list another device deleted falls back to Inbox"; G_BROWSER: "ticking a todo whose list another device deleted falls back to Inbox"; G_BROWSER: "the typed rename is kept after a 404"; G_BROWSER: "the typed rename is kept after a 409" | Each step clears the status region first, so the announcement is new. Where a kept rename draft is offered after switching lists is not specified (T28). |
| T22 | A list name stays text on every surface (toggle, heading, rename, status) | check | G_BROWSER: "A list name was inserted as markup"; G_BROWSER: "A list name ran as markup" |  |
| T23 | The delete dialog's name, count and revision come from one snapshot | check | G_BROWSER: "Confirmation must name the list and its todo count" | The dialog now opens under the Active filter with the list's one todo done, so its count must be the list's total; the C1 row already checks the revision sent and the next dialog's new count. |
| T24 | An older reply never shows under a newer filter (C7's latest-request rule) | check | G_BROWSER: "an older filter reply never shows under a newer filter" | A late list refresh overwriting counts is not specified beyond C7. |
| T25 | A failed Add keeps the draft, says so, and is never retried by the UI | check | G_BROWSER: "a failed Add keeps the draft"; G_BROWSER: "A failed Add must be sent once, never retried" | An unknown outcome (the reply lost after a commit) and a failed refresh after a success are not specified (C6, T27). |
| T26 | Pending writes across list switches, new typing, double submission and rerendered controls | risk | design.md defines no pending-write behaviour beyond C7 (the latest read wins); a double submission is a visible duplicate (C6) |  |
| T27 | Unknown write outcomes and failed recovery reads | risk | design.md States gives a network failure a kept draft and a message (gated in T25); recovery after a failed reload and wording for an unknown outcome are not specified; a retried write is C6 |  |
| T28 | A rename draft for a list that vanished while the owner switched lists | risk | design.md keeps the typed text in #rename-list (gated in T21); where a draft for a vanished list is recovered after switching lists is not specified |  |
| T29 | Where focus goes when the focused control disappears | risk | design.md Accessibility asks for visible focus and a keyboard-reachable menu (gated in T18); a focus destination after removal is not specified |  |
| T30 | Choosing another list while a confirmed list delete is pending | risk | design.md: confirming Delete list makes Inbox current; choosing another list while the delete is pending is not specified |  |
| T31 | Client-side trimming (U+FEFF) and UTF-16 lengths | risk | api-contract.md: the server trims and counts and is authoritative; the UI's only validation is the empty-title message (design.md States) |  |
| T32 | A 40-character unbroken name at 320px | check | G_BROWSER: "with a 40-character list name" |  |
| T33 | Inbox's own name is taken in every casing; one Inbox after a restart | check | G_API: "duplicates Inbox"; G_API: "a rename to Inbox"; G_API: "one Inbox" |  |
| T34 | Malformed ids and parameters never crash and change nothing | check | G_API: "malformed input must get a 4xx, not"; G_API: "a malformed request changed data or a revision"; G_API: "a current revision with leading zeros is still the current revision"; G_API: "a huge Content-Length is oversized (413)" | The contract fixes no status for these beyond a refusal, so any 4xx passes; an omitted status (all) and repeated parameters are not specified. |
| T35 | Name rules: full case folding, folded ordering, inclusive limits, rename validation | check | G_API: "names compare by casefold(), not lower()"; G_API: "order by folded name"; G_API: "a 40-character list name must be accepted"; G_API: "a 200-character title must be accepted"; G_API: "a rename trims the name"; G_API: "rename length" | Oldest-first order was already checked (Buy milk, then Call bank); ties within one millisecond have no observable wrong build. |
| T36 | Every reply's row shape and types; 204 replies are empty | check | G_API: "row shape"; G_API: "a 204 reply has an empty body" |  |
| T37 | Revisions start at 1 and rise by exactly one; a PATCH persists | check | G_API: "a revision starts at 1"; G_API: "a rename raises the revision by exactly one"; G_API: "an add raises the revision by exactly one"; G_API: "a todo delete raises the revision by exactly one"; G_API: "must persist, found" |  |
| T38 | Apostrophes, quotes and SQL-looking text round-trip (bound parameters) | check | G_API: "punctuation must round-trip" |  |
| T39 | Stored data: the cascade on disk, a full restart, ids retired across a restart | check | G_API: "the deleted list's todos are still in the database"; G_API: "a restart changed lists, todos, ids or revisions"; G_API: "a deleted maximum list id was reused after a restart" |  |
| T40 | Racing writes: an add against a stale delete; two devices taking one name | check | G_API: "an add raced a delete with the older revision"; G_API: "two devices created the same name at once"; G_API: "racing writes left todos without a list" | 25 rounds of each race; a correct server never fails them. Retrying after a lost reply is C6. |
| T41 | A full, corrupt or externally locked database | risk | architecture.md specifies no behaviour for these: an outside lock is a local program (A11) or a second server (C8), and disk failure is physical (threat model) |  |
| T42 | Database file modes: an existing permissive database, journals during writes | check | G_API: "is readable by others"; G_API: "an existing database others could read must be made owner-only at startup"; G_API: "after writes" | The parent directory's owner and links in the path are A11 (local accounts) and stay outside. |
| T43 | Only the three assets are served, in the documented layout, for GET and HEAD | check | G_API: "only /, /app.js and /styles.css are served"; G_API: "checks Host" | The app runs from a copy of the candidate with --db todos.sqlite3 next to server.py and inert files beside it. Links are T44. |
| T44 | An asset or the database reached through a link or an aliasing `--db` path | risk | A11 and the threat model: a link or a --db path in the app folder is set by someone with access to the owner's files; A7 is gated for the documented layout (T43) |  |
| T45 | Every response path carries the exact CSP, one of each header, no CORS, and JSON errors | check | G_API: "the CSP must be exactly default-src 'self'; frame-ancestors 'none'"; G_API: "one Content-Security-Policy header"; G_API: "sends a CORS header"; G_API: "error shape" | Covers assets, reads, 201, 200, 204, 409, a preflight, other methods and every refusal. The browser enforces these headers itself (a trusted browser, T10). |
| T46 | Host and Origin strictness: real addresses, every method, a hidden second Host, two Origins | check | G_API: "is not an IP address: 403"; G_API: "every method checks Host"; G_API: "a malformed header block must be refused, not served"; G_API: "two Origin headers on"; G_API: "a LAN address Host must be served" | A missing Origin stays allowed (api-contract.md: direct clients); browsers send one on cross-site writes. |
| T47 | What another site can infer (timing, load errors, top-level navigation) | risk | api-contract.md promises other websites cannot read, change or frame the app (gated: A2-A5); inference and navigation are not in the threat model's defended list and need the owner's decision |  |
| T48 | Bodies and framing: empty, invalid UTF-8, nested, surrogates, huge integers, chunked, two lengths, short, the 64 KB edge, a stalled body | check | G_API: "malformed input must get a 4xx, not"; G_API: "malformed framing must get a 4xx"; G_API: "a 64,000-byte body is within the limit"; G_API: "65,537 bytes is over the limit"; G_API: "a stalled request blocked another client" | 64 KB read as 64,000 or 65,536 bytes: both accept 64,000 and refuse 65,537. A slow trickle is T50. |
| T49 | The parser's own replies and malformed request targets | check | G_API: "the parser's own error reply must be framed HTTP"; G_API: "a malformed request target must get a 4xx" | `//health` reaches /health because Python's own parser folds the slashes; it is the same route with the same checks. |
| T50 | A slowly trickled body, and a DELETE whose declared body never arrives | risk | A12 (slowing the app is outside the threat model) and A9/A11 (a client that reaches the port already has full access); a browser sends whole bodies, and T48 gates that a stalled request does not stop another device |  |

## Findings

One row per exported finding: the run, its finding id, the group, the decision, and the group's first assertion or its reason.

| Run | Finding | Group | Decision | Assertion or reason |
| --- | --- | --- | --- | --- |
| 2026-11-20 run 1 | F1 | T01 | check | G_API: "the default bind must be loopback only (127.0.0.1)" (and the group's others) |
| 2026-11-20 run 1 | F2 | T01 | check | G_API: "the default bind must be loopback only (127.0.0.1)" (and the group's others) |
| 2026-11-20 run 1 | F3 | T17 | check | G_UI: "Only local assets" (and the group's others) |
| 2026-11-20 run 1 | F4 | T21 | check | G_BROWSER: "a todo another device deleted disappears when its Delete is clicked" (and the group's others) |
| 2026-11-20 run 1 | F5 | T33 | check | G_API: "duplicates Inbox" (and the group's others) |
| 2026-11-20 run 1 | F6 | T34 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-20 run 1 | F7 | T40 | check | G_API: "an add raced a delete with the older revision" (and the group's others) |
| 2026-11-20 run 1 | F10 | T48 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-20 run 1 | F11 | T42 | check | G_API: "is readable by others" (and the group's others) |
| 2026-11-20 run 1 | F14 | T03 | risk | A9: a proposed risk the owner accepts by approving the plan (architecture.md, decisions.md threat model) |
| 2026-11-20 run 1 | F15 | T04 | risk | A11: local programs and accounts using the loopback port are trusted (decisions.md threat model) |
| 2026-11-20 run 1 | F16 | T05 | risk | A12: outside the threat model (decisions.md) |
| 2026-11-20 run 1 | F17 | T06 | risk | A13: outside the threat model (decisions.md) |
| 2026-11-20 run 1 | F18 | T07 | risk | C5: a proposed risk (architecture.md): one owner, only a name or a tick is overwritten |
| 2026-11-20 run 1 | F19 | T25 | check | G_BROWSER: "a failed Add keeps the draft" (and the group's others) |
| 2026-11-20 run 1 | F20 | T09 | risk | C8: not supported, run one server per database file (product.md, architecture.md) |
| 2026-11-20 run 1 | F21 | T10 | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted |
| 2026-11-20 run 3 | F1 | T02 | risk | A9: with --host 0.0.0.0 every device that can reach the laptop is trusted (decisions.md threat model) |
| 2026-11-20 run 3 | F2 | T05 | risk | A12: outside the threat model (decisions.md) |
| 2026-11-20 run 3 | F3 | T42 | check | G_API: "is readable by others" (and the group's others) |
| 2026-11-20 run 3 | F4 | T43 | check | G_API: "only /, /app.js and /styles.css are served" (and the group's others) |
| 2026-11-20 run 3 | F5 | T48 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-20 run 3 | F6 | T45 | check | G_API: "the CSP must be exactly default-src 'self'; frame-ancestors 'none'" (and the group's others) |
| 2026-11-20 run 3 | F7 | T46 | check | G_API: "is not an IP address: 403" (and the group's others) |
| 2026-11-20 run 3 | F8 | T47 | risk | api-contract.md promises other websites cannot read, change or frame the app (gated: A2-A5) |
| 2026-11-20 run 3 | F9 | T38 | check | G_API: "punctuation must round-trip" (and the group's others) |
| 2026-11-20 run 3 | F10 | T48 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-20 run 3 | F11 | T34 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-20 run 3 | F12 | T35 | check | G_API: "names compare by casefold(), not lower()" (and the group's others) |
| 2026-11-20 run 3 | F13 | T37 | check | G_API: "a revision starts at 1" (and the group's others) |
| 2026-11-20 run 3 | F14 | T39 | check | G_API: "the deleted list's todos are still in the database" (and the group's others) |
| 2026-11-20 run 3 | F15 | T39 | check | G_API: "the deleted list's todos are still in the database" (and the group's others) |
| 2026-11-20 run 3 | F16 | T40 | check | G_API: "an add raced a delete with the older revision" (and the group's others) |
| 2026-11-20 run 3 | F17 | T41 | risk | architecture.md specifies no behaviour for these: an outside lock is a local program (A11) or a second server (C8), and disk failure is physical (threat model) |
| 2026-11-20 run 3 | F18 | T23 | check | G_BROWSER: "Confirmation must name the list and its todo count" (and the group's others) |
| 2026-11-20 run 3 | F19 | T26 | risk | design.md defines no pending-write behaviour beyond C7 (the latest read wins) |
| 2026-11-20 run 3 | F20 | T21 | check | G_BROWSER: "a todo another device deleted disappears when its Delete is clicked" (and the group's others) |
| 2026-11-20 run 3 | F21 | T40 | check | G_API: "an add raced a delete with the older revision" (and the group's others) |
| 2026-11-20 run 3 | F22 | T25 | check | G_BROWSER: "a failed Add keeps the draft" (and the group's others) |
| 2026-11-20 run 3 | F23 | T19 | check | G_BROWSER: "below 720px the list toggle shows" (and the group's others) |
| 2026-11-20 run 3 | F24 | T18 | check | G_BROWSER: "the New todo label is visible" (and the group's others) |
| 2026-11-20 run 3 | F25 | T22 | check | G_BROWSER: "A list name was inserted as markup" (and the group's others) |
| 2026-11-20 run 3 | F26 | T21 | check | G_BROWSER: "a todo another device deleted disappears when its Delete is clicked" (and the group's others) |
| 2026-11-20 run 3 | F27 | T12 | risk | planning.json assumptions: the owner opens http://<laptop IP>:8080 on the phone at first use |
| 2026-11-20 run 3 | F28 | T11 | risk | product.md: the owner runs python3 server.py --db todos.sqlite3 from the exported folder |
| 2026-11-20 run 3 | F29 | T16 | check | G_API: "assertions are disabled" (and the group's others) |
| 2026-11-20 run 3 | F30 | T15 | check | tests/test_pocket_todo_triage.py: "acceptance.md and failure_paths have different rows" (and the group's others) |
| 2026-11-20 run 3 | F31 | T13 | risk | Outside the fixture's gates (contract.json): Vesper runs every gate on the last job and exports that accepted snapshot |
| 2026-11-20 run 3 | F32 | T14 | risk | design.md is the handoff J_UI builds from (contract.json: the exact ids and labels in design.md) |
| 2026-11-20 run 3 | F33 | T03 | risk | A9: a proposed risk the owner accepts by approving the plan (architecture.md, decisions.md threat model) |
| 2026-11-20 run 3 | F34 | T04 | risk | A11: local programs and accounts using the loopback port are trusted (decisions.md threat model) |
| 2026-11-20 run 3 | F35 | T05 | risk | A12: outside the threat model (decisions.md) |
| 2026-11-20 run 3 | F36 | T06 | risk | A13: outside the threat model (decisions.md) |
| 2026-11-20 run 3 | F37 | T10 | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted |
| 2026-11-20 run 3 | F38 | T10 | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted |
| 2026-11-20 run 3 | F39 | T07 | risk | C5: a proposed risk (architecture.md): one owner, only a name or a tick is overwritten |
| 2026-11-20 run 3 | F40 | T08 | risk | C6: a proposed risk (architecture.md): the UI never retries by itself (gated in T25) |
| 2026-11-20 run 3 | F41 | T09 | risk | C8: not supported, run one server per database file (product.md, architecture.md) |
| 2026-11-20 run 3 | F42 | T10 | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted |
| 2026-11-20 run 3 | F43 | T10 | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted |
| 2026-11-20 run 3 | F57 | T49 | check | G_API: "the parser's own error reply must be framed HTTP" (and the group's others) |
| 2026-11-20 run 3 | F58 | T49 | check | G_API: "the parser's own error reply must be framed HTTP" (and the group's others) |
| 2026-11-20 run 3 | F68 | T21 | check | G_BROWSER: "a todo another device deleted disappears when its Delete is clicked" (and the group's others) |
| 2026-11-20 run 3 | F69 | T28 | risk | design.md keeps the typed text in #rename-list (gated in T21) |
| 2026-11-20 run 3 | F70 | T27 | risk | design.md States gives a network failure a kept draft and a message (gated in T25) |
| 2026-11-20 run 3 | F71 | T26 | risk | design.md defines no pending-write behaviour beyond C7 (the latest read wins) |
| 2026-11-20 run 3 | F72 | T27 | risk | design.md States gives a network failure a kept draft and a message (gated in T25) |
| 2026-11-21 run C | F1 | T02 | risk | A9: with --host 0.0.0.0 every device that can reach the laptop is trusted (decisions.md threat model) |
| 2026-11-21 run C | F2 | T04 | risk | A11: local programs and accounts using the loopback port are trusted (decisions.md threat model) |
| 2026-11-21 run C | F3 | T01 | check | G_API: "the default bind must be loopback only (127.0.0.1)" (and the group's others) |
| 2026-11-21 run C | F4 | T13 | risk | Outside the fixture's gates (contract.json): Vesper runs every gate on the last job and exports that accepted snapshot |
| 2026-11-21 run C | F5 | T46 | check | G_API: "is not an IP address: 403" (and the group's others) |
| 2026-11-21 run C | F6 | T45 | check | G_API: "the CSP must be exactly default-src 'self'; frame-ancestors 'none'" (and the group's others) |
| 2026-11-21 run C | F7 | T48 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-21 run C | F8 | T42 | check | G_API: "is readable by others" (and the group's others) |
| 2026-11-21 run C | F9 | T44 | risk | A11 and the threat model: a link or a --db path in the app folder is set by someone with access to the owner's files |
| 2026-11-21 run C | F10 | T17 | check | G_UI: "Only local assets" (and the group's others) |
| 2026-11-21 run C | F11 | T22 | check | G_BROWSER: "A list name was inserted as markup" (and the group's others) |
| 2026-11-21 run C | F12 | T47 | risk | api-contract.md promises other websites cannot read, change or frame the app (gated: A2-A5) |
| 2026-11-21 run C | F13 | T40 | check | G_API: "an add raced a delete with the older revision" (and the group's others) |
| 2026-11-21 run C | F14 | T23 | check | G_BROWSER: "Confirmation must name the list and its todo count" (and the group's others) |
| 2026-11-21 run C | F15 | T26 | risk | design.md defines no pending-write behaviour beyond C7 (the latest read wins) |
| 2026-11-21 run C | F16 | T24 | check | G_BROWSER: "an older filter reply never shows under a newer filter" (and the group's others) |
| 2026-11-21 run C | F17 | T21 | check | G_BROWSER: "a todo another device deleted disappears when its Delete is clicked" (and the group's others) |
| 2026-11-21 run C | F18 | T21 | check | G_BROWSER: "a todo another device deleted disappears when its Delete is clicked" (and the group's others) |
| 2026-11-21 run C | F19 | T25 | check | G_BROWSER: "a failed Add keeps the draft" (and the group's others) |
| 2026-11-21 run C | F20 | T41 | risk | architecture.md specifies no behaviour for these: an outside lock is a local program (A11) or a second server (C8), and disk failure is physical (threat model) |
| 2026-11-21 run C | F21 | T11 | risk | product.md: the owner runs python3 server.py --db todos.sqlite3 from the exported folder |
| 2026-11-21 run C | F22 | T37 | check | G_API: "a revision starts at 1" (and the group's others) |
| 2026-11-21 run C | F23 | T35 | check | G_API: "names compare by casefold(), not lower()" (and the group's others) |
| 2026-11-21 run C | F24 | T34 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-21 run C | F25 | T36 | check | G_API: "row shape" (and the group's others) |
| 2026-11-21 run C | F26 | T19 | check | G_BROWSER: "below 720px the list toggle shows" (and the group's others) |
| 2026-11-21 run C | F27 | T18 | check | G_BROWSER: "the New todo label is visible" (and the group's others) |
| 2026-11-21 run C | F28 | T20 | check | G_BROWSER: "Enter in New list adds the list" (and the group's others) |
| 2026-11-21 run C | F29 | T40 | check | G_API: "an add raced a delete with the older revision" (and the group's others) |
| 2026-11-21 run C | F30 | T39 | check | G_API: "the deleted list's todos are still in the database" (and the group's others) |
| 2026-11-21 run C | F31 | T15 | check | tests/test_pocket_todo_triage.py: "acceptance.md and failure_paths have different rows" (and the group's others) |
| 2026-11-21 run C | F32 | T16 | check | G_API: "assertions are disabled" (and the group's others) |
| 2026-11-21 run C | F33 | T03 | risk | A9: a proposed risk the owner accepts by approving the plan (architecture.md, decisions.md threat model) |
| 2026-11-21 run C | F34 | T04 | risk | A11: local programs and accounts using the loopback port are trusted (decisions.md threat model) |
| 2026-11-21 run C | F35 | T05 | risk | A12: outside the threat model (decisions.md) |
| 2026-11-21 run C | F36 | T06 | risk | A13: outside the threat model (decisions.md) |
| 2026-11-21 run C | F37 | T10 | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted |
| 2026-11-21 run C | F38 | T10 | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted |
| 2026-11-21 run C | F39 | T07 | risk | C5: a proposed risk (architecture.md): one owner, only a name or a tick is overwritten |
| 2026-11-21 run C | F40 | T08 | risk | C6: a proposed risk (architecture.md): the UI never retries by itself (gated in T25) |
| 2026-11-21 run C | F41 | T09 | risk | C8: not supported, run one server per database file (product.md, architecture.md) |
| 2026-11-21 run C | F57 | T46 | check | G_API: "is not an IP address: 403" (and the group's others) |
| 2026-11-21 run C | F58 | T50 | risk | A12 (slowing the app is outside the threat model) and A9/A11 (a client that reaches the port already has full access) |
| 2026-11-21 run C | F59 | T46 | check | G_API: "is not an IP address: 403" (and the group's others) |
| 2026-11-21 run C | F60 | T49 | check | G_API: "the parser's own error reply must be framed HTTP" (and the group's others) |
| 2026-11-21 run C | F61 | T48 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-21 run C | F62 | T44 | risk | A11 and the threat model: a link or a --db path in the app folder is set by someone with access to the owner's files |
| 2026-11-21 run C | F71 | T27 | risk | design.md States gives a network failure a kept draft and a message (gated in T25) |
| 2026-11-21 run C | F72 | T28 | risk | design.md keeps the typed text in #rename-list (gated in T21) |
| 2026-11-21 run C | F73 | T26 | risk | design.md defines no pending-write behaviour beyond C7 (the latest read wins) |
| 2026-11-21 run C | F74 | T31 | risk | api-contract.md: the server trims and counts and is authoritative |
| 2026-11-21 run C | F75 | T27 | risk | design.md States gives a network failure a kept draft and a message (gated in T25) |
| 2026-11-21 run C | F76 | T30 | risk | design.md: confirming Delete list makes Inbox current |
| 2026-11-21 run C | F77 | T29 | risk | design.md Accessibility asks for visible focus and a keyboard-reachable menu (gated in T18) |
| 2026-11-21 run R1 | F1 | T02 | risk | A9: with --host 0.0.0.0 every device that can reach the laptop is trusted (decisions.md threat model) |
| 2026-11-21 run R1 | F2 | T01 | check | G_API: "the default bind must be loopback only (127.0.0.1)" (and the group's others) |
| 2026-11-21 run R1 | F3 | T46 | check | G_API: "is not an IP address: 403" (and the group's others) |
| 2026-11-21 run R1 | F4 | T45 | check | G_API: "the CSP must be exactly default-src 'self'; frame-ancestors 'none'" (and the group's others) |
| 2026-11-21 run R1 | F5 | T47 | risk | api-contract.md promises other websites cannot read, change or frame the app (gated: A2-A5) |
| 2026-11-21 run R1 | F6 | T43 | check | G_API: "only /, /app.js and /styles.css are served" (and the group's others) |
| 2026-11-21 run R1 | F7 | T42 | check | G_API: "is readable by others" (and the group's others) |
| 2026-11-21 run R1 | F8 | T48 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-21 run R1 | F9 | T38 | check | G_API: "punctuation must round-trip" (and the group's others) |
| 2026-11-21 run R1 | F10 | T22 | check | G_BROWSER: "A list name was inserted as markup" (and the group's others) |
| 2026-11-21 run R1 | F11 | T40 | check | G_API: "an add raced a delete with the older revision" (and the group's others) |
| 2026-11-21 run R1 | F12 | T23 | check | G_BROWSER: "Confirmation must name the list and its todo count" (and the group's others) |
| 2026-11-21 run R1 | F13 | T40 | check | G_API: "an add raced a delete with the older revision" (and the group's others) |
| 2026-11-21 run R1 | F14 | T26 | risk | design.md defines no pending-write behaviour beyond C7 (the latest read wins) |
| 2026-11-21 run R1 | F15 | T21 | check | G_BROWSER: "a todo another device deleted disappears when its Delete is clicked" (and the group's others) |
| 2026-11-21 run R1 | F16 | T21 | check | G_BROWSER: "a todo another device deleted disappears when its Delete is clicked" (and the group's others) |
| 2026-11-21 run R1 | F17 | T24 | check | G_BROWSER: "an older filter reply never shows under a newer filter" (and the group's others) |
| 2026-11-21 run R1 | F18 | T25 | check | G_BROWSER: "a failed Add keeps the draft" (and the group's others) |
| 2026-11-21 run R1 | F19 | T35 | check | G_API: "names compare by casefold(), not lower()" (and the group's others) |
| 2026-11-21 run R1 | F20 | T36 | check | G_API: "row shape" (and the group's others) |
| 2026-11-21 run R1 | F21 | T39 | check | G_API: "the deleted list's todos are still in the database" (and the group's others) |
| 2026-11-21 run R1 | F22 | T41 | risk | architecture.md specifies no behaviour for these: an outside lock is a local program (A11) or a second server (C8), and disk failure is physical (threat model) |
| 2026-11-21 run R1 | F23 | T19 | check | G_BROWSER: "below 720px the list toggle shows" (and the group's others) |
| 2026-11-21 run R1 | F24 | T18 | check | G_BROWSER: "the New todo label is visible" (and the group's others) |
| 2026-11-21 run R1 | F25 | T14 | risk | design.md is the handoff J_UI builds from (contract.json: the exact ids and labels in design.md) |
| 2026-11-21 run R1 | F26 | T13 | risk | Outside the fixture's gates (contract.json): Vesper runs every gate on the last job and exports that accepted snapshot |
| 2026-11-21 run R1 | F27 | T15 | check | tests/test_pocket_todo_triage.py: "acceptance.md and failure_paths have different rows" (and the group's others) |
| 2026-11-21 run R1 | F28 | T16 | check | G_API: "assertions are disabled" (and the group's others) |
| 2026-11-21 run R1 | F30 | T03 | risk | A9: a proposed risk the owner accepts by approving the plan (architecture.md, decisions.md threat model) |
| 2026-11-21 run R1 | F31 | T04 | risk | A11: local programs and accounts using the loopback port are trusted (decisions.md threat model) |
| 2026-11-21 run R1 | F32 | T05 | risk | A12: outside the threat model (decisions.md) |
| 2026-11-21 run R1 | F33 | T06 | risk | A13: outside the threat model (decisions.md) |
| 2026-11-21 run R1 | F34 | T10 | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted |
| 2026-11-21 run R1 | F35 | T07 | risk | C5: a proposed risk (architecture.md): one owner, only a name or a tick is overwritten |
| 2026-11-21 run R1 | F36 | T08 | risk | C6: a proposed risk (architecture.md): the UI never retries by itself (gated in T25) |
| 2026-11-21 run R1 | F37 | T09 | risk | C8: not supported, run one server per database file (product.md, architecture.md) |
| 2026-11-21 run R1 | F38 | T10 | risk | decisions.md threat model: anyone with physical access is outside, and the owner's devices and browser are trusted |
| 2026-11-21 run R1 | F49 | T49 | check | G_API: "the parser's own error reply must be framed HTTP" (and the group's others) |
| 2026-11-21 run R1 | F50 | T46 | check | G_API: "is not an IP address: 403" (and the group's others) |
| 2026-11-21 run R1 | F51 | T50 | risk | A12 (slowing the app is outside the threat model) and A9/A11 (a client that reaches the port already has full access) |
| 2026-11-21 run R1 | F52 | T34 | check | G_API: "malformed input must get a 4xx, not" (and the group's others) |
| 2026-11-21 run R1 | F53 | T46 | check | G_API: "is not an IP address: 403" (and the group's others) |
| 2026-11-21 run R1 | F54 | T49 | check | G_API: "the parser's own error reply must be framed HTTP" (and the group's others) |
| 2026-11-21 run R1 | F66 | T26 | risk | design.md defines no pending-write behaviour beyond C7 (the latest read wins) |
| 2026-11-21 run R1 | F67 | T26 | risk | design.md defines no pending-write behaviour beyond C7 (the latest read wins) |
| 2026-11-21 run R1 | F68 | T27 | risk | design.md States gives a network failure a kept draft and a message (gated in T25) |
| 2026-11-21 run R1 | F69 | T28 | risk | design.md keeps the typed text in #rename-list (gated in T21) |
| 2026-11-21 run R1 | F70 | T32 | check | G_BROWSER: "with a 40-character list name" (and the group's others) |

## Outside the export

P2-G rerun R2's F1 (the `list_id` SQL injection) was in that run's seed, not in `reference/`, which binds every `list_id`. It is **covered** by the new malformed-id assertion: `DELETE /api/lists/(1)OR(inbox=0)?rev=1` must get a 4xx and change nothing (G_API: "malformed input must get a 4xx, not"). `reference/` was not changed for it.
