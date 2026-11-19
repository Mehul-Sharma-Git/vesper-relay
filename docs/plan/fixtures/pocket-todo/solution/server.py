#!/usr/bin/env python3
"""Pocket Todo server: stdlib HTTP + SQLite. See architecture.md."""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_BODY = 64 * 1024
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  inbox INTEGER NOT NULL DEFAULT 0 CHECK (inbox IN (0, 1))
);
CREATE TABLE IF NOT EXISTS todos (
  id INTEGER PRIMARY KEY,
  list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)),
  created INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS todos_list ON todos(list_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS lists_one_inbox ON lists(inbox) WHERE inbox = 1;
"""


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def connect(path):
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path):
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM lists WHERE inbox = 1").fetchone() is None:
            # If a user list already took the name "Inbox", adopt it.
            row = conn.execute("SELECT id FROM lists WHERE name = 'Inbox'").fetchone()
            if row:
                conn.execute("UPDATE lists SET inbox = 1 WHERE id = ?", (row["id"],))
            else:
                conn.execute("INSERT INTO lists (name, inbox) VALUES ('Inbox', 1)")
        conn.execute("COMMIT")
    finally:
        conn.close()


# ---- storage / business operations -------------------------------------

LIST_SQL = """
SELECT l.id, l.name, l.inbox,
       COALESCE(SUM(t.done = 0), 0) AS active,
       COUNT(t.id) AS total
FROM lists l LEFT JOIN todos t ON t.list_id = l.id
"""


def list_json(row):
    return {"id": row["id"], "name": row["name"], "inbox": bool(row["inbox"]),
            "active": row["active"], "total": row["total"]}


def get_list(conn, list_id):
    row = conn.execute(LIST_SQL + " WHERE l.id = ? GROUP BY l.id", (list_id,)).fetchone()
    if row is None:
        raise ApiError(404, "list not found")
    return list_json(row)


def todo_json(row):
    return {"id": row["id"], "listId": row["list_id"], "title": row["title"],
            "done": bool(row["done"])}


def get_todo(conn, todo_id):
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if row is None:
        raise ApiError(404, "todo not found")
    return todo_json(row)


def clean_text(value, field, maxlen):
    if not isinstance(value, str):
        raise ApiError(400, f"{field} must be a string")
    value = value.strip()
    if not 1 <= len(value) <= maxlen:
        raise ApiError(400, f"{field} must be 1-{maxlen} characters")
    return value


def clean_name(body):
    return clean_text(body.get("name"), "name", 40)


def require_object(body):
    if not isinstance(body, dict):
        raise ApiError(400, "JSON object expected")
    return body


def lists_index(conn):
    rows = conn.execute(LIST_SQL + " GROUP BY l.id ORDER BY l.inbox DESC, l.name COLLATE NOCASE, l.id").fetchall()
    return [list_json(r) for r in rows]


def lists_create(conn, body):
    name = clean_name(require_object(body))
    try:
        cur = conn.execute("INSERT INTO lists (name, inbox) VALUES (?, 0)", (name,))
    except sqlite3.IntegrityError:
        raise ApiError(409, "a list with that name already exists")
    return 201, get_list(conn, cur.lastrowid)


def lists_rename(conn, list_id, body):
    name = clean_name(require_object(body))
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT inbox FROM lists WHERE id = ?", (list_id,)).fetchone()
        if row is None:
            raise ApiError(404, "list not found")
        if row["inbox"]:
            raise ApiError(400, "Inbox cannot be renamed")
        try:
            conn.execute("UPDATE lists SET name = ? WHERE id = ? AND inbox = 0", (name, list_id))
        except sqlite3.IntegrityError:
            raise ApiError(409, "a list with that name already exists")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return 200, get_list(conn, list_id)


def lists_delete(conn, list_id):
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT inbox FROM lists WHERE id = ?", (list_id,)).fetchone()
        if row is None:
            raise ApiError(404, "list not found")
        if row["inbox"]:
            raise ApiError(400, "Inbox cannot be deleted")
        conn.execute("DELETE FROM lists WHERE id = ? AND inbox = 0", (list_id,))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return 204, None


def todos_index(conn, query):
    raw = query.get("list", [None])[0]
    if raw is None or not re.fullmatch(r"[0-9]{1,18}", raw):
        raise ApiError(400, "list must be a list id")
    status = query.get("status", ["all"])[0]
    if status not in ("all", "active", "done"):
        raise ApiError(400, "status must be all, active or done")
    list_id = int(raw)
    if conn.execute("SELECT 1 FROM lists WHERE id = ?", (list_id,)).fetchone() is None:
        raise ApiError(404, "list not found")
    sql = "SELECT * FROM todos WHERE list_id = ?"
    if status == "active":
        sql += " AND done = 0"
    elif status == "done":
        sql += " AND done = 1"
    rows = conn.execute(sql + " ORDER BY created, id", (list_id,)).fetchall()
    return [todo_json(r) for r in rows]


def todos_create(conn, body):
    body = require_object(body)
    list_id = body.get("listId")
    if not isinstance(list_id, int) or isinstance(list_id, bool):
        raise ApiError(400, "listId must be an integer")
    title = clean_text(body.get("title"), "title", 200)
    try:
        cur = conn.execute(
            "INSERT INTO todos (list_id, title, done, created) VALUES (?, ?, 0, ?)",
            (list_id, title, int(time.time() * 1000)))
    except sqlite3.IntegrityError:  # foreign key: list missing
        raise ApiError(404, "list not found")
    except OverflowError:
        raise ApiError(404, "list not found")
    return 201, get_todo(conn, cur.lastrowid)


def todos_update(conn, todo_id, body):
    body = require_object(body)
    done = body.get("done")
    if not isinstance(done, bool):
        raise ApiError(400, "done must be a boolean")
    cur = conn.execute("UPDATE todos SET done = ? WHERE id = ?", (int(done), todo_id))
    if cur.rowcount == 0:
        raise ApiError(404, "todo not found")
    return 200, get_todo(conn, todo_id)


def todos_delete(conn, todo_id):
    cur = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    if cur.rowcount == 0:
        raise ApiError(404, "todo not found")
    return 204, None


# ---- HTTP translation ----------------------------------------------------

ID_MAX = 2 ** 63 - 1


def route(conn, method, path, query, read_body):
    """Return (status, payload) or raise ApiError."""
    if path == "/health" and method == "GET":
        return 200, {"ok": True}
    if path == "/api/lists":
        if method == "GET":
            return 200, lists_index(conn)
        if method == "POST":
            return lists_create(conn, read_body())
    if path == "/api/todos":
        if method == "GET":
            return 200, todos_index(conn, query)
        if method == "POST":
            return todos_create(conn, read_body())
    m = re.fullmatch(r"/api/(lists|todos)/([0-9]{1,18})", path)
    if m:
        kind, oid = m.group(1), int(m.group(2))
        if kind == "lists":
            if method == "PATCH":
                return lists_rename(conn, oid, read_body())
            if method == "DELETE":
                return lists_delete(conn, oid)
        else:
            if method == "PATCH":
                return todos_update(conn, oid, read_body())
            if method == "DELETE":
                return todos_delete(conn, oid)
    raise ApiError(404, "not found")


class Handler(BaseHTTPRequestHandler):
    server_version = "PocketTodo"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send_payload(self, status, ctype, data):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, status, payload):
        if status == 204:
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_payload(status, "application/json; charset=utf-8",
                          json.dumps(payload).encode("utf-8"))

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "invalid Content-Length")
        if length < 0 or length > MAX_BODY:
            raise ApiError(400, "body too large")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "body must be valid JSON")

    def handle_any(self):
        parts = urlsplit(self.path)
        path = parts.path
        try:
            if self.command == "GET" and path in STATIC:
                name, ctype = STATIC[path]
                try:
                    with open(os.path.join(BASE_DIR, name), "rb") as f:
                        data = f.read()
                except OSError:
                    raise ApiError(404, "not found")
                return self.send_payload(200, ctype, data)
            body_read = []

            def read_body():
                body_read.append(True)
                return self.read_body()

            conn = connect(self.server.db_path)
            try:
                status, payload = route(conn, self.command, path,
                                        parse_qs(parts.query), read_body)
            finally:
                conn.close()
            self.send_json(status, payload)
        except ApiError as e:
            self.send_error_json(e.status, e.message)
        except sqlite3.OperationalError:
            self.send_error_json(503, "database busy, try again")
        except Exception:
            self.send_error_json(500, "internal error")

    def send_error_json(self, status, message):
        # Unread request bodies would corrupt keep-alive framing; close.
        self.close_connection = True
        self.send_json(status, {"error": message})

    do_GET = do_POST = do_PATCH = do_DELETE = handle_any


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args(argv)
    init_db(args.db)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    httpd.db_path = args.db
    print(f"READY http://{args.host}:{httpd.server_address[1]}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
