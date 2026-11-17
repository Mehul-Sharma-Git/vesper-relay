# Pocket Todo API contract

Canonical contract shared by backend, frontend and QA (acknowledged in planning.json).

## API (JSON; errors are `{"error": "message"}`)
| Method & path | Body | Success | Errors |
|---|---|---|---|
| GET /health | | 200 `{"ok": true}` | |
| GET /api/lists | | 200 `[{"id","name","inbox","active","total"}]`, Inbox first, then by name | |
| POST /api/lists | `{"name"}` trimmed 1-40 | 201 list | 400 invalid, 409 duplicate (case-insensitive) |
| PATCH /api/lists/{id} | `{"name"}` | 200 list | 400 invalid or Inbox, 404, 409 duplicate |
| DELETE /api/lists/{id} | | 204, its todos removed | 400 Inbox, 404 |
| GET /api/todos?list=ID&status=all\|active\|done | | 200 `[{"id","listId","title","done"}]` oldest first | 400 bad status, 404 unknown list |
| POST /api/todos | `{"listId","title"}` title trimmed 1-200 | 201 todo (done false) | 400 invalid, 404 unknown list |
| PATCH /api/todos/{id} | `{"done": bool}` | 200 todo | 400, 404 |
| DELETE /api/todos/{id} | | 204 | 404 |
| GET / , /app.js, /styles.css | | text/html, text/javascript, text/css | 404 other paths |

`active` and `total` are todo counts. Non-JSON or wrong types return 400.
