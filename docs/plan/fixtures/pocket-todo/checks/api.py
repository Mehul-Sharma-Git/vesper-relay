"""G_API: Pocket Todo HTTP API, browser safety and persistence. Usage: api.py CANDIDATE_DIR

Rows of plan/acceptance.md checked here: R1-R3, R6, R7 and items A2-A5, A7, A8, C1, C3, C4."""
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlsplit
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


def raw(base, path, method="GET", host=None, headers=None, body=None):
    """One request with full control of Host (None sends no Host header); returns (status, headers)."""
    address = urlsplit(base)
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=5)
    try:
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        if host is not None:
            connection.putheader("Host", host)
        for name, value in (headers or {}).items():
            connection.putheader(name, value)
        if body is not None:
            connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        response.read()
        return response.status, {name.lower(): value for name, value in response.getheaders()}
    finally:
        connection.close()


def lists(base):
    return {item["name"]: item for item in call(base, "/api/lists")[1]}


def delete_list(base, list_id, rev, headers=None):
    return call(base, f"/api/lists/{list_id}?rev={rev}", "DELETE", headers=headers)


def titles(base, list_id):
    return [t["title"] for t in call(base, f"/api/todos?list={list_id}&status=all")[1]]


def check(root):
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "todos.sqlite3"
        with server(root, db) as base:
            port = base.rsplit(":", 1)[1]
            here = f"127.0.0.1:{port}"
            assert call(base, "/health") == (200, {"ok": True})
            # A7: only /, /app.js and /styles.css are static: never the server's files or the database.
            for path in ("/server.py", "/%2e%2e/server.py", "/todos.sqlite3", "/missing.txt"):
                assert raw(base, path, host=here)[0] == 404, f"GET {path} must be 404"
            code, found = call(base, "/api/lists")
            assert code == 200 and len(found) == 1, found
            inbox = found[0]
            assert inbox["name"] == "Inbox" and inbox["inbox"] is True
            assert inbox["active"] == 0 and inbox["total"] == 0 and isinstance(inbox["rev"], int)

            # R1: validation and names unique by Unicode case folding.
            code, work = call(base, "/api/lists", "POST", {"name": "  Work  "})
            assert code == 201 and work["name"] == "Work" and work["inbox"] is False, work
            assert call(base, "/api/lists", "POST", {"name": "work"})[0] == 409
            code, school = call(base, "/api/lists", "POST", {"name": "École"})
            assert code == 201 and school["name"] == "École", school
            for twin in ("école", "ÉCOLE"):
                assert call(base, "/api/lists", "POST", {"name": twin})[0] == 409, f"{twin} duplicates École"
            assert call(base, f"/api/lists/{work['id']}", "PATCH", {"name": "école"})[0] == 409
            assert delete_list(base, school["id"], lists(base)["École"]["rev"])[0] == 204
            assert call(base, "/api/lists", "POST", {"name": "  "})[0] == 400
            assert call(base, "/api/lists", "POST", {"name": "x" * 41})[0] == 400
            assert call(base, "/api/lists", "POST", {"name": 5})[0] == 400
            assert call(base, "/api/lists", "POST", raw=b"not json")[0] == 400
            code, home = call(base, "/api/lists", "POST", {"name": "Home"})
            assert code == 201
            assert list(lists(base)) == ["Inbox", "Home", "Work"], list(lists(base))

            code, renamed = call(base, f"/api/lists/{home['id']}", "PATCH", {"name": "House"})
            assert code == 200 and renamed["name"] == "House"
            # A list may take a new casing of its own name.
            code, renamed = call(base, f"/api/lists/{home['id']}", "PATCH", {"name": "HOUSE"})
            assert code == 200 and renamed["name"] == "HOUSE", renamed
            assert call(base, f"/api/lists/{home['id']}", "PATCH", {"name": "House"})[0] == 200
            assert call(base, f"/api/lists/{home['id']}", "PATCH", {"name": "WORK"})[0] == 409
            assert call(base, f"/api/lists/{inbox['id']}", "PATCH", {"name": "Other"})[0] == 400
            assert delete_list(base, inbox["id"], lists(base)["Inbox"]["rev"])[0] == 400
            assert call(base, "/api/lists/99999", "PATCH", {"name": "Nope"})[0] == 404
            assert delete_list(base, 99999, 1)[0] == 404

            # R2: todos, validation and filters.
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
            counts = {name: (item["active"], item["total"]) for name, item in lists(base).items()}
            assert counts == {"Inbox": (1, 2), "House": (0, 0), "Work": (1, 1)}, counts

            # C4: a todo deleted elsewhere is gone for every action.
            assert call(base, f"/api/todos/{milk['id']}", "DELETE")[0] == 204
            assert call(base, f"/api/todos/{milk['id']}", "DELETE")[0] == 404
            assert call(base, f"/api/todos/{milk['id']}", "PATCH", {"done": True})[0] == 404

            # R1, C1: a delete needs the list's current revision; any change to the list or its todos
            # raises it, even one that keeps the same todo count; a stale delete removes nothing.
            assert call(base, f"/api/lists/{work['id']}", "DELETE")[0] == 400
            assert call(base, f"/api/lists/{work['id']}?rev=one", "DELETE")[0] == 400
            old = lists(base)["Work"]["rev"]
            code, extra = call(base, "/api/todos", "POST", {"listId": work["id"], "title": "Book room"})
            assert code == 201
            assert lists(base)["Work"]["rev"] > old
            assert delete_list(base, work["id"], old)[0] == 409
            assert titles(base, work["id"]) == ["Send report", "Book room"]
            same_count = lists(base)["Work"]["rev"]
            assert call(base, f"/api/todos/{extra['id']}", "DELETE")[0] == 204
            assert call(base, "/api/todos", "POST", {"listId": work["id"], "title": "Book hall"})[0] == 201
            assert lists(base)["Work"]["total"] == 2
            assert delete_list(base, work["id"], same_count)[0] == 409, "same todo count, but the list changed"
            renamed_rev = lists(base)["Work"]["rev"]
            assert call(base, f"/api/lists/{work['id']}", "PATCH", {"name": "Jobs"})[0] == 200
            assert delete_list(base, work["id"], renamed_rev)[0] == 409, "a rename raises the revision"
            assert delete_list(base, work["id"], lists(base)["Jobs"]["rev"])[0] == 204
            assert call(base, f"/api/todos/{report['id']}", "PATCH", {"done": True})[0] == 404
            assert list(lists(base)) == ["Inbox", "House"]

            # C3: ids are never reused after a delete.
            code, temp = call(base, "/api/lists", "POST", {"name": "Temp"})
            assert delete_list(base, temp["id"], lists(base)["Temp"]["rev"])[0] == 204
            code, again = call(base, "/api/lists", "POST", {"name": "Temp"})
            assert again["id"] > temp["id"], "a list id was reused"
            code, gone = call(base, "/api/todos", "POST", {"listId": again["id"], "title": "Gone"})
            assert call(base, f"/api/todos/{gone['id']}", "DELETE")[0] == 204
            code, next_todo = call(base, "/api/todos", "POST", {"listId": again["id"], "title": "Next"})
            assert next_todo["id"] > gone["id"], "a todo id was reused"
            assert delete_list(base, again["id"], lists(base)["Temp"]["rev"])[0] == 204

            # A8: an oversized body is refused.
            big = json.dumps({"name": "Big", "pad": "x" * 70_000}).encode()
            assert raw(base, "/api/lists", "POST", here, {"Content-Type": "application/json"}, big)[0] == 413

            # A3: only localhost or an IP address may be the Host (stops DNS rebinding).
            for host in (f"evil.example:{port}", f"localhost.evil.example:{port}", None):
                assert raw(base, "/api/lists", host=host)[0] == 403, f"Host {host!r} must be refused"
                assert raw(base, "/", host=host)[0] == 403, f"Host {host!r} must be refused"
            for host in (f"localhost:{port}", f"[::1]:{port}", here):
                assert raw(base, "/api/lists", host=host)[0] == 200, f"Host {host!r} must be served"

            # A2: writes another website could send are refused and change nothing.
            for origin in ("http://evil.example", "null"):
                foreign = {"Origin": origin}
                assert call(base, "/api/lists", "POST", {"name": "Evil"}, headers=foreign)[0] == 403
                assert call(base, f"/api/lists/{home['id']}", "PATCH", {"name": "Evil"}, headers=foreign)[0] == 403
                assert delete_list(base, home["id"], lists(base)["House"]["rev"], foreign)[0] == 403
                assert call(base, f"/api/todos/{bank['id']}", "DELETE", headers=foreign)[0] == 403
            assert call(base, "/api/lists", "POST", raw=json.dumps({"name": "Evil"}).encode(),
                        headers={"Content-Type": "text/plain"})[0] == 415
            assert call(base, "/api/lists", "POST", raw=b"name=Evil",
                        headers={"Content-Type": "application/x-www-form-urlencoded"})[0] == 415
            assert list(lists(base)) == ["Inbox", "House"]
            assert titles(base, inbox["id"]) == ["Call bank"]
            # The app's own page (same Origin, by IP or localhost, JSON with a charset) still works.
            same = {"Origin": base, "Content-Type": "application/json; charset=utf-8"}
            code, garden = call(base, "/api/lists", "POST", {"name": "Garden"}, headers=same)
            assert code == 201, garden
            local = {"Host": f"localhost:{port}", "Origin": f"http://localhost:{port}"}
            assert delete_list(base, garden["id"], lists(base)["Garden"]["rev"], local)[0] == 204

            # A4, A5: no CORS, not frameable, no MIME sniffing, on every response.
            for path in ("/", "/api/lists", "/missing.txt"):
                headers = raw(base, path, host=here, headers={"Origin": "http://evil.example"})[1]
                assert "access-control-allow-origin" not in headers, f"{path} sends a CORS header"
                policy = headers.get("content-security-policy", "")
                assert "frame-ancestors 'none'" in policy and "default-src 'self'" in policy, (path, policy)
                assert headers.get("x-frame-options", "").upper() == "DENY", path
                assert headers.get("x-content-type-options", "").lower() == "nosniff", path

        # R3: data survives a restart.
        with server(root, db) as base:
            assert list(lists(base)) == ["Inbox", "House"]
            todos = call(base, f"/api/todos?list={inbox['id']}&status=all")[1]
            assert [(t["title"], t["done"]) for t in todos] == [("Call bank", True)], todos
    print("Lists, todos, validation, filters, case-folded names, revision-guarded delete, unused ids, "
          "browser safety and headers, cascade delete and restart persistence passed.")


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve())
