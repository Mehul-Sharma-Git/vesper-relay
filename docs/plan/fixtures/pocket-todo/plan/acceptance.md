# Acceptance: failure-path matrix (QA)

Each row: a requirement or an item from architecture.md (A = reachability, C = concurrent
change), the scenario, the gate assertion, and the wrong build it catches. Items proposed as
risks in architecture.md (A9, A11-A13, C5, C6, C8) have no row; the owner accepts them by approving the plan. Gates run against the candidate in the sandbox.

| Item | Scenario | Assertion (gate) | Wrong build it catches |
|---|---|---|---|
| R1 | Create "Work", then "work", "École", then "école" and "ÉCOLE" | 201, 409, 201, 409, 409 (G_API) | NOCASE collation (ASCII only) or no uniqueness |
| R1 | Rename "House" to "HOUSE" | 200, name "HOUSE" (G_API) | a uniqueness check that collides with the list's own row |
| R1 | Rename or delete Inbox | 400 (G_API) | Inbox unprotected |
| R1, C1 | Delete "Work" with no `rev`, a bad `rev`, an old `rev`, then the current `rev` | 400, 400, 409 (list and todos still there), 204 (G_API) | a delete with no guard, or a guard on name and count |
| C1 | Note `rev`, delete one todo and add another (same count), delete with the old `rev` | 409 (G_API) | a guard on the todo count instead of a revision |
| C1 | Complete, reopen, and re-send the same done value; each time delete with the `rev` from before | `rev` rises each time; 409 each time (G_API) | a revision that ignores completion or a no-op PATCH |
| C1 | Delete one todo alone; then a duplicate rename, a blank name, a bad done, a blank title and a repeat delete | the delete raises `rev`; the refused writes change no record and no `rev` (G_API) | a delete that skips the revision, or a refused write that bumps it |
| R2 | Add, complete, filter, delete todos; empty and long titles | statuses and lists as in the contract (G_API) | missing validation or filters |
| R2 | Wrong types: title 5, null or []; listId true, "1", null or missing; done 1 or null; a body that is an array, a number or null | 400 each, nothing created or changed (G_API) | a server that coerces types (Python `True` is an `int`) |
| R3 | Delete a list with a todo, then restart the server | its todos are gone; the rest survives (G_API) | no cascade, or data kept only in memory |
| C3 | Delete the newest list and todo, then create new ones | new ids are larger than the deleted ones (G_API) | ids reused after a delete |
| A7 | GET `/server.py`, `/%2e%2e/server.py`, `/todos.sqlite3`, `/missing.txt` | 404 each (G_API) | a static handler that serves the folder |
| A8 | A 70 KB body on all four body routes | 413, nothing changed (G_API) | no body size limit, or one on some routes |
| A3 | On every route and method (GET `/`, `/health`, both lists, both todo collections; POST, PATCH, DELETE of lists and todos): `Host` `evil.example`, `localhost.evil.example`, `127.0.0.1.evil.example:PORT`, `1.2.3.4.evil.example`, `localhost.:PORT`, `127.0.0.1:x`, `a@127.0.0.1`, empty, missing, or two `Host` headers | 403 each (G_API) | no Host check, a prefix or unanchored match, or one that reads only the first header |
| A3 | `Host` `localhost`, `localhost:PORT`, `127.0.0.1:PORT`, `[::1]`, `[::1]:PORT` | served (G_API) | a Host check that refuses legitimate addresses |
| A2 | On all six write routes, writes with `Origin` `http://evil.example`, `null`, `https://HOST`, `http://127.0.0.1:OTHER`, `http://localhost:PORT` (Host is `127.0.0.1:PORT`), `http://HOST.evil.example` | 403, nothing changed (G_API) | no Origin check, or one that compares only the host name or a prefix |
| A2 | On all four body routes (POST and PATCH of lists and todos), `text/plain` or form encoding | 415, nothing changed (G_API) | a server that parses any body as JSON, or checks only some routes |
| A2 | Writes from the app's own origin, JSON with `charset` | succeed (G_API) | an Origin check that blocks the app itself |
| A4 | A request with a foreign `Origin` | no `Access-Control-Allow-Origin` in the reply (G_API) | a server that sends CORS headers |
| A5 | `/`, `/api/lists`, a 404, and refused 400, 403, 413 and 415 replies | CSP with `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`; JSON replies typed `application/json` (G_API) | headers set only on success paths |
| A10 | Start the server on a new database | the database and any journal files have no group or other permissions (G_API) | a database file created with the default umask |
| C10 | 20 adds to one list at the same moment | all 201, total 20, `rev` up by exactly 20 (G_API) | no busy timeout ("database is locked"), or lost revision updates |
| R4 | The served page | labelled controls, picker, filters, status region, local assets only (G_UI) | missing labels or remote assets |
| R5 | Phone at 320×740: add, complete, filter, add, choose, rename and delete lists (cancel first), Escape | each visible effect, no horizontal scroll (G_BROWSER) | a layout that only fits 375px, or a broken journey |
| R5 | Laptop at 1280×800: choose a list in the sidebar, add and complete a todo there | each visible effect (G_BROWSER) | a sidebar that shows lists but cannot switch them |
| R5, A6 | Add a todo titled `<img src=x onerror="window.__xss=1">` and a list named `<b>Bold</b>` | both shown as text; `window.__xss` stays undefined (G_BROWSER) | rendering with `innerHTML` |
| R5, C1 | While the delete dialog is open, another device adds a todo; accept | the DELETE is sent and gets 409; the status says "another device"; the list stays; the next dialog shows the new count (G_BROWSER) | a UI that sends no guard, ignores the 409, or quietly gives up |
| C2 | Another device deletes the current list; type a title and press Add | Inbox becomes current, the title is still in the field, the status says "another device", no todo was posted (G_BROWSER) | a UI that loses the draft or posts it to another list |
| C4 | Another device deletes a todo; click its checkbox | the todo disappears and the status says "another device" (G_BROWSER) | a UI that ignores a 404 and keeps a dead todo |
| C7 | Hold Inbox's todo reply, switch to another list, then release it | only the current list's todos show (G_BROWSER, laptop) | a UI that renders whichever reply arrives last |
| C9 | Another device deletes the current list; then Rename list, or Delete list | Inbox becomes current; the status says "another device" (G_BROWSER) | a UI that ignores a 404 on list actions |
| C9 | Another device creates "Garage"; this device adds a list named "garage" | the status says "already"; the name stays in `#new-list` (G_BROWSER) | a UI that drops a 409 or the typed name |
