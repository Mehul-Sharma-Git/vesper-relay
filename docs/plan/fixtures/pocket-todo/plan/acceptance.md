# Acceptance: failure-path matrix (QA)

Each row: a requirement or an item from architecture.md (A = reachability, C = concurrent
change), the scenario, the gate assertion, and the wrong build it catches. Items accepted in
architecture.md (A9, A10, C5–C8) have no row. Gates run against the candidate in the sandbox.

| Item | Scenario | Assertion (gate) | Wrong build it catches |
|---|---|---|---|
| R1 | Create "Work", then "work", "École", then "école" and "ÉCOLE" | 201, 409, 201, 409, 409 (G_API) | NOCASE collation (ASCII only) or no uniqueness |
| R1 | Rename "House" to "HOUSE" | 200, name "HOUSE" (G_API) | a uniqueness check that collides with the list's own row |
| R1 | Rename or delete Inbox | 400 (G_API) | Inbox unprotected |
| R1, C1 | Delete "Work" with no `rev`, a bad `rev`, an old `rev`, then the current `rev` | 400, 400, 409 (list and todos still there), 204 (G_API) | a delete with no guard, or a guard on name and count |
| C1 | Note `rev`, delete one todo and add another (same count), delete with the old `rev` | 409 (G_API) | a guard on the todo count instead of a revision |
| R2 | Add, complete, filter, delete todos; empty, long and wrong-type titles | statuses and lists as in the contract (G_API) | missing validation or filters |
| R3 | Delete a list with a todo, then restart the server | its todos are gone; the rest survives (G_API) | no cascade, or data kept only in memory |
| C3 | Delete the newest list and todo, then create new ones | new ids are larger than the deleted ones (G_API) | ids reused after a delete |
| A7 | GET `/server.py`, `/%2e%2e/server.py`, `/todos.sqlite3`, `/missing.txt` | 404 each (G_API) | a static handler that serves the folder |
| A8 | POST a 70 KB body | 413, nothing created (G_API) | no body size limit |
| A3 | Any request with `Host` `evil.example`, `localhost.evil.example`, or no `Host` | 403 (G_API) | no Host check, or a prefix match on "localhost" |
| A3 | A request with `Host: [::1]:PORT` or `localhost:PORT` | served (G_API) | a Host check that refuses legitimate addresses |
| A2 | Writes with `Origin: http://evil.example` or `Origin: null` | 403, nothing changed (G_API) | no Origin check, or one that lets `null` through |
| A2 | POST with `text/plain` or form encoding | 415, nothing changed (G_API) | a server that parses any body as JSON |
| A2 | Writes from the app's own origin, JSON with `charset` | succeed (G_API) | an Origin check that blocks the app itself |
| A4 | A request with a foreign `Origin` | no `Access-Control-Allow-Origin` in the reply (G_API) | a server that sends CORS headers |
| A5 | GET `/` | CSP with `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff` (G_API) | a frameable page |
| R4 | The served page | labelled controls, picker, filters, status region, local assets only (G_UI) | missing labels or remote assets |
| R5 | Phone at 320×740: add, complete, filter, add, choose, rename and delete lists (cancel first), Escape | each visible effect, no horizontal scroll (G_BROWSER) | a layout that only fits 375px, or a broken journey |
| R5 | Laptop at 1280×800: choose a list in the sidebar, add and complete a todo there | each visible effect (G_BROWSER) | a sidebar that shows lists but cannot switch them |
| R5, A6 | Add a todo titled `<img src=x onerror="window.__xss=1">` and a list named `<b>Bold</b>` | both shown as text; `window.__xss` stays undefined (G_BROWSER) | rendering with `innerHTML` |
| R5, C1 | While the delete dialog is open, another device adds a todo; accept | the DELETE is sent and gets 409; the status says "another device"; the list stays; the next dialog shows the new count (G_BROWSER) | a UI that sends no guard, ignores the 409, or quietly gives up |
| C2 | Another device deletes the current list; type a title and press Add | Inbox becomes current, the title is still in the field, the status says "another device", no todo was posted (G_BROWSER) | a UI that loses the draft or posts it to another list |
| C4 | Another device deletes a todo; click its checkbox | the todo disappears and the status says "another device" (G_BROWSER) | a UI that ignores a 404 and keeps a dead todo |
