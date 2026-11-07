"""Stockroom local HTTP service."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit


ROOMS = ("Kitchen", "Bedroom", "Bath", "General")
STATUSES = ("needed", "bought")
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/styles.css": ("styles.css", "text/css")}
COLUMNS = "id, name, room, quantity, status, version"


class InputError(ValueError):
    pass


def verify(condition, message):
    if not condition:
        raise InputError(message)


class Stockroom(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def dispatch(self):
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in allowed:
            return self.reply(400, {"error": "Use the local preview URL."})
        target = urlsplit(self.path)
        try:
            return self.route(target)
        except (InputError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return self.reply(400, {"error": str(error)})

    do_GET = do_POST = do_PATCH = dispatch

    def reply(self, code, data, content_type="application/json"):
        payload = json.dumps(data).encode() if content_type == "application/json" else data
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def body(self):
        verify(self.headers.get_content_type() == "application/json", "Expected application/json")
        size = self.headers.get("Content-Length", "")
        verify(size.isascii() and size.isdecimal() and len(size) <= 4 and 0 < int(size) <= 4096,
               "Invalid request length")
        payload = json.loads(self.rfile.read(int(size)))
        verify(isinstance(payload, dict), "Expected a JSON object")
        return payload

    def route(self, target):
        if self.command == "GET" and target.path == "/health":
            return self.reply(200, {"status": "ok"})
        if self.command == "GET" and target.path in ASSETS:
            name, content_type = ASSETS[target.path]
            try:
                payload = (Path(__file__).resolve().parent / name).read_bytes()
            except FileNotFoundError:
                return self.reply(404, {"error": "Asset unavailable"})
            return self.reply(200, payload, content_type)
        match = re.fullmatch(r"/api/items/([1-9][0-9]{0,17})", target.path)
        if target.path != "/api/items" and not match:
            return self.reply(404, {"error": "Not found"})
        with closing(sqlite3.connect(self.server.db_path)) as db, db:
            db.row_factory = sqlite3.Row
            if self.command == "GET" and not match:
                return self.list_items(db, target.query)
            if self.command == "POST" and not match:
                status, payload = self.create_item(db, self.body())
            elif self.command == "PATCH" and match:
                status, payload = self.update_item(db, int(match[1]), self.body())
            else:
                return self.reply(405, {"error": "Method not allowed"})
        # Confirm writes only after the database transaction commits.
        return self.reply(status, payload)

    def list_items(self, db, query):
        filters = parse_qs(query, keep_blank_values=True)
        verify(set(filters) <= {"room", "status"}, "Unknown filter")
        conditions, values = [], []
        for key, allowed in (("room", ROOMS), ("status", STATUSES)):
            if key in filters:
                selected = filters[key]
                verify(len(selected) == 1 and selected[0] in allowed, f"Invalid {key} filter")
                conditions.append(key + " = ?")
                values.append(selected[0])
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = db.execute(f"SELECT {COLUMNS} FROM items{where} ORDER BY id DESC", values)
        return self.reply(200, [dict(row) for row in rows])

    def create_item(self, db, body):
        name, room, quantity, request = (body.get(key) for key in ("name", "room", "quantity", "requestId"))
        verify(isinstance(name, str) and 1 <= len(name.strip()) <= 80, "Enter an item name of 1–80 characters.")
        verify(room in ROOMS, "Choose a room.")
        verify(type(quantity) is int and 1 <= quantity <= 99, "Enter a whole quantity from 1 to 99.")
        verify(isinstance(request, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", request),
               "Invalid request identifier.")
        name = name.strip()
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(f"SELECT {COLUMNS} FROM items WHERE request_id = ?", (request,)).fetchone()
        if existing:
            if (existing["name"], existing["room"], existing["quantity"]) != (name, room, quantity):
                return 409, {"error": "That request ID was used for different values."}
            return 200, dict(existing)
        item_id = db.execute("INSERT INTO items (name, room, quantity, request_id) VALUES (?, ?, ?, ?)",
                             (name, room, quantity, request)).lastrowid
        return 201, self.item(db, item_id)

    def item(self, db, item_id):
        row = db.execute(f"SELECT {COLUMNS} FROM items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def update_item(self, db, item_id, body):
        status, version = body.get("status"), body.get("version")
        verify(status in STATUSES and type(version) is int and 0 < version < 2**63,
               "Provide a valid status and version.")
        update = db.execute("UPDATE items SET status = ?, version = version + 1 WHERE id = ? AND version = ?",
                            (status, item_id, version))
        current = self.item(db, item_id)
        if current is None:
            return 404, {"error": "Item not found."}
        if update.rowcount == 0:
            return 409, {"error": "This item changed. Review it and try again.", "current": current}
        return 200, current


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("stockroom.sqlite3"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with closing(sqlite3.connect(args.db)) as db, db:
        db.execute("""
          CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, room TEXT NOT NULL,
            quantity INTEGER NOT NULL, request_id TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'needed', version INTEGER NOT NULL DEFAULT 1
          )
        """)
    with ThreadingHTTPServer(("127.0.0.1", args.port), Stockroom) as server:
        server.db_path = args.db
        print(f"READY http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
