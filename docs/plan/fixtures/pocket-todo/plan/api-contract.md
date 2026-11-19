# Pocket Todo API contract

Canonical contract shared by backend, frontend and QA (acknowledged in planning.json).
architecture.md does not repeat it.

## API (JSON; errors are `{"error": "message"}`)
| Method & path | Body | Success | Errors |
|---|---|---|---|
| GET /health | | 200 `{"ok": true}` | |
| GET /api/lists | | 200 `[{"id","name","inbox","active","total","rev"}]`, Inbox first, then by case-folded name | |
| POST /api/lists | `{"name"}` trimmed 1-40 | 201 list | 400 invalid, 409 duplicate |
| PATCH /api/lists/{id} | `{"name"}` | 200 list | 400 invalid or Inbox, 404, 409 duplicate |
| DELETE /api/lists/{id}?rev=N | | 204, its todos removed | 400 Inbox or missing/invalid rev, 404, 409 rev differs |
| GET /api/todos?list=ID&status=all\|active\|done | | 200 `[{"id","listId","title","done"}]` oldest first | 400 bad status, 404 unknown list |
| POST /api/todos | `{"listId","title"}` title trimmed 1-200 | 201 todo (done false) | 400 invalid, 404 unknown list |
| PATCH /api/todos/{id} | `{"done": bool}` | 200 todo | 400, 404 |
| DELETE /api/todos/{id} | | 204 | 404 |
| GET / , /app.js, /styles.css | | text/html, text/javascript, text/css | 404 other paths |

- `active` and `total` are todo counts. Non-JSON or wrong types return 400. A body over
  64 KB returns 413.
- List names are unique after trimming and Unicode case folding (Python `str.casefold()`):
  "Work" and "WORK", or "École" and "école", are duplicates. A list may be renamed to a
  different casing of its own name ("Work" to "WORK"). The name keeps the casing typed.
- `rev` is a list's revision. It starts at 1 and goes up by one each time the list is renamed
  or one of its todos is added, completed or reopened, or deleted.
- Deleting a list sends the `rev` the confirmation dialog showed. The server compares it
  with the stored `rev` and deletes the list with its todos in one transaction; if it
  differs (another device changed the list or its todos), it answers 409 and deletes nothing.
- List and todo ids are never reused, even after a delete.

## Browser safety (no login, so the server refuses what another website could do)
- Every request: the `Host` header must name `localhost`, an IPv4 address or a bracketed
  IPv6 address (any port); a missing `Host` or any other host name (such as
  `localhost.evil.example`) gets 403. This stops DNS-rebinding pages.
- POST, PATCH and DELETE: if an `Origin` header is present it must equal `http://` + the
  `Host` header (`Origin: null` is refused), else 403. POST and PATCH need
  `Content-Type: application/json` (parameters such as `charset` allowed), else 415.
  A refused request changes nothing.
- Every response carries `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'`,
  `X-Frame-Options: DENY` and `X-Content-Type-Options: nosniff`, and no CORS header
  (`Access-Control-Allow-Origin`). So the page cannot be framed by another site, and the
  UI must use no inline script or style: all script in app.js, all CSS in styles.css.
