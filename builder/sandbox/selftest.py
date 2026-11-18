"""Sandbox selftest: from inside every operation, try to break out. Every attempt must fail.

Each operation runs a probe through the same job builders and backend the runner uses. The
probe tries to write outside /work and to a read-only mount, read the host home, find the
engine's socket, run as root or keep capabilities, and reach the internet directly. Brain
operations also ask their proxy for a host that isn't theirs (must be refused) and for their
provider (must work, so the refusal means something). Every operation checks that loopback
works, which servers started by gates need.
"""
import json
from pathlib import Path
import sys
import tempfile

from . import agent_job, backend, check_job, command_job

PROVIDER = "api.anthropic.com"
PROBE = r'''
import json, os, socket, sys, time
here = os.path.dirname(os.path.abspath(__file__))
args = json.load(open(os.path.join(here, "probe.json")))
operation, host_home = args["operation"], args["host_home"]
results = {}

def attempt(label, action):  # must fail
    try:
        action()
        results[label] = "ESCAPED"
    except Exception:
        results[label] = "blocked"

def control(label, action):  # must work
    try:
        action()
        results[label] = "ok"
    except Exception as exc:
        results[label] = "FAILED: %s" % exc

def write(path):
    with open(path, "w") as handle:
        handle.write("escape")

def present(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if os.path.isdir(path):
        os.listdir(path)

def root():
    if os.getuid() != 0:
        raise PermissionError("not root")

def capabilities():
    for line in open("/proc/self/status"):
        if line.startswith("CapEff:") and int(line.split()[1], 16):
            return
    raise PermissionError("no capabilities")

def connect(host, port=443):
    socket.create_connection((host, port), timeout=5).close()

def loopback():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    socket.create_connection(server.getsockname(), timeout=5).close()
    server.close()

def tunnel(host):
    proxy = os.environ["HTTPS_PROXY"].split("//", 1)[1].rstrip("/")
    name, port = proxy.rsplit(":", 1)
    for _ in range(40):  # the proxy may still be starting
        try:
            sock = socket.create_connection((name, int(port)), timeout=10)
            break
        except OSError:
            time.sleep(0.25)
    else:
        raise ConnectionError("proxy unreachable")
    sock.sendall(("CONNECT %s:443 HTTP/1.1\r\nHost: %s:443\r\n\r\n" % (host, host)).encode())
    status = sock.recv(200).decode("latin-1").split("\r\n")[0]
    sock.close()
    if " 200 " not in status + " ":
        raise PermissionError(status)

attempt("write the image (/usr)", lambda: write("/usr/vesper-escape"))
attempt("write /etc", lambda: write("/etc/vesper-escape"))
attempt("write /", lambda: write("/vesper-escape"))
attempt("read the host home", lambda: present(host_home))
def engine_socket():
    found = [path for path in ("/var/run/docker.sock", "/run/docker.sock", "/run/podman/podman.sock")
             if os.path.exists(path)]
    if not found:
        raise FileNotFoundError("no engine socket")

attempt("find the engine socket", engine_socket)
attempt("run as root", root)
attempt("keep capabilities", capabilities)
if args["work_readonly"]:
    attempt("write the read-only mount", lambda: write("/work/vesper-escape"))
else:
    control("write /work", lambda: write("/work/vesper-probe-ok"))
if args["cache"] == "ro":
    attempt("write the read-only cache", lambda: write("/cache/vesper-escape"))
if operation != "setup":
    attempt("reach the internet directly", lambda: connect("1.1.1.1"))
    attempt("reach a named host directly", lambda: connect("example.com"))
if args["proxied"]:
    attempt("tunnel to another host", lambda: tunnel("example.com"))
    control("tunnel to the provider", lambda: tunnel(args["provider"]))
control("loopback", loopback)
print("VESPER_SELFTEST " + json.dumps({"operation": operation, "results": results}))
'''


def jobs(base):
    """One probe job per operation, built exactly as the runner builds its jobs."""
    built = {}
    for operation in ("worker", "reviewer", "consult"):
        work = base / operation / "work"
        work.mkdir(parents=True)
        out = base / operation / "out"
        out.mkdir()
        built[operation] = (agent_job(operation, ("python3", "-I", "/work/probe.py"), work,
                                      out=out if operation != "worker" else None, hosts=(PROVIDER,)), work)
    for operation in ("setup", "check-command"):
        work, cache = base / operation / "work", base / operation / "cache"
        work.mkdir(parents=True)
        cache.mkdir()
        built[operation] = (command_job(operation, ("python3", "-I", "/work/probe.py"), work,
                                        dependencies=cache), work)
    home = base / "check"
    (home / "checks").mkdir(parents=True)
    (home / "candidate").mkdir()
    built["check"] = (check_job(home, "probe.py"), home / "checks")
    return built


def run(name="docker", base=None):
    """Run every probe; print one line per attempt; return 0 only when every attempt failed."""
    engine = backend(name)
    if engine is None:
        print("selftest: the none backend has no sandbox to test", file=sys.stderr)
        return 1
    engine.check()
    from ..learning import state_home
    root = Path(base) if base else state_home()
    root.mkdir(parents=True, exist_ok=True)
    failures = 0
    # Under the state directory: a Colima engine shares only the home directory by default.
    with tempfile.TemporaryDirectory(prefix="sandbox-selftest-", dir=root) as temporary:
        for operation, (job, probe_dir) in jobs(Path(temporary)).items():
            settings = {"operation": operation, "host_home": str(Path.home()), "provider": PROVIDER,
                        "work_readonly": job.work_readonly, "proxied": job.network == "egress",
                        "cache": next(("ro" if readonly else "rw" for _, target, readonly in job.mounts
                                       if target == "/cache"), None)}
            (probe_dir / "probe.py").write_text(PROBE, encoding="utf-8")
            (probe_dir / "probe.json").write_text(json.dumps(settings), encoding="utf-8")
            for path in (probe_dir / "probe.py", probe_dir / "probe.json"):
                path.chmod(0o644)
            log = Path(temporary) / f"{operation}.log"
            code = engine.run(job, input_text="", log=log, timeout=180)
            lines = [line for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
                     if line.startswith("VESPER_SELFTEST ")]
            if code != 0 or not lines:
                failures += 1
                print(f"FAIL  {operation}: probe exited {code}\n{log.read_text(errors='replace')[-2000:]}")
                continue
            for label, outcome in json.loads(lines[-1].split(" ", 1)[1])["results"].items():
                good = outcome in ("blocked", "ok")
                failures += not good
                print(f"{'ok  ' if good else 'FAIL'}  {operation:<13} {label}: {outcome}")
    print(f"\nselftest ({engine.name}): " + ("every escape attempt failed" if not failures
                                            else f"{failures} problem(s)"))
    return 1 if failures else 0
