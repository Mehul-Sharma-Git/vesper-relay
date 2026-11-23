"""G_API: Pocket Todo HTTP API, browser safety and persistence. Usage: api.py CANDIDATE_DIR

Rows of plan/acceptance.md checked here: R1-R3, R6, R7 and items A1-A5, A7, A8, A10, C1, C3, C4, C9,
C10. P3-T3b folded P2-G's accepted findings in (findings-triage.md)."""
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import re
import selectors
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

if sys.flags.optimize:
    raise SystemExit("G_API: assertions are disabled (python -O or PYTHONOPTIMIZE); run the gate without them")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AssertionError(f"Unexpected redirect {code} from {req.full_url} to {newurl}: the app never redirects")


# Straight to the candidate: no proxy from the environment, and a redirect is a failure, never followed.
OPENER = build_opener(ProxyHandler({}), NoRedirect())


@contextmanager
def server(root, db, host=None, cwd=None):
    command = [sys.executable, "-B", str(root / "server.py"), "--port", "0", "--db", str(db)]
    command += ["--host", host] if host else []
    with subprocess.Popen(command, cwd=cwd or root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1) as process:
        try:
            with selectors.DefaultSelector() as ready:
                ready.register(process.stdout, selectors.EVENT_READ)
                assert ready.select(8), "Server did not announce readiness"
            line = process.stdout.readline().strip()
            expected = re.escape(host or "127.0.0.1")
            assert re.fullmatch(rf"READY http://{expected}:[0-9]+", line), f"Startup failed: {line}"
            # Keep reading what the server prints, so a chatty server never blocks on a full pipe.
            threading.Thread(target=process.stdout.read, daemon=True).start()
            yield "http://127.0.0.1:" + line.rsplit(":", 1)[1]
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
        response = OPENER.open(Request(base + path, data=data, method=method, headers=headers), timeout=5)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read()
        return response.status, (json.loads(body) if body else None)


def exchange(base, path, method="GET", host=None, headers=None, body=None, address=None):
    """One request with full control of Host (None sends none; a list sends each); returns (status,
    header pairs, body)."""
    target = urlsplit(base)
    connection = http.client.HTTPConnection(address or target.hostname, target.port, timeout=5)
    try:
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for value in ([] if host is None else host if isinstance(host, list) else [host]):
            connection.putheader("Host", value)
        for name, value in (headers or {}).items():
            for one in (value if isinstance(value, list) else [value]):
                connection.putheader(name, one)
        if body is not None:
            connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        return response.status, [(name.lower(), value) for name, value in response.getheaders()], response.read()
    finally:
        connection.close()


def raw(base, path, method="GET", host=None, headers=None, body=None):
    """One request with full control of Host (None sends none; a list sends each); returns (status, headers)."""
    status, pairs, _ = exchange(base, path, method, host, headers, body)
    return status, dict(pairs)


def wire(base, data):
    """Send raw bytes, end the request side and read the whole reply: (status line, header pairs, body)."""
    target = urlsplit(base)
    with socket.create_connection((target.hostname, target.port), timeout=5) as sock:
        sock.sendall(data)
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
    head, _, body = b"".join(chunks).partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    pairs = [(name.strip().lower(), value.strip()) for name, _, value in
             (line.partition(":") for line in lines[1:] if ":" in line)]
    return lines[0], pairs, body


def lists(base):
    return {item["name"]: item for item in call(base, "/api/lists")[1]}


def delete_list(base, list_id, rev, headers=None):
    return call(base, f"/api/lists/{list_id}?rev={rev}", "DELETE", headers=headers)


def snapshot(base):
    """Every list (with its revision) and every todo (with its state): to prove a refusal changed nothing."""
    return [(item, call(base, f"/api/todos?list={item['id']}&status=all")[1]) for item in call(base, "/api/lists")[1]]


def titles(base, list_id):
    return [t["title"] for t in call(base, f"/api/todos?list={list_id}&status=all")[1]]


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def list_shape(item):
    """api-contract.md: a list is {"id", "name", "inbox", "active", "total", "rev"} with these types."""
    assert isinstance(item, dict) and {"id", "name", "inbox", "active", "total", "rev"} <= set(item), \
        f"row shape: a list needs id, name, inbox, active, total and rev: {item}"
    assert all(is_int(item[key]) for key in ("id", "active", "total", "rev")), f"row shape: list numbers: {item}"
    assert isinstance(item["name"], str) and isinstance(item["inbox"], bool), f"row shape: list name and inbox: {item}"
    return item


def todo_shape(item):
    """api-contract.md: a todo is {"id", "listId", "title", "done"}; done is true or false, never 0 or 1."""
    assert isinstance(item, dict) and {"id", "listId", "title", "done"} <= set(item), \
        f"row shape: a todo needs id, listId, title and done: {item}"
    assert is_int(item["id"]) and is_int(item["listId"]), f"row shape: todo ids: {item}"
    assert isinstance(item["title"], str) and isinstance(item["done"], bool), f"row shape: todo title and done: {item}"
    return item


def every_row_shape(base):
    for item in call(base, "/api/lists")[1]:
        list_shape(item)
        for status in ("all", "active", "done"):
            for todo in call(base, f"/api/todos?list={item['id']}&status={status}")[1]:
                todo_shape(todo)


def owner_only(directory, when):
    """A10: the database and its journal files are the owner's only."""
    for file in Path(directory).iterdir():
        assert stat.S_IMODE(file.stat().st_mode) & 0o077 == 0, f"{file.name} is readable by others ({when})"


def orphans(db):
    """Todos whose list is gone, read straight from the database file (architecture.md's schema)."""
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
        return connection.execute("SELECT COUNT(*) FROM todos WHERE list_id NOT IN (SELECT id FROM lists)").fetchone()[0]


def policy(pairs, where):
    """A4, A5: one CSP of exactly default-src 'self' and frame-ancestors 'none', DENY, nosniff, no CORS."""
    values = lambda name: [value for key, value in pairs if key == name]
    assert not [key for key, _ in pairs if key.startswith("access-control-")], f"{where} sends a CORS header"
    csp = values("content-security-policy")
    assert len(csp) == 1, f"{where}: one Content-Security-Policy header, not {csp}"
    directives = {}
    for part in filter(None, (piece.strip() for piece in csp[0].split(";"))):
        name, *sources = part.split()
        directives[name.lower()] = sources
    assert directives == {"default-src": ["'self'"], "frame-ancestors": ["'none'"]}, \
        f"{where}: the CSP must be exactly default-src 'self'; frame-ancestors 'none': {csp[0]!r}"
    assert [value.upper() for value in values("x-frame-options")] == ["DENY"], f"{where}: X-Frame-Options"
    assert [value.lower() for value in values("x-content-type-options")] == ["nosniff"], f"{where}: nosniff"


def error_shape(status, pairs, body, where):
    """api-contract.md: errors are {"error": "message"} typed application/json."""
    kind = dict(pairs).get("content-type", "")
    assert kind.startswith("application/json"), f"{where}: a {status} error must be JSON, not {kind!r}"
    reply = json.loads(body)
    assert isinstance(reply, dict) and isinstance(reply.get("error"), str), f"{where}: error shape {reply!r}"


def second_loopback():
    """Linux routes all of 127.0.0.0/8 to loopback, macOS only 127.0.0.1: the bind checks need 127.0.0.2."""
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.2", 0))
        return True
    except OSError:
        return False


def reachable(address, port):
    try:
        with socket.create_connection((address, port), timeout=1):
            return True
    except OSError:
        return False


def check(root):
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "todos.sqlite3"
        with server(root, db) as base:
            port = base.rsplit(":", 1)[1]
            here = f"127.0.0.1:{port}"
            assert call(base, "/health") == (200, {"ok": True})
            # A1, decisions.md: the server listens on 127.0.0.1 unless started with --host 0.0.0.0.
            if second_loopback():
                assert not reachable("127.0.0.2", int(port)), "the default bind must be loopback only (127.0.0.1)"
            # A10: the database and its journal files are the owner's only.
            owner_only(directory, "at startup")
            # A7: only /, /app.js and /styles.css are static: never the server's files or the database.
            for path in ("/server.py", "/%2e%2e/server.py", "/todos.sqlite3", "/missing.txt"):
                assert raw(base, path, host=here)[0] == 404, f"GET {path} must be 404"
            code, found = call(base, "/api/lists")
            assert code == 200 and len(found) == 1, found
            inbox = list_shape(found[0])
            assert inbox["name"] == "Inbox" and inbox["inbox"] is True
            assert inbox["active"] == 0 and inbox["total"] == 0 and isinstance(inbox["rev"], int)
            assert inbox["rev"] == 1, f"a revision starts at 1: Inbox has {inbox['rev']}"

            # R1: validation and names unique by Unicode case folding.
            code, work = call(base, "/api/lists", "POST", {"name": "  Work  "})
            assert code == 201 and work["name"] == "Work" and work["inbox"] is False, work
            assert list_shape(work)["rev"] == 1, f"a revision starts at 1: {work}"
            assert call(base, "/api/lists", "POST", {"name": "work"})[0] == 409
            code, school = call(base, "/api/lists", "POST", {"name": "École"})
            assert code == 201 and school["name"] == "École", school
            for twin in ("école", "ÉCOLE"):
                assert call(base, "/api/lists", "POST", {"name": twin})[0] == 409, f"{twin} duplicates École"
            assert call(base, f"/api/lists/{work['id']}", "PATCH", {"name": "école"})[0] == 409
            assert delete_list(base, school["id"], lists(base)["École"]["rev"])[0] == 204
            # Full case folding, not lowercasing: "Straße" folds to "strasse", as "STRASSE" does.
            code, street = call(base, "/api/lists", "POST", {"name": "Straße"})
            assert code == 201, street
            assert call(base, "/api/lists", "POST", {"name": "STRASSE"})[0] == 409, "names compare by casefold(), not lower()"
            assert delete_list(base, street["id"], lists(base)["Straße"]["rev"])[0] == 204
            # Inbox's own name is taken in every casing.
            for twin in ("inbox", "INBOX"):
                assert call(base, "/api/lists", "POST", {"name": twin})[0] == 409, f"{twin} duplicates Inbox"
            assert call(base, f"/api/lists/{work['id']}", "PATCH", {"name": "Inbox"})[0] == 409, "a rename to Inbox"
            assert call(base, "/api/lists", "POST", {"name": "  "})[0] == 400
            assert call(base, "/api/lists", "POST", {"name": "x" * 41})[0] == 400
            assert call(base, "/api/lists", "POST", {"name": 5})[0] == 400
            assert call(base, "/api/lists", "POST", raw=b"not json")[0] == 400
            code, home = call(base, "/api/lists", "POST", {"name": "Home"})
            assert code == 201
            assert list(lists(base)) == ["Inbox", "Home", "Work"], list(lists(base))
            # Lists sort by the case-folded name, not the name as typed.
            code, apple = call(base, "/api/lists", "POST", {"name": "apple"})
            assert list(lists(base)) == ["Inbox", "apple", "Home", "Work"], f"order by folded name: {list(lists(base))}"
            # Limits are inclusive: a 40-character name and a 200-character title are accepted.
            code, longest = call(base, "/api/lists", "POST", {"name": "N" * 40})
            assert code == 201 and longest["name"] == "N" * 40, "a 40-character list name must be accepted"
            assert call(base, f"/api/lists/{longest['id']}", "PATCH", {"name": "y" * 41})[0] == 400, "rename length"
            code, spaced = call(base, f"/api/lists/{longest['id']}", "PATCH", {"name": "  Spaced  "})
            assert code == 200 and spaced["name"] == "Spaced", f"a rename trims the name: {spaced}"
            code, full = call(base, "/api/todos", "POST", {"listId": apple["id"], "title": "t" * 200})
            assert code == 201 and full["title"] == "t" * 200, "a 200-character title must be accepted"
            # Punctuation and SQL-looking text round-trip exactly (bound parameters, never string building).
            code, odd = call(base, "/api/lists", "POST", {"name": "O'Brien \"quotes\"; --"})
            assert code == 201 and odd["name"] == "O'Brien \"quotes\"; --", f"punctuation must round-trip: {odd}"
            code, odd = call(base, f"/api/lists/{odd['id']}", "PATCH", {"name": "Bob's; DELETE FROM lists; --"})
            assert code == 200 and odd["name"] == "Bob's; DELETE FROM lists; --", f"punctuation must round-trip: {odd}"
            title = "it's done'); DROP TABLE todos; --"
            code, quoted = call(base, "/api/todos", "POST", {"listId": odd["id"], "title": title})
            assert code == 201 and titles(base, odd["id"]) == [title], "punctuation must round-trip in a title"
            for extra in (apple, longest, odd):
                current = next(item for item in call(base, "/api/lists")[1] if item["id"] == extra["id"])
                assert delete_list(base, extra["id"], current["rev"])[0] == 204
            assert list(lists(base)) == ["Inbox", "Home", "Work"], list(lists(base))

            code, renamed = call(base, f"/api/lists/{home['id']}", "PATCH", {"name": "House"})
            assert code == 200 and renamed["name"] == "House"
            assert list_shape(renamed)["rev"] == home["rev"] + 1, "a rename raises the revision by exactly one"
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
            assert todo_shape(milk)["listId"] == inbox["id"]
            code, bank = call(base, "/api/todos", "POST", {"listId": inbox["id"], "title": "Call bank"})
            assert code == 201
            code, report = call(base, "/api/todos", "POST", {"listId": work["id"], "title": "Send report"})
            assert code == 201
            assert call(base, "/api/todos", "POST", {"listId": inbox["id"], "title": " "})[0] == 400
            assert call(base, "/api/todos", "POST", {"listId": inbox["id"], "title": "x" * 201})[0] == 400
            assert call(base, "/api/todos", "POST", {"listId": 99999, "title": "Lost"})[0] == 404

            # R2: wrong types are refused and change nothing (Python's True is an int).
            for body in ({"listId": inbox["id"], "title": 5}, {"listId": inbox["id"], "title": None},
                         {"listId": inbox["id"], "title": []}, {"listId": True, "title": "Coerced"},
                         {"listId": str(inbox["id"]), "title": "Coerced"}, {"listId": None, "title": "Coerced"},
                         {"title": "Coerced"}, [inbox["id"], "Coerced"], 5, None):
                assert call(base, "/api/todos", "POST", raw=json.dumps(body).encode())[0] == 400, body
            for body in ({"done": 1}, {"done": None}, {}, [True], None):
                assert call(base, f"/api/todos/{bank['id']}", "PATCH", raw=json.dumps(body).encode())[0] == 400, body
            for body in ([{"name": "Arr"}], 7, None, {"name": None}, {}):
                assert call(base, "/api/lists", "POST", raw=json.dumps(body).encode())[0] == 400, body
                assert call(base, f"/api/lists/{home['id']}", "PATCH", raw=json.dumps(body).encode())[0] == 400, body
            assert titles(base, inbox["id"]) == ["Buy milk", "Call bank"]
            assert list(lists(base)) == ["Inbox", "House", "Work"]

            code, done = call(base, f"/api/todos/{bank['id']}", "PATCH", {"done": True})
            assert code == 200 and done["done"] is True
            todo_shape(done)
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
            every_row_shape(base)

            # C4: a todo deleted elsewhere is gone for every action.
            assert call(base, f"/api/todos/{milk['id']}", "DELETE") == (204, None), "a 204 reply has an empty body"
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
            assert lists(base)["Work"]["rev"] == old + 1, "an add raises the revision by exactly one"
            assert delete_list(base, work["id"], old)[0] == 409
            assert titles(base, work["id"]) == ["Send report", "Book room"]
            same_count = lists(base)["Work"]["rev"]
            assert call(base, f"/api/todos/{extra['id']}", "DELETE")[0] == 204
            assert call(base, "/api/todos", "POST", {"listId": work["id"], "title": "Book hall"})[0] == 201
            assert lists(base)["Work"]["total"] == 2
            assert delete_list(base, work["id"], same_count)[0] == 409, "same todo count, but the list changed"
            # A todo delete on its own raises the revision; a refused write changes nothing, revision included.
            hall = next(t for t in call(base, f"/api/todos?list={work['id']}&status=all")[1] if t["title"] == "Book hall")
            before = lists(base)["Work"]["rev"]
            assert call(base, f"/api/todos/{hall['id']}", "DELETE")[0] == 204
            assert lists(base)["Work"]["rev"] > before, "a todo delete must raise the revision"
            assert lists(base)["Work"]["rev"] == before + 1, "a todo delete raises the revision by exactly one"
            assert delete_list(base, work["id"], before)[0] == 409
            unchanged = snapshot(base)
            assert call(base, f"/api/lists/{work['id']}", "PATCH", {"name": "House"})[0] == 409
            assert call(base, f"/api/lists/{work['id']}", "PATCH", {"name": " "})[0] == 400
            assert call(base, f"/api/todos/{report['id']}", "PATCH", {"done": "yes"})[0] == 400
            assert call(base, "/api/todos", "POST", {"listId": work["id"], "title": ""})[0] == 400
            assert call(base, f"/api/todos/{hall['id']}", "DELETE")[0] == 404
            assert snapshot(base) == unchanged, "a refused write changed data or a revision"
            # Completing, reopening and re-sending the same value each raise the revision.
            sent = next(t for t in call(base, f"/api/todos?list={work['id']}&status=all")[1] if t["title"] == "Send report")
            for done in (True, False, False):
                before = lists(base)["Work"]["rev"]
                assert call(base, f"/api/todos/{sent['id']}", "PATCH", {"done": done})[0] == 200
                assert lists(base)["Work"]["rev"] > before, f"PATCH done={done} must raise the revision"
                assert lists(base)["Work"]["rev"] == before + 1, f"PATCH done={done} raises the revision by exactly one"
                stored = [t["done"] for t in call(base, f"/api/todos?list={work['id']}&status=all")[1] if t["id"] == sent["id"]]
                assert stored == [done], f"PATCH done={done} must persist, found {stored}"
                assert delete_list(base, work["id"], before)[0] == 409
            renamed_rev = lists(base)["Work"]["rev"]
            assert call(base, f"/api/lists/{work['id']}", "PATCH", {"name": "Jobs"})[0] == 200
            assert delete_list(base, work["id"], renamed_rev)[0] == 409, "a rename raises the revision"
            assert delete_list(base, work["id"], lists(base)["Jobs"]["rev"])[0] == 204
            assert call(base, f"/api/todos/{report['id']}", "PATCH", {"done": True})[0] == 404
            assert list(lists(base)) == ["Inbox", "House"]
            # R3: the cascade really removes the rows, not only hides them.
            assert orphans(db) == 0, "the deleted list's todos are still in the database"

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

            # A3, A2: the same refusals on every route and method, and a refusal changes nothing.
            json_type = {"Content-Type": "application/json"}
            house_rev = lists(base)["House"]["rev"]
            writes = [("POST", "/api/lists", {"name": "Evil"}),
                      ("PATCH", f"/api/lists/{home['id']}", {"name": "Evil"}),
                      ("DELETE", f"/api/lists/{home['id']}?rev={house_rev}", None),
                      ("POST", "/api/todos", {"listId": inbox["id"], "title": "Evil"}),
                      ("PATCH", f"/api/todos/{bank['id']}", {"done": False}),
                      ("DELETE", f"/api/todos/{bank['id']}", None)]
            reads = [("GET", path, None) for path in
                     ("/", "/health", "/api/lists", f"/api/todos?list={inbox['id']}&status=all")]
            # Every method, not only the six routes: HEAD, a preflight and methods the app does not use.
            others = [(method, path, None) for method, path in
                      (("HEAD", "/"), ("HEAD", "/api/lists"), ("OPTIONS", "/api/lists"), ("PUT", "/api/lists"),
                       ("TRACE", "/"), ("FOO-BAR", "/api/lists"), ("get", "/api/lists"))]
            before = snapshot(base)

            def send(method, path, payload, host=here, headers=None, body=None):
                if body is None and payload is not None:
                    body = json.dumps(payload).encode()
                extra = {**(json_type if body is not None else {}), **(headers or {})}
                return raw(base, path, method, host, extra, body)[0]

            # A3: only localhost or an IP address may be the Host (stops DNS rebinding).
            for host in (f"evil.example:{port}", f"localhost.evil.example:{port}", f"127.0.0.1.evil.example:{port}",
                         "1.2.3.4.evil.example", f"localhost.:{port}", "127.0.0.1:x", "a@127.0.0.1", "", None,
                         [here, f"evil.example:{port}"]):
                for method, path, payload in reads + writes:
                    assert send(method, path, payload, host) == 403, f"{method} {path} with Host {host!r}"
            for host in ("localhost", f"localhost:{port}", "[::1]", f"[::1]:{port}", here):
                assert raw(base, "/api/lists", host=host)[0] == 200, f"Host {host!r} must be served"
            # A3: "a dotted IPv4 address" or "a bracketed IPv6 address" is a real address, not digit-shaped text.
            for host in ("1.2.3.4.5", "256.1.1.1", "1.2.3", f"999.0.0.1:{port}", "[1::2::3]", "[::1", "[::g]"):
                assert send("GET", "/api/lists", None, host) == 403, f"Host {host!r} is not an IP address: 403"
            # A3: the check runs for every method, before any route.
            for host in (f"evil.example:{port}", None):
                for method, path, payload in others:
                    assert send(method, path, payload, host) == 403, f"every method checks Host: {method} {path} {host!r}"
            # A1: the phone opens the app by the laptop's address; a port is any run of digits.
            for host in ("192.168.1.20:8080", "192.168.1.20", "localhost:000080", f"[fe80::1]:{port}"):
                assert raw(base, "/api/lists", host=host)[0] == 200, f"a LAN address Host must be served: {host!r}"
            lan = {"Host": "192.168.1.20:8080", "Origin": "http://192.168.1.20:8080"}
            code, phone = call(base, "/api/lists", "POST", {"name": "Phone"}, headers=lan)
            assert code == 201, f"a same-origin write from the phone's LAN address must succeed: {phone}"
            assert delete_list(base, phone["id"], lists(base)["Phone"]["rev"], lan)[0] == 204
            # A3: a malformed header line must not hide a second Host header from the check.
            status_line, _, _ = wire(base, f"GET /api/lists HTTP/1.1\r\nHost: {here}\r\nBroken header line\r\n"
                                            f"Host: evil.example\r\n\r\n".encode())
            assert re.match(r"HTTP/1\.[01] 4[0-9][0-9] ", status_line), \
                f"a malformed header block must be refused, not served: {status_line!r}"
            # A2: writes another website could send are refused on every write route.
            for origin in ("http://evil.example", "null", f"https://{here}", "http://127.0.0.1:1",
                           f"http://localhost:{port}", f"http://{here}.evil.example"):
                for method, path, payload in writes:
                    assert send(method, path, payload, headers={"Origin": origin}) == 403, f"{method} {path} {origin}"
            # A2: the Origin must be exactly one value: a second, foreign Origin header is refused too.
            for method, path, payload in writes:
                assert send(method, path, payload, headers={"Origin": [f"http://{here}", "http://evil.example"]}) == 403, \
                    f"two Origin headers on {method} {path} must be refused"
            for method, path, payload in writes:
                if payload is None:
                    continue
                for kind in ("text/plain", "application/x-www-form-urlencoded"):
                    assert send(method, path, payload, headers={"Content-Type": kind}) == 415, f"{method} {path} {kind}"
                assert send(method, path, None, body=big) == 413, f"{method} {path} oversized"
            assert snapshot(base) == before, "a refused request changed data or a revision"
            # The app's own page (same Origin, by IP or localhost, JSON with a charset) still works.
            same = {"Origin": base, "Content-Type": "application/json; charset=utf-8"}
            code, garden = call(base, "/api/lists", "POST", {"name": "Garden"}, headers=same)
            assert code == 201, garden
            local = {"Host": f"localhost:{port}", "Origin": f"http://localhost:{port}"}
            assert delete_list(base, garden["id"], lists(base)["Garden"]["rev"], local)[0] == 204

            # A8, R2: malformed input from any client is refused (4xx, never a crash) and changes nothing.
            before = snapshot(base)
            todo_route = f"/api/todos/{bank['id']}"
            malformed = [("PATCH", "/api/lists/abc", {"name": "Bad id"}),
                         ("PATCH", "/api/lists/" + "9" * 30, {"name": "Huge id"}),
                         ("DELETE", "/api/lists/(1)OR(inbox=0)?rev=1", None),
                         ("DELETE", f"/api/lists/{home['id']}?rev=" + "9" * 30, None),
                         ("DELETE", f"/api/todos/{'9' * 30}", None),
                         ("PATCH", "/api/todos/-1", {"done": True}),
                         ("GET", "/api/todos?status=all", None), ("GET", "/api/todos?list=abc", None),
                         ("GET", "/api/todos?list=" + "9" * 30, None), ("GET", "/api/nothing", None),
                         ("PUT", "/api/lists", {"name": "Put"}), ("POST", "/api/lists/1", {"name": "Post"})]
            for method, path, payload in malformed:
                code = send(method, path, payload)
                assert 400 <= code < 500, f"malformed input must get a 4xx, not {code}: {method} {path}"
            bodies = [(b"", "an empty body"), (b"\xff\xfe{}", "invalid UTF-8"),
                      (b"[" * 20_000 + b"]" * 20_000, "deeply nested JSON"),
                      (b'{"name": "\\ud800"}', "a lone surrogate"),
                      (b'{"listId": 1' + b"0" * 5000 + b', "title": "Huge"}', "a 5000-digit listId"),
                      (b'{"listId": %d, "title": "\\udfff"}' % inbox["id"], "a lone surrogate title")]
            for body, what in bodies:
                for path in ("/api/lists", "/api/todos"):
                    code = send("POST", path, None, body=body)
                    assert 400 <= code < 500, f"malformed input must get a 4xx, not {code}: {what} to {path}"
            assert 400 <= send("PATCH", todo_route, None, body=b'{"done": tr') < 500, "malformed input: cut JSON"
            # Framing: chunked bodies, two Content-Length values, a body shorter than declared, a huge length.
            framing = [b"POST /api/lists HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\n"
                       b"Transfer-Encoding: chunked\r\n\r\n11\r\n{\"name\": \"Chunk\"}\r\n0\r\n\r\n",
                       b"POST /api/lists HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\n"
                       b"Content-Length: 16\r\nContent-Length: 2\r\n\r\n{\"name\": \"Twice\"}",
                       b"POST /api/lists HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\n"
                       b"Content-Length: 40\r\n\r\n{\"name\": \"Short\"}",
                       b"POST /api/lists HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\n"
                       b"Content-Length: -5\r\n\r\n{}"]
            for request in framing:
                status_line, pairs, _ = wire(base, request % here.encode())
                assert re.match(r"HTTP/1\.[01] 4[0-9][0-9] ", status_line), \
                    f"malformed framing must get a 4xx: {status_line!r} for {request[:90]!r}"
            status_line, _, _ = wire(base, b"POST /api/lists HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\n"
                                           b"Content-Length: %s\r\n\r\n{}" % (here.encode(), b"9" * 30))
            assert status_line.split()[1:2] == ["413"], f"a huge Content-Length is oversized (413): {status_line!r}"
            # A request target is a path and a query: a fragment is malformed and changes nothing.
            for target in (f"/api/lists/{home['id']}?rev={lists(base)['House']['rev']}#x", "/health#x",
                           "http://[::1/api/lists"):
                status_line, _, _ = wire(base, f"DELETE {target} HTTP/1.1\r\nHost: {here}\r\n\r\n".encode())
                assert re.match(r"HTTP/1\.[01] 4[0-9][0-9] ", status_line), \
                    f"a malformed request target must get a 4xx: {status_line!r} for {target}"
            assert snapshot(base) == before, "a malformed request changed data or a revision"
            # A8: 64 KB is the limit: a 64,000-byte body is accepted and 65,537 bytes are refused.
            padded = json.dumps({"name": "Pad", "pad": ""}).encode()
            padded = json.dumps({"name": "Pad", "pad": "p" * (64_000 - len(padded))}).encode()
            assert len(padded) == 64_000 and send("POST", "/api/lists", None, body=padded) == 201, \
                "a 64,000-byte body is within the limit"
            # A current revision written with leading zeros is still the current revision (it is digits).
            assert delete_list(base, lists(base)["Pad"]["id"], "000" + str(lists(base)["Pad"]["rev"]))[0] == 204, \
                "a current revision with leading zeros is still the current revision"
            assert send("POST", "/api/lists", None, body=b" " * 65_535 + b"{}") == 413, "65,537 bytes is over the limit"
            # A8: a client that stops mid-body does not stop another device from using the app.
            target = urlsplit(base)
            stalled = socket.create_connection((target.hostname, target.port), timeout=5)
            try:
                stalled.sendall(f"POST /api/lists HTTP/1.1\r\nHost: {here}\r\nContent-Type: application/json\r\n"
                                f"Content-Length: 100\r\n\r\n{{\"na".encode())
                try:
                    answer = call(base, "/health")
                except OSError as exc:
                    raise AssertionError(f"a stalled request blocked another client: {exc}")
                assert answer == (200, {"ok": True}), answer
            finally:
                stalled.close()
            assert call(base, "/health") == (200, {"ok": True}), "the server stopped serving after malformed input"

            # A4, A5: no CORS, not frameable, no MIME sniffing, on every response.
            replies = [raw(base, path, host=here, headers={"Origin": "http://evil.example"})
                       for path in ("/", "/api/lists", "/missing.txt")]
            replies += [raw(base, "/api/lists", host=f"evil.example:{port}"),
                        raw(base, "/api/lists", "POST", here, {**json_type, "Origin": "http://evil.example"}, b"{}"),
                        raw(base, "/api/lists", "POST", here, json_type, big),
                        raw(base, "/api/lists", "POST", here, {"Content-Type": "text/plain"}, b"{}"),
                        raw(base, "/api/lists", "POST", here, json_type, b"not json")]
            assert [code for code, _ in replies[3:]] == [403, 403, 413, 415, 400], [code for code, _ in replies]
            assert replies[1][1].get("content-type", "").startswith("application/json"), replies[1][1]
            for path, (_, headers) in zip(("/", "/api/lists", "/missing.txt", "403 host", "403 origin", "413",
                                          "415", "400"), replies):
                assert "access-control-allow-origin" not in headers, f"{path} sends a CORS header"
                policy_text = headers.get("content-security-policy", "")
                assert "frame-ancestors 'none'" in policy_text and "default-src 'self'" in policy_text, (path, policy_text)
                assert headers.get("x-frame-options", "").upper() == "DENY", path
                assert headers.get("x-content-type-options", "").lower() == "nosniff", path
            # Every response path: assets, reads, each write's success and conflict, a preflight, other
            # methods, and each refusal; exactly one of each header, the CSP exactly as the contract gives it.
            evil = {"Origin": "http://evil.example"}
            code, kept = call(base, "/api/todos", "POST", {"listId": home["id"], "title": "Kept"})
            paths = [(method, path, None, here, evil) for method, path in
                     (("GET", "/"), ("GET", "/app.js"), ("GET", "/styles.css"), ("HEAD", "/"), ("GET", "/health"),
                      ("GET", "/api/lists"), ("GET", f"/api/todos?list={home['id']}&status=all"),
                      ("GET", "/api/todos?list=99999&status=all"), ("GET", "/api/todos?list=1&status=bogus"),
                      ("PUT", "/api/lists"), ("FOO-BAR", "/api/lists"), ("GET", "/server.py"))]
            paths += [("OPTIONS", "/api/lists", None, here, {**evil, "Access-Control-Request-Method": "POST",
                                                            "Access-Control-Request-Headers": "content-type"}),
                      ("POST", "/api/lists", b'{"name": "Header"}', here, json_type),
                      ("PATCH", f"/api/todos/{kept['id']}", b'{"done": true}', here, json_type),
                      ("DELETE", f"/api/lists/{home['id']}?rev=1", None, here, {}),
                      ("POST", "/api/lists", b'{"name": "Header"}', here, json_type),
                      ("DELETE", f"/api/todos/{kept['id']}", None, here, {}),
                      ("DELETE", f"/api/todos/{kept['id']}", None, here, {}),
                      ("GET", "/api/lists", None, None, {}), ("POST", "/api/lists", b"{}", here, {**json_type, **evil})]
            seen = set()
            for method, path, body, host, headers in paths:
                status, pairs, reply = exchange(base, path, method, host, headers, body)
                seen.add(status)
                policy(pairs, f"{method} {path} ({status})")
                if 400 <= status < 500 and method != "HEAD":
                    error_shape(status, pairs, reply, f"{method} {path}")
            assert {200, 201, 204, 403, 404, 409} <= seen, f"every kind of reply was checked: {sorted(seen)}"
            assert delete_list(base, lists(base)["Header"]["id"], lists(base)["Header"]["rev"])[0] == 204
            # Replies the HTTP parser writes itself (a bad request line or version) are framed HTTP with
            # the same headers: never a bare body.
            for request in (b"GARBAGE\r\n\r\n", b"GET / HTTP/x.y\r\nHost: %s\r\n\r\n", b"GET /\r\n\r\n",
                            b"GET / HTTP/1.1 extra\r\nHost: %s\r\n\r\n", b"GET / HTTP/1.1\r\nHost: %s\r\nX: " +
                            b"y" * 70_000 + b"\r\n\r\n"):
                status_line, pairs, _ = wire(base, request.replace(b"%s", here.encode()))
                assert re.match(r"HTTP/1\.[01] [45][0-9][0-9] ", status_line), \
                    f"the parser's own error reply must be framed HTTP: {status_line!r} for {request[:40]!r}"
                policy(pairs, f"parser reply {status_line!r}")

            # C10: simultaneous writes wait for each other instead of failing.
            code, busy = call(base, "/api/lists", "POST", {"name": "Busy"})
            first = lists(base)["Busy"]["rev"]
            with ThreadPoolExecutor(20) as pool:
                codes = list(pool.map(lambda n: call(base, "/api/todos", "POST",
                                                     {"listId": busy["id"], "title": f"Task {n}"})[0], range(20)))
            assert codes == [201] * 20, codes
            assert lists(base)["Busy"]["total"] == 20
            assert lists(base)["Busy"]["rev"] == first + 20, "each add raises the revision by exactly one"
            assert delete_list(base, busy["id"], lists(base)["Busy"]["rev"])[0] == 204

            # C1, C9: racing writes. An add and a delete carrying the revision from before the add never
            # both succeed (the todo would vanish with a stale delete); two devices taking one name: one 409.
            for round_number in range(25):
                code, racing = call(base, "/api/lists", "POST", {"name": f"Race {round_number}"})
                start = threading.Barrier(2)

                def add(list_id=racing["id"]):
                    start.wait()
                    return call(base, "/api/todos", "POST", {"listId": list_id, "title": "Racer"})[0]

                def remove(list_id=racing["id"], rev=racing["rev"]):
                    start.wait()
                    return delete_list(base, list_id, rev)[0]

                with ThreadPoolExecutor(2) as pool:
                    added, removed = pool.submit(add), pool.submit(remove)
                    outcome = (added.result(), removed.result())
                assert outcome in {(201, 409), (404, 204)}, \
                    f"an add raced a delete with the older revision: {outcome} (201 and 204 loses the todo)"
                if outcome == (201, 409):
                    current = lists(base)[f"Race {round_number}"]
                    assert delete_list(base, current["id"], current["rev"])[0] == 204
                start = threading.Barrier(2)

                def take(name=f"Twin {round_number}"):
                    start.wait()
                    return call(base, "/api/lists", "POST", {"name": name})[0]

                with ThreadPoolExecutor(2) as pool:
                    outcome = sorted(pool.map(lambda _: take(), range(2)))
                assert outcome == [201, 409], f"two devices created the same name at once: {outcome}"
                twin = lists(base)[f"Twin {round_number}"]
                assert delete_list(base, twin["id"], twin["rev"])[0] == 204
            assert orphans(db) == 0, "racing writes left todos without a list"

            # R3: leave a populated list, then retire the highest ids before the restart.
            code, chores = call(base, "/api/todos", "POST", {"listId": home["id"], "title": "Sweep"})
            assert call(base, f"/api/todos/{chores['id']}", "PATCH", {"done": True})[0] == 200
            code, last = call(base, "/api/lists", "POST", {"name": "Last"})
            code, last_todo = call(base, "/api/todos", "POST", {"listId": last["id"], "title": "Last todo"})
            assert delete_list(base, last["id"], lists(base)["Last"]["rev"])[0] == 204
            every_row_shape(base)
            # A10: still the owner's only after writes (journal files come and go during them).
            owner_only(directory, "after writes")
            state = snapshot(base)

        # A10: a database copied in with permissions for others is made the owner's only at startup.
        db.chmod(0o644)
        # R3: data survives a restart.
        with server(root, db) as base:
            owner_only(directory, "an existing database others could read must be made owner-only at startup")
            assert list(lists(base)) == ["Inbox", "House"]
            todos = call(base, f"/api/todos?list={inbox['id']}&status=all")[1]
            assert [(t["title"], t["done"]) for t in todos] == [("Call bank", True)], todos
            assert snapshot(base) == state, "a restart changed lists, todos, ids or revisions"
            assert [item["name"] for item in call(base, "/api/lists")[1] if item["inbox"]] == ["Inbox"], "one Inbox"
            code, after = call(base, "/api/lists", "POST", {"name": "After"})
            assert code == 201 and after["id"] > last["id"], "a deleted maximum list id was reused after a restart"
            code, after_todo = call(base, "/api/todos", "POST", {"listId": after["id"], "title": "After"})
            assert code == 201 and after_todo["id"] > last_todo["id"], "a deleted maximum todo id was reused after a restart"
            assert orphans(db) == 0, "the deleted list's todos are still in the database"

    deployed(root)
    if second_loopback():
        with tempfile.TemporaryDirectory() as directory, \
                server(root, Path(directory) / "lan.sqlite3", host="0.0.0.0") as base:
            assert reachable("127.0.0.2", int(base.rsplit(":", 1)[1])), "--host 0.0.0.0 must listen beyond loopback"
    print("Lists, todos, validation, filters, case-folded names, revision-guarded delete, unused ids, "
          "browser safety and headers, cascade delete and restart persistence passed.")


def deployed(root):
    """A7 in the documented layout (product.md: `python3 server.py --db todos.sqlite3` in the app folder):
    only the three assets are served, never the database, its journals or any other file there."""
    with tempfile.TemporaryDirectory() as directory:
        app = Path(directory) / "app"
        shutil.copytree(root, app, ignore=shutil.ignore_patterns(".vesper-gates", "__pycache__"))
        for name in ("notes.txt", ".env", "todos.sqlite3-journal", "todos.sqlite3-wal", "index.htm", "README.md"):
            (app / name).write_text("inert fixture file\n")
        with server(app, "todos.sqlite3", cwd=app) as base:
            here = base.split("//", 1)[1]
            assert call(base, "/api/todos", "POST", {"listId": lists(base)["Inbox"]["id"], "title": "Stored"})[0] == 201
            for path in ("/todos.sqlite3", "/todos.sqlite3-journal", "/todos.sqlite3-wal", "/notes.txt", "/.env",
                         "/index.htm", "/README.md", "/server.py", "/Server.py", "/./server.py", "/app/server.py",
                         "/app.js/", "/static/../server.py", "/%2e%2e/app/server.py", "/index.html"):
                for method in ("GET", "HEAD"):
                    assert raw(base, path, method, host=here)[0] == 404, \
                        f"only /, /app.js and /styles.css are served: {method} {path} must be 404"
            for path in ("/", "/app.js", "/styles.css"):
                if (app / {"/": "index.html"}.get(path, path[1:])).exists():
                    assert raw(base, path, "HEAD", host=here)[0] == 200, f"HEAD {path} serves the asset"
                assert raw(base, path, "HEAD", host="evil.example")[0] == 403, f"HEAD {path} checks Host"


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve())
