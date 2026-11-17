from collections import deque
from contextlib import contextmanager
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def wait_for_ready(process, timeout):
    deadline = time.monotonic() + timeout
    recent = deque(maxlen=6)
    stage = "unreported"
    partial = b""
    with selectors.DefaultSelector() as ready:
        ready.register(process.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if not ready.select(max(0, deadline - time.monotonic())):
                break
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
                break
            *lines, partial = (partial + chunk).split(b"\n")
            for raw in lines:
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("READY http://127.0.0.1:"):
                    return line.split(" ", 1)[1]
                if line.startswith("STARTUP "):
                    stage = line.removeprefix("STARTUP ")[:180]
                recent.append(line[-180:])
            partial = partial[-180:]
    if partial:
        recent.append(partial.decode("utf-8", errors="replace"))
    status = process.poll()
    if status is None:
        status = "unavailable (running)"
    output = "\n".join(recent) or "(none)"
    raise AssertionError(
        f"Server did not announce readiness (deadline {timeout}s). "
        f"Last startup stage: {stage}. Exit status: {status}.\nRecent output:\n{output}"
    )


@contextmanager
def server(root, db, *, timeout=6):
    command = [sys.executable, "-B", str(root / "server.py"), "--port", "0", "--db", str(db)]
    env = dict(os.environ, STOCKROOM_STARTUP_DIAGNOSTICS="1")
    with subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          env=env) as process:
        try:
            yield wait_for_ready(process, timeout)
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
