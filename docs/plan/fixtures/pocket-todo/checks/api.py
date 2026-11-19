"""G_API: Pocket Todo HTTP API and persistence. Usage: api.py CANDIDATE_DIR"""
from contextlib import contextmanager
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.parse import quote
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


def call(base, path, method="GET", payload=None, raw=None, headers=None):
    data = raw if raw is not None else (None if payload is None else json.dumps(payload).encode())
    headers = {**({"Content-Type": "application/json"} if data is not None else {}), **(headers or {})}
    try:
        response = urlopen(Request(base + path, data=data, method=method, headers=headers), timeout=5)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read()
        return response.status, (json.loads(body) if body else None)


def delete_list(base, list_id, name, total, headers=None):
    return call(base, f"/api/lists/{list_id}?name={quote(name)}&total={total}", "DELETE", headers=headers)


def status(base, path, headers=None):
    try:
        with urlopen(Request(base + path, headers=headers or {}), timeout=5) as response:
            return response.status
    except HTTPError as exc:
        exc.close()
        return exc.code


def check(root):
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "todos.sqlite3"
        with server(root, db) as base:
            assert call(base, "/health") == (200, {"ok": True})
            # Only /, /app.js and /styles.css are static: never the server's own files or the database.
            for path in ("/server.py", "/%2e%2e/server.py", "/todos.sqlite3", "/missing.txt"):
                assert status(base, path) == 404, f"GET {path} must be 404"
            code, lists = call(base, "/api/lists")
            assert code == 200 and len(lists) == 1, lists
            inbox = lists[0]
            assert inbox["name"] == "Inbox" and inbox["inbox"] is True
            assert inbox["active"] == 0 and inbox["total"] == 0

            code, work = call(base, "/api/lists", "POST", {"name": "  Work  "})
            assert code == 201 and work["name"] == "Work" and work["inbox"] is False, work
            assert call(base, "/api/lists", "POST", {"name": "work"})[0] == 409
            code, school = call(base, "/api/lists", "POST", {"name": "École"})
            assert code == 201 and school["name"] == "École", school
            for twin in ("école", "ÉCOLE"):
                assert call(base, "/api/lists", "POST", {"name": twin})[0] == 409, f"{twin} duplicates École"
            assert call(base, f"/api/lists/{work['id']}", "PATCH", {"name": "école"})[0] == 409
            assert delete_list(base, school["id"], "École", 0)[0] == 204
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
            assert delete_list(base, inbox["id"], "Inbox", 0)[0] == 400
            assert call(base, "/api/lists/99999", "PATCH", {"name": "Nope"})[0] == 404
            assert delete_list(base, 99999, "Nope", 0)[0] == 404

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

            # A delete needs the name and todo count the user confirmed; a stale one deletes nothing.
            assert call(base, f"/api/lists/{work['id']}", "DELETE")[0] == 400
            assert call(base, f"/api/lists/{work['id']}?name=Work&total=one", "DELETE")[0] == 400
            assert delete_list(base, work["id"], "Work", 0)[0] == 409
            assert delete_list(base, work["id"], "work", 1)[0] == 409
            assert call(base, f"/api/todos?list={work['id']}&status=all")[0] == 200
            assert delete_list(base, work["id"], "Work", 1)[0] == 204
            assert call(base, f"/api/todos/{report['id']}", "PATCH", {"done": True})[0] == 404
            assert [item["name"] for item in call(base, "/api/lists")[1]] == ["Inbox", "House"]

            # Browser safety: what another website could send is refused and changes nothing.
            port = base.rsplit(":", 1)[1]
            foreign = {"Origin": "http://evil.example"}
            assert call(base, "/api/lists", headers={"Host": f"evil.example:{port}"})[0] == 403
            assert status(base, "/", {"Host": f"rebind.example:{port}"}) == 403
            assert call(base, "/api/lists", "POST", {"name": "Evil"}, headers=foreign)[0] == 403
            assert call(base, f"/api/lists/{home['id']}", "PATCH", {"name": "Evil"}, headers=foreign)[0] == 403
            assert call(base, f"/api/lists/{home['id']}?name=House&total=0", "DELETE", headers=foreign)[0] == 403
            assert call(base, f"/api/todos/{bank['id']}", "DELETE", headers=foreign)[0] == 403
            assert call(base, "/api/lists", "POST", raw=json.dumps({"name": "Evil"}).encode(),
                        headers={"Content-Type": "text/plain"})[0] == 415
            assert call(base, "/api/lists", "POST", raw=b"name=Evil",
                        headers={"Content-Type": "application/x-www-form-urlencoded"})[0] == 415
            assert [item["name"] for item in call(base, "/api/lists")[1]] == ["Inbox", "House"]
            assert [t["title"] for t in call(base, f"/api/todos?list={inbox['id']}&status=all")[1]] == ["Call bank"]
            # The app's own page (same Origin, by IP or localhost, JSON with a charset) still works.
            same = {"Origin": base, "Content-Type": "application/json; charset=utf-8"}
            code, garden = call(base, "/api/lists", "POST", {"name": "Garden"}, headers=same)
            assert code == 201, garden
            local = {"Host": f"localhost:{port}", "Origin": f"http://localhost:{port}"}
            assert delete_list(base, garden["id"], "Garden", 0, local)[0] == 204

        with server(root, db) as base:
            lists = call(base, "/api/lists")[1]
            assert [item["name"] for item in lists] == ["Inbox", "House"], lists
            todos = call(base, f"/api/todos?list={inbox['id']}&status=all")[1]
            assert [(t["title"], t["done"]) for t in todos] == [("Call bank", True)], todos
    print("Lists, todos, validation, filters, case-folded names, guarded list delete, browser safety, "
          "cascade delete and restart persistence passed.")


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve())
