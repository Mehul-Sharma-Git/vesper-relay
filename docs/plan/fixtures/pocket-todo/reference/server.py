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
from urllib.parse import parse_qs, urlsplit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_BODY = 64 * 1024
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  fold TEXT NOT NULL UNIQUE,
  rev INTEGER NOT NULL DEFAULT 1,
  inbox INTEGER NOT NULL DEFAULT 0 CHECK (inbox IN (0, 1))
);
CREATE TABLE IF NOT EXISTS todos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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


# ---------- storage / business logic ----------

def connect(path):
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path):
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO lists(name, fold, inbox) VALUES ('Inbox', 'inbox', 1)")
        conn.execute("COMMIT")
    finally:
        conn.close()


def clean_text(value, field, maxlen):
    if not isinstance(value, str):
        raise ApiError(400, f"{field} must be a string")
    value = value.strip()
    if not 1 <= len(value) <= maxlen:
        raise ApiError(400, f"{field} must be 1-{maxlen} characters")
    return value


def list_json(conn, list_id):
    row = conn.execute(
        "SELECT l.id, l.name, l.inbox, l.rev, "
        "COALESCE(SUM(t.done = 0), 0) AS active, COUNT(t.id) AS total "
        "FROM lists l LEFT JOIN todos t ON t.list_id = l.id "
        "WHERE l.id = ? GROUP BY l.id", (list_id,)).fetchone()
    return None if row is None else {
        "id": row["id"], "name": row["name"], "inbox": bool(row["inbox"]),
        "active": row["active"], "total": row["total"], "rev": row["rev"]}


def todo_json(row):
    return {"id": row["id"], "listId": row["list_id"],
            "title": row["title"], "done": bool(row["done"])}


def get_lists(conn):
    rows = conn.execute(
        "SELECT l.id, l.name, l.inbox, l.rev, "
        "COALESCE(SUM(t.done = 0), 0) AS active, COUNT(t.id) AS total "
        "FROM lists l LEFT JOIN todos t ON t.list_id = l.id "
        "GROUP BY l.id ORDER BY l.inbox DESC, l.fold, l.id").fetchall()
    return [{"id": r["id"], "name": r["name"], "inbox": bool(r["inbox"]),
             "active": r["active"], "total": r["total"], "rev": r["rev"]} for r in rows]


def create_list(conn, body):
    name = clean_text(body.get("name"), "name", 40)
    try:
        cur = conn.execute("INSERT INTO lists(name, fold, inbox) VALUES (?, ?, 0)", (name, name.casefold()))
    except sqlite3.IntegrityError:
        raise ApiError(409, "a list with that name already exists")
    return list_json(conn, cur.lastrowid)


def rename_list(conn, list_id, body):
    row = conn.execute("SELECT inbox FROM lists WHERE id = ?", (list_id,)).fetchone()
    if row is None:
        raise ApiError(404, "list not found")
    name = clean_text(body.get("name"), "name", 40)
    if row["inbox"]:
        raise ApiError(400, "Inbox cannot be renamed")
    try:
        conn.execute("UPDATE lists SET name = ?, fold = ?, rev = rev + 1 WHERE id = ? AND inbox = 0", (name, name.casefold(), list_id))
    except sqlite3.IntegrityError:
        raise ApiError(409, "a list with that name already exists")
    return list_json(conn, list_id)


def delete_list(conn, list_id, query):
    rev = query.get("rev", [None])[0]
    if rev is None or not re.fullmatch(r"[0-9]{1,9}", rev):
        raise ApiError(400, "rev is required")
    row = conn.execute("SELECT inbox, rev FROM lists WHERE id = ?", (list_id,)).fetchone()
    if row is None:
        raise ApiError(404, "list not found")
    if row["inbox"]:
        raise ApiError(400, "Inbox cannot be deleted")
    if row["rev"] != int(rev):
        raise ApiError(409, "the list changed; check it and try again")
    conn.execute("DELETE FROM lists WHERE id = ? AND inbox = 0", (list_id,))


def get_todos(conn, query):
    raw = query.get("list", [None])[0]
    if raw is None or not re.fullmatch(r"[0-9]{1,18}", raw):
        raise ApiError(400, "list must be a list id")
    status = query.get("status", ["all"])[0]
    if status not in ("all", "active", "done"):
        raise ApiError(400, "status must be all, active or done")
    if conn.execute("SELECT 1 FROM lists WHERE id = ?", (int(raw),)).fetchone() is None:
        raise ApiError(404, "list not found")
    sql = "SELECT id, list_id, title, done FROM todos WHERE list_id = ?"
    if status == "active":
        sql += " AND done = 0"
    elif status == "done":
        sql += " AND done = 1"
    rows = conn.execute(sql + " ORDER BY created, id", (int(raw),)).fetchall()
    return [todo_json(r) for r in rows]


def create_todo(conn, body):
    list_id = body.get("listId")
    if not isinstance(list_id, int) or isinstance(list_id, bool):
        raise ApiError(400, "listId must be an integer")
    title = clean_text(body.get("title"), "title", 200)
    if not -2**63 <= list_id < 2**63:
        raise ApiError(404, "list not found")
    try:
        cur = conn.execute(
            "INSERT INTO todos(list_id, title, done, created) VALUES (?, ?, 0, ?)",
            (list_id, title, int(time.time() * 1000)))
    except sqlite3.IntegrityError:  # FK violation: list does not exist
        raise ApiError(404, "list not found")
    conn.execute("UPDATE lists SET rev = rev + 1 WHERE id = ?", (list_id,))
    row = conn.execute("SELECT id, list_id, title, done FROM todos WHERE id = ?",
                       (cur.lastrowid,)).fetchone()
    return todo_json(row)


def update_todo(conn, todo_id, body):
    done = body.get("done")
    if not isinstance(done, bool):
        raise ApiError(400, "done must be a boolean")
    cur = conn.execute("UPDATE todos SET done = ? WHERE id = ?", (int(done), todo_id))
    if cur.rowcount == 0:
        raise ApiError(404, "todo not found")
    conn.execute("UPDATE lists SET rev = rev + 1 WHERE id = (SELECT list_id FROM todos WHERE id = ?)", (todo_id,))
    row = conn.execute("SELECT id, list_id, title, done FROM todos WHERE id = ?",
                       (todo_id,)).fetchone()
    return todo_json(row)


def delete_todo(conn, todo_id):
    owner = conn.execute("SELECT list_id FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if owner is None:
        raise ApiError(404, "todo not found")
    conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.execute("UPDATE lists SET rev = rev + 1 WHERE id = ?", (owner["list_id"],))


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    server_version = "PocketTodo"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, payload=None, ctype="application/json; charset=utf-8", raw=None):
        if raw is None and payload is not None:
            raw = json.dumps(payload).encode("utf-8")
        raw = raw or b""
        self.send_response(status)
        if status != 204:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "invalid Content-Length")
        if length < 0:
            raise ApiError(400, "invalid Content-Length")
        if length > MAX_BODY:
            raise ApiError(413, "body too large")
        data = self.rfile.read(length) if length else b""
        try:
            body = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "body must be JSON")
        if not isinstance(body, dict):
            raise ApiError(400, "body must be a JSON object")
        return body

    def _handle(self):
        parts = urlsplit(self.path)
        path, query = parts.path, parse_qs(parts.query)
        method = self.command
        try:
            if len(self.headers.get_all("Host") or []) != 1:
                raise ApiError(403, "one Host header required")
            host = self.headers.get("Host") or ""
            hostname = re.sub(r":[0-9]+$", "", host) if not host.startswith("[") else host.split("]")[0] + "]"
            if not (hostname == "localhost" or re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,3}){3}", hostname)
                    or re.fullmatch(r"\[[0-9a-fA-F:.]+\]", hostname)):
                raise ApiError(403, "unknown host")
            if method in ("POST", "PATCH", "DELETE"):
                origin = self.headers.get("Origin")
                if origin is not None and origin != "http://" + host:
                    raise ApiError(403, "foreign origin")
            if method in ("POST", "PATCH"):
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ctype != "application/json":
                    raise ApiError(415, "body must be application/json")
            if method in ("GET", "HEAD") and path in STATIC:
                return self._static(*STATIC[path])
            if path == "/health" and method == "GET":
                return self._send(200, {"ok": True})
            m = re.fullmatch(r"/api/(lists|todos)(?:/([0-9]{1,18}))?", path)
            if not m:
                raise ApiError(404, "not found")
            res, rid = m.group(1), m.group(2)
            rid = int(rid) if rid is not None else None
            routes = {
                ("lists", None, "GET"): lambda c: (200, get_lists(c)),
                ("lists", None, "POST"): lambda c: (201, create_list(c, self._body())),
                ("lists", rid, "PATCH"): lambda c: (200, rename_list(c, rid, self._body())),
                ("lists", rid, "DELETE"): lambda c: (204, delete_list(c, rid, query)),
                ("todos", None, "GET"): lambda c: (200, get_todos(c, query)),
                ("todos", None, "POST"): lambda c: (201, create_todo(c, self._body())),
                ("todos", rid, "PATCH"): lambda c: (200, update_todo(c, rid, self._body())),
                ("todos", rid, "DELETE"): lambda c: (204, delete_todo(c, rid)),
            }
            fn = routes.get((res, rid, method))
            if fn is None:
                raise ApiError(405, "method not allowed")
            conn = connect(self.server.db_path)
            try:
                conn.execute("BEGIN IMMEDIATE" if method != "GET" else "BEGIN")
                try:
                    status, payload = fn(conn)
                    conn.execute("COMMIT")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            finally:
                conn.close()
            self._send(status, payload)
        except ApiError as e:
            self.close_connection = True  # request body may be unread
            self._send(e.status, {"error": e.message})
        except sqlite3.OperationalError:
            self._send(503, {"error": "database busy, retry"})
        except Exception:
            self._send(500, {"error": "internal error"})

    def _static(self, filename, ctype):
        try:
            with open(os.path.join(BASE_DIR, filename), "rb") as f:
                raw = f.read()
        except OSError:
            raise ApiError(404, "not found")
        self._send(200, ctype=ctype, raw=raw)

    do_GET = do_HEAD = do_POST = do_PATCH = do_DELETE = do_PUT = _handle


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args(argv)
    os.umask(0o077)
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
    sys.exit(main())
