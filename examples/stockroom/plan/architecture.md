# Architecture

Use Python 3.11+ standard library and SQLite. Run the HTTP service on 127.0.0.1.
Expose GET /health, GET /, GET /app.js, GET /styles.css, GET /api/items,
POST /api/items, and PATCH /api/items/{id}. The frontend uses vanilla browser JS.

GET /api/items returns a JSON array. Query filters are room and status, where
status is needed or bought. Create takes requestId, name, room, and quantity.
Allowed rooms are Kitchen, Bedroom, Bath, and General. Trim names, require 1–80
characters, and accept integer quantity 1–99. Create returns HTTP 201 with
id, name, room, quantity, status, version. A replay with the same requestId and
same normalized data returns HTTP 200 and the same item. An inconsistent replay
returns HTTP 409. Invalid fields return HTTP 400. A PATCH body contains status
and version. A stale version returns HTTP 409 and the current item. A missing
item returns HTTP 404. Mutations require application/json.

Use an SQLite transaction for create/idempotency and compare-and-update. Startup
accepts --port and --db, and port 0 chooses a free port. Print READY followed by the
loopback URL on stdout after binding. Serve only the three named assets. Use
the response as the source of truth and use text nodes for user-provided names.
