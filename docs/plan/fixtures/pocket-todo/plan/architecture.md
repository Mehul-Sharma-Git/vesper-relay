# Architecture

Python 3.11 standard library HTTP server (`server.py`) + SQLite + static
`index.html`, `styles.css`, `app.js`. No third-party packages, no build step.

## Launch
`python3 server.py --db PATH [--host 127.0.0.1] [--port 8080]`. `--port 0` picks a
free port. After binding, print exactly one line `READY http://HOST:PORT` and flush.
Creates tables and the Inbox list on first start.

## Data
- lists(id INTEGER PK, name TEXT, fold TEXT UNIQUE (the case-folded name), inbox INTEGER 0/1)
- todos(id INTEGER PK, list_id FK ON DELETE CASCADE, title TEXT, done INTEGER, created INTEGER)

## API (JSON; errors are `{"error": "message"}`)
| Method & path | Body | Success | Errors |
|---|---|---|---|
| GET /health | | 200 `{"ok": true}` | |
| GET /api/lists | | 200 `[{"id","name","inbox","active","total"}]`, Inbox first, then by name | |
| POST /api/lists | `{"name"}` trimmed 1-40 | 201 list | 400 invalid, 409 duplicate (case-folded, see below) |
| PATCH /api/lists/{id} | `{"name"}` | 200 list | 400 invalid or Inbox, 404, 409 duplicate |
| DELETE /api/lists/{id}?name=NAME&total=N | | 204, its todos removed | 400 Inbox or missing/invalid name or total, 404, 409 name or total differs |
| GET /api/todos?list=ID&status=all\|active\|done | | 200 `[{"id","listId","title","done"}]` oldest first | 400 bad status, 404 unknown list |
| POST /api/todos | `{"listId","title"}` title trimmed 1-200 | 201 todo (done false) | 400 invalid, 404 unknown list |
| PATCH /api/todos/{id} | `{"done": bool}` | 200 todo | 400, 404 |
| DELETE /api/todos/{id} | | 204 | 404 |
| GET / , /app.js, /styles.css | | text/html, text/javascript, text/css | 404 other paths |

`active` and `total` are todo counts. Non-JSON or wrong types return 400.

List names are unique after trimming and Unicode case folding (Python `str.casefold()`):
"Work" and "WORK", or "École" and "école", are duplicates. The name keeps the casing typed.

Deleting a list sends the name and todo `total` the user confirmed. The server compares
both with the list as stored and deletes it with its todos in one transaction; if either
differs (another device renamed it or changed its todos), it answers 409 and deletes nothing.

## Browser safety (no login, so the server refuses requests a foreign site could make)
- Every request: the `Host` header must name `localhost`, an IPv4 address or a bracketed
  IPv6 address (any port); any other host name gets 403. This stops DNS-rebinding pages.
- POST, PATCH and DELETE: if an `Origin` header is present it must equal `http://` + the
  `Host` header, else 403. POST and PATCH need `Content-Type: application/json`
  (parameters such as `charset` allowed), else 415. A refused request changes nothing.
- The server sends no CORS headers.

## First slice
J_API (backend, server.py) then J_UI (frontend, static files) against this API.
