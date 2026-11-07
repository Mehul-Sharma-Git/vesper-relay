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
                assert ready.select(6), "Server did not announce readiness"
            line = process.stdout.readline().strip()
            assert line.startswith("READY http://127.0.0.1:"), f"Startup failed: {line}"
            yield line.split(" ", 1)[1]
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()


def request(base, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"} if data else {}
    req = Request(base + path, data=data, method=method, headers=headers)
    try:
        response = urlopen(req, timeout=4)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, json.loads(response.read())


def check(root):
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "inventory.sqlite3"
        with server(root, db) as base:
            assert request(base, "/health")[0] == 200
            body = {"requestId": "test-1", "name": "  Storage bins  ", "room": "Kitchen", "quantity": 2}
            code, item = request(base, "/api/items", "POST", body)
            assert code == 201 and item["name"] == "Storage bins" and item["version"] == 1
            assert item["status"] == "needed"
            assert request(base, "/api/items", "POST", body) == (200, item)
            assert request(base, "/api/items", "POST", {**body, "quantity": 3})[0] == 409
            assert request(base, "/api/items", "POST", {**body, "requestId": "test-2", "quantity": True})[0] == 400
            assert request(base, "/api/items", "POST", {**body, "requestId": "test-3", "name": " "})[0] == 400
            assert request(base, "/api/items", "POST", {**body, "requestId": "test-4", "room": "Garage"})[0] == 400
            assert request(base, "/api/items?room=Kitchen") == (200, [item])
            assert request(base, "/api/items?room=Bedroom") == (200, [])
            path = f"/api/items/{item['id']}"
            code, bought = request(base, path, "PATCH", {"status": "bought", "version": 1})
            assert code == 200 and bought["status"] == "bought" and bought["version"] == 2
            code, stale = request(base, path, "PATCH", {"status": "needed", "version": 1})
            assert code == 409 and stale["current"] == bought
            assert request(base, "/api/items?status=needed") == (200, [])
        with server(root, db) as base:
            assert request(base, "/api/items?status=bought") == (200, [bought])
    print("Create, replay, input validation, filters, stale edit, and database restart passed.")


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve())
