"""G_API: Pocket Todo HTTP API and persistence. Usage: api.py CANDIDATE_DIR"""
from contextlib import contextmanager
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@contextmanager
def server(root, db):
    command = [sys.executable, "-B", str(root / "server.py"), "--port", "0", "--db", str(db)]
    with subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1) as process:
        try:
            with selectors.DefaultSelector() as ready:
                ready.register(process.stdout, selectors.EVENT_READ)
                assert ready.select(8), "Server did not announce readiness"
            line = process.stdout.readline().strip()
            assert line.startswith("READY http://127.0.0.1:"), f"Startup failed: {line}"
            yield line.split(" ", 1)[1]
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()


def call(base, path, method="GET", payload=None, raw=None):
    data = raw if raw is not None else (None if payload is None else json.dumps(payload).encode())
    headers = {"Content-Type": "application/json"} if data is not None else {}
    try:
        response = urlopen(Request(base + path, data=data, method=method, headers=headers), timeout=5)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read()
        return response.status, (json.loads(body) if body else None)


def check(root):
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "todos.sqlite3"
        with server(root, db) as base:
            assert call(base, "/health") == (200, {"ok": True})
            code, lists = call(base, "/api/lists")
            assert code == 200 and len(lists) == 1, lists
            inbox = lists[0]
            assert inbox["name"] == "Inbox" and inbox["inbox"] is True
            assert inbox["active"] == 0 and inbox["total"] == 0

            code, work = call(base, "/api/lists", "POST", {"name": "  Work  "})
            assert code == 201 and work["name"] == "Work" and work["inbox"] is False, work
            assert call(base, "/api/lists", "POST", {"name": "work"})[0] == 409
            assert call(base, "/api/lists", "POST", {"name": "  "})[0] == 400
            assert call(base, "/api/lists", "POST", {"name": "x" * 41})[0] == 400
            assert call(base, "/api/lists", "POST", {"name": 5})[0] == 400
            assert call(base, "/api/lists", "POST", raw=b"not json")[0] == 400
            code, home = call(base, "/api/lists", "POST", {"name": "Home"})
            assert code == 201
            names = [item["name"] for item in call(base, "/api/lists")[1]]
            assert names == ["Inbox", "Home", "Work"], names

            code, renamed = call(base, f"/api/lists/{home['id']}", "PATCH", {"name": "House"})
            assert code == 200 and renamed["name"] == "House"
            assert call(base, f"/api/lists/{home['id']}", "PATCH", {"name": "WORK"})[0] == 409
            assert call(base, f"/api/lists/{inbox['id']}", "PATCH", {"name": "Other"})[0] == 400
            assert call(base, f"/api/lists/{inbox['id']}", "DELETE")[0] == 400
            assert call(base, "/api/lists/99999", "PATCH", {"name": "Nope"})[0] == 404
            assert call(base, "/api/lists/99999", "DELETE")[0] == 404

            code, milk = call(base, "/api/todos", "POST", {"listId": inbox["id"], "title": "  Buy milk "})
            assert code == 201 and milk["title"] == "Buy milk" and milk["done"] is False
            assert milk["listId"] == inbox["id"]
            code, bank = call(base, "/api/todos", "POST", {"listId": inbox["id"], "title": "Call bank"})
            assert code == 201
            code, report = call(base, "/api/todos", "POST", {"listId": work["id"], "title": "Send report"})
            assert code == 201
            assert call(base, "/api/todos", "POST", {"listId": inbox["id"], "title": " "})[0] == 400
            assert call(base, "/api/todos", "POST", {"listId": inbox["id"], "title": "x" * 201})[0] == 400
            assert call(base, "/api/todos", "POST", {"listId": 99999, "title": "Lost"})[0] == 404

            code, done = call(base, f"/api/todos/{bank['id']}", "PATCH", {"done": True})
            assert code == 200 and done["done"] is True
            assert call(base, f"/api/todos/{bank['id']}", "PATCH", {"done": "yes"})[0] == 400
            assert call(base, "/api/todos/99999", "PATCH", {"done": True})[0] == 404

            q = f"/api/todos?list={inbox['id']}"
            assert [t["title"] for t in call(base, q + "&status=all")[1]] == ["Buy milk", "Call bank"]
            assert [t["title"] for t in call(base, q + "&status=active")[1]] == ["Buy milk"]
            assert [t["title"] for t in call(base, q + "&status=done")[1]] == ["Call bank"]
            assert call(base, q + "&status=bogus")[0] == 400
            assert call(base, "/api/todos?list=99999&status=all")[0] == 404
            counts = {item["name"]: (item["active"], item["total"]) for item in call(base, "/api/lists")[1]}
            assert counts == {"Inbox": (1, 2), "House": (0, 0), "Work": (1, 1)}, counts

            assert call(base, f"/api/todos/{milk['id']}", "DELETE")[0] == 204
            assert call(base, f"/api/todos/{milk['id']}", "DELETE")[0] == 404

            assert call(base, f"/api/lists/{work['id']}", "DELETE")[0] == 204
            assert call(base, f"/api/todos/{report['id']}", "PATCH", {"done": True})[0] == 404
            assert [item["name"] for item in call(base, "/api/lists")[1]] == ["Inbox", "House"]

        with server(root, db) as base:
            lists = call(base, "/api/lists")[1]
            assert [item["name"] for item in lists] == ["Inbox", "House"], lists
            todos = call(base, f"/api/todos?list={inbox['id']}&status=all")[1]
            assert [(t["title"], t["done"]) for t in todos] == [("Call bank", True)], todos
    print("Lists, todos, validation, filters, cascade delete and restart persistence passed.")


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve())
