"""`vesper doctor`: is this machine ready for automatic runs? Every failure prints its fix.

Checks, in order: Python version; the personal and project config; the sandbox backend
(engine on PATH, engine running, image built for this machine's architecture, and the
engine can see Vesper's state folder, where runs live); then, for
every brain in the config, its adapter's CLI (inside the image when a sandbox runs it, on
this machine with ``none``), whether ``--help`` still lists every flag the adapter uses
(CLIs change their flags over time), the sandbox login, and a tiny dry call per distinct
brain (``--no-call`` skips it).

Everything the checks ask the machine goes through ``Probe``, so tests can give it a fake
environment. ``vesper setup`` (builder/wizard.py) shares the probe and the fix texts.
"""
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

from .contracts import BuilderError

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
MINIMUM = (3, 11)
PYTHON_FIX = ("Install Python 3.11 or newer: brew install python@3.12 (macOS), your distribution's python3.12 "
              "package (Linux), or uv python install 3.12. The vesper command finds it on its own")
DRY_PROMPT = "This is a connection check. Reply with the single word OK. Do not use any tools."
DRY_TIMEOUT = 180
FLAG = re.compile(r"(?<![\w-])(--?[A-Za-z][A-Za-z0-9-]*)")
MARKER = ".vesper-doctor"
SHARE_FIX = ("Runs must live in a folder the engine shares. Colima shares only your home folder; Docker Desktop "
             "shares /Users, /private, /tmp and /var/folders. Keep VESPER_STATE_DIR and --project paths inside "
             "one, or share the folder (colima start --mount PATH:w, or Docker Desktop > Settings > Resources > "
             "File sharing)")
ARCHES = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}


def host_arch(machine):
    """A machine name (``platform.machine()``, an image's Architecture) as arm64 or amd64."""
    return ARCHES.get(str(machine).lower(), str(machine).lower())


class Probe:
    """The machine as doctor and setup see it: the OS, programs on PATH, files under HOME."""

    def __init__(self, environ=None):
        self.environ = dict(os.environ if environ is None else environ)

    def system(self):
        return platform.system()

    def machine(self):
        return platform.machine()

    def python(self):
        return tuple(sys.version_info[:3])

    def which(self, name):
        return shutil.which(name, path=self.environ.get("PATH", os.defpath))

    def home(self):
        return Path(self.environ["HOME"]) if self.environ.get("HOME") else Path.home()

    def state(self):
        """Vesper's state directory (under HOME, so a sandbox engine that shares only HOME can mount it)."""
        if self.environ.get("VESPER_STATE_DIR"):
            return Path(self.environ["VESPER_STATE_DIR"]).expanduser()
        base = self.environ.get("XDG_STATE_HOME") or self.home() / ".local" / "state"
        return Path(base).expanduser() / "vesper-relay"

    def run(self, argv, timeout=120):
        """Run quietly; return (exit status, combined output). 127: not found, 124: timed out."""
        try:
            result = subprocess.run(list(map(str, argv)), env=self.environ, capture_output=True, text=True,
                                    timeout=timeout, stdin=subprocess.DEVNULL)
        except FileNotFoundError as exc:
            return 127, str(exc)
        except subprocess.TimeoutExpired:
            return 124, f"timed out after {timeout} s"
        except OSError as exc:
            return 126, str(exc)
        return result.returncode, (result.stdout or "") + (result.stderr or "")

    def show(self, argv):
        """Run with the output on the terminal (installs, builds); return the exit status."""
        try:
            return subprocess.run(list(map(str, argv)), env=self.environ).returncode
        except OSError as exc:
            print(f"vesper: {exc}", file=sys.stderr)
            return 127

    def keychain(self):
        """The Keychain is offered only on a Mac that has the ``security`` command."""
        return self.system() == "Darwin" and bool(self.which("security"))

    def secret(self, name):
        from .sandbox import secrets
        try:
            return secrets.read(name, environ=self.environ)
        except BuilderError:
            return None

    def store(self, name, value, where):
        from .sandbox import secrets
        return secrets.store(name, value, where, environ=self.environ)

    def login_file(self, value):
        return self.home() / value[2:] if value.startswith("~/") else Path(value)

    def login_ready(self, login):
        kind, value = login
        return bool(self.secret(value)) if kind == "env" else self.login_file(value).is_file()

    def dry_call(self, brain, backend):
        """A tiny consultation through the real launch path; returns (exit status, output)."""
        from .brains import launch, reply_path
        from .sandbox import backend as sandbox
        engine = sandbox(backend).check() if backend != "none" else None
        place = self.state()
        place.mkdir(parents=True, mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="doctor-", dir=place) as temporary:
            directory = Path(temporary)
            work = directory / "work"
            work.mkdir()
            log, response = directory / "call.log", directory / "response.md"
            code = launch(brain, "consult", engine, engine is None, work=work, input_text=DRY_PROMPT, log=log,
                          timeout=DRY_TIMEOUT, response=response, max_turns=2)
            reply = reply_path(brain, response, log, engine)  # never an event-stream log (P2-T10)
            if reply is None:  # no reply; a failed call still shows why
                return code, "" if code == 0 or not log.is_file() else brain.adapter.summary(
                    log.read_text(encoding="utf-8", errors="replace"))
            return code, reply.read_text(encoding="utf-8", errors="replace") if reply.is_file() else ""


# Fixes shared with `vesper setup`: (command it may offer to run, or None; text for the user).
def install_engine(name, system, probe):
    if system == "Darwin":
        if name == "docker":
            argv = ["brew", "install", "colima", "docker"]
            text = ("brew install colima docker, then colima start (or install Docker Desktop from "
                    "https://www.docker.com/products/docker-desktop/ and open it once)")
        else:
            argv = ["brew", "install", "podman"]
            text = "brew install podman, then podman machine init && podman machine start"
        return (argv if probe.which("brew") else None), text + ("" if probe.which("brew") else
                                                                " (Homebrew: https://brew.sh)")
    if name == "docker":
        return None, "Install Docker Engine: https://docs.docker.com/engine/install/ (then add yourself to the docker group)"
    return None, "Install Podman with your package manager: sudo apt install podman, or sudo dnf install podman"


def start_engine(name, system, probe):
    if system == "Darwin":
        if name == "podman":
            return ["podman", "machine", "start"], ("podman machine start (the first time: podman machine init, "
                                                    "then podman machine start)")
        if probe.which("colima"):
            return ["colima", "start"], "colima start"
        return None, "Open Docker Desktop and wait until it says it is running, or install Colima and run colima start"
    if name == "docker":
        return None, "sudo systemctl start docker (and check that `docker info` works without sudo)"
    return None, "Check that `podman info` works (rootless Podman needs no service)"


def build_fix(name, platform_arch=None):
    return f"vesper sandbox build --backend {name}" + (f" --platform linux/{platform_arch}" if platform_arch else "")


def used_flags(adapter):
    """Every flag the adapter's worker, reviewer and consult commands use, minus the hidden ones."""
    from .brains import Brain, arguments
    from .team import TOOLS
    capabilities = adapter.capabilities
    brain = Brain(adapter.name, adapter, "model" if capabilities.model_select else None,
                  "high" if capabilities.effort_select else None)
    flags = set()
    for operation in ("worker", "reviewer", "consult"):
        argv = arguments(brain, operation, response="/out/response.json", schema={"type": "object"},
                         program=adapter.binary, tools=frozenset(TOOLS))
        flags.update(item for item in argv[1:] if FLAG.fullmatch(item))
    return frozenset(flags - set(adapter.hidden_flags))


def listed_flags(text):
    return {match.group(1) for match in FLAG.finditer(text)}


def configured_brains(values):
    from .brains import brain
    names = sorted({key.split(".")[1] for key in values if key.startswith("brains.") and key.count(".") >= 2})
    return [brain(name, values[f"brains.{name}.use"], values.get(f"brains.{name}.model"),
                  values.get(f"brains.{name}.effort")) for name in names]


def doctor(config=None, call=True, probe=None, project=None):
    """Run every check; return {"status": "ok"|"failed", "checks": [...]} (warnings don't fail)."""
    from .config import DEFAULTS, PROJECT_FILE, load_config, personal_path
    from .sandbox import Docker, Podman, image_tag
    probe = probe or Probe()
    checks = []

    def add(check, status, detail, fix=""):
        checks.append({"check": check, "status": status, "detail": detail, "fix": fix})
        return status == OK

    version = probe.python()
    text = ".".join(map(str, version))
    add("python", OK if version >= MINIMUM else FAIL, f"Python {text}",
        "" if version >= MINIMUM else PYTHON_FIX)

    personal, explicit = personal_path(config, probe.environ)
    values = dict(DEFAULTS)
    try:
        loaded = load_config(personal, Path(project or Path.cwd()) / PROJECT_FILE, explicit=explicit)
        values = {key: entry["value"] for key, entry in loaded["values"].items()}
        if loaded["files"]["personal"]["found"]:
            add("config", OK, f"{personal} is valid")
        else:
            add("config", WARN, f"No personal config at {personal}; built-in defaults apply",
                "vesper setup writes one")
    except (BuilderError, OSError, UnicodeError) as exc:
        add("config", FAIL, str(exc), f"Fix the file named above, or run vesper setup to write a new {personal}")

    from .approvals import TEST_CONFIRMER
    confirmer = values.get("approvals.confirmer", "tty")
    if probe.environ.get(TEST_CONFIRMER):
        add("approvals", WARN, f"{TEST_CONFIRMER} is set: protected actions are confirmed by a test stand-in "
            f"({probe.environ[TEST_CONFIRMER]}), not by you", f"unset {TEST_CONFIRMER}; it is for tests only")
    elif confirmer == "macos-dialog" and probe.system() != "Darwin":
        add("approvals", FAIL, "approvals.confirmer is macos-dialog, which needs macOS",
            '[approvals] confirmer = "tty" in the config')
    else:
        add("approvals", OK, f"approvals are confirmed by you through {confirmer}")

    system, backend = probe.system(), values.get("sandbox.backend", "docker")
    tag, program, engine = image_tag(), None, None
    if backend == "none":
        add("sandbox", WARN, "sandbox.backend is none: brains and gates run on this machine with your files "
            "and network", 'Set [sandbox] backend = "docker" (or podman) in the config, or run vesper setup')
        ready = True
    else:
        engine = {"docker": Docker, "podman": Podman}[backend]()
        program = probe.which(engine.program)
        ready = add("sandbox engine", OK if program else FAIL,
                    f"{backend}: {program}" if program else f"{backend} is not installed (not on PATH)",
                    "" if program else install_engine(backend, system, probe)[1])
        if ready:
            code, output = probe.run([program, "info"])
            ready = add("sandbox running", OK if code == 0 else FAIL,
                        f"{backend} is running" if code == 0 else f"{backend} could not be reached: {tail(output)}",
                        "" if code == 0 else start_engine(backend, system, probe)[1])
        else:
            add("sandbox running", SKIP, f"{backend} is not installed")
        if ready:
            code, output = probe.run([program, "image", "inspect", "--format", "{{.Architecture}}", tag])
            want, have = host_arch(probe.machine()), host_arch(output.strip().splitlines()[-1] if output.strip() else "")
            if code != 0 and probe.run([program, "image", "ls", "-q", tag])[1].strip():
                # Seen with Docker Desktop 29.2 (containerd image store): the tag is listed, yet
                # inspect answers "No such image" for a while. The runner's check would fail too.
                ready = add("sandbox image", FAIL, f"{backend} lists {tag} but cannot inspect it: {tail(output)}",
                            f"Run vesper doctor again in a minute; if it persists, restart {backend} or rebuild: "
                            + build_fix(backend))
            elif code != 0:
                ready = add("sandbox image", FAIL, f"Image {tag} is not built for {backend}", build_fix(backend))
            elif have != want:
                ready = add("sandbox image", FAIL, f"Image {tag} is built for {have}, this machine is {want}",
                            build_fix(backend, want))
            else:
                add("sandbox image", OK, f"{tag} ({have})")
        else:
            add("sandbox image", SKIP, f"{backend} is not ready")
        if ready:
            code, output = in_image(("test", "-f", MARKER), engine, program, probe, marker=True)
            ready = add("sandbox folders", OK if code == 0 else FAIL,
                        f"{backend} sees files under {probe.state()}" if code == 0 else
                        f"{backend} cannot see files under {probe.state()}: {tail(output) or f'exit {code}'}",
                        "" if code == 0 else SHARE_FIX)
        else:
            add("sandbox folders", SKIP, f"{backend} is not ready")

    try:
        brains = configured_brains(values)
    except BuilderError as exc:
        brains = []
        add("brains", FAIL, str(exc), "Fix [brains] in the config, or run vesper setup")
    if not brains and not any(item["check"] == "brains" for item in checks):
        add("brains", WARN, "No brains in the config: automatic runs need --brain NAME on every command",
            "vesper setup (one AI is enough for every role)")

    usable = {}
    for adapter in dict.fromkeys(item.adapter for item in brains):
        usable[adapter.name] = check_adapter(adapter, backend, ready, probe, add, engine, program, tag)

    seen = set()
    for item in brains:
        label = f"brain {item.name}: dry call"
        key = (item.adapter.name, item.model, item.effort)
        if key in seen:
            continue
        seen.add(key)
        if not call:
            add(label, SKIP, "skipped (--no-call)")
        elif not usable[item.adapter.name]:
            add(label, SKIP, f"{item.adapter.name} is not ready (see above)")
        else:
            try:
                code, output = probe.dry_call(item, backend)
            except (BuilderError, OSError) as exc:
                code, output = 1, str(exc)
            add(label, OK if code == 0 and output.strip() else FAIL,
                f"{item.adapter.name} answered" if code == 0 and output.strip()
                else f"exit {code}: {tail(output) or 'no reply'}",
                "" if code == 0 and output.strip() else
                f"Check the login ({item.adapter.login_help}), the model name and your plan limits, then run "
                "vesper doctor again")

    failed = any(item["status"] == FAIL for item in checks)
    return {"status": "failed" if failed else "ok", "checks": checks}


def check_adapter(adapter, backend, ready, probe, add, engine, program, tag):
    """CLI present, flags still listed, login stored; True when a dry call can go ahead."""
    name, binary = adapter.name, adapter.binary
    if not ready:
        for part in ("cli", "flags", "login"):
            add(f"{name} {part}", SKIP, f"the {backend} sandbox is not ready")
        return False
    if backend == "none":
        found = probe.which(binary)
        if not add(f"{name} cli", OK if found else FAIL, found or f"{binary} is not installed",
                   "" if found else adapter.install_help):
            add(f"{name} flags", SKIP, f"{binary} is not installed")
            add(f"{name} login", SKIP, f"{binary} is not installed")
            return False
        code, output = probe.run([found, *adapter.help_command], timeout=60)
    else:
        code, output = in_image((binary, *adapter.help_command), engine, program, probe)
        if not add(f"{name} cli", FAIL if code in (126, 127) else OK,
                   f"{binary} is missing from the image {tag}" if code in (126, 127) else f"{binary} in {tag}",
                   build_fix(backend) + " (the image installs every supported AI CLI)" if code in (126, 127) else ""):
            add(f"{name} flags", SKIP, f"{binary} is missing from the image")
            add(f"{name} login", SKIP, f"{binary} is missing from the image")
            return False
    module = f"builder/brains/{name.replace('-', '_')}.py"
    missing = sorted(used_flags(adapter) - listed_flags(output))
    command = " ".join((binary, *adapter.help_command))
    flags_ok = add(f"{name} flags", FAIL if missing else OK,
                   f"`{command}` no longer lists: {', '.join(missing)}" if missing
                   else f"`{command}` lists every flag Vesper uses",
                   (f"Update {binary} ({adapter.install_help}"
                    + (f", or rebuild the image: {build_fix(backend)}" if backend != "none" else "")
                    + f"); if it is already current, its flags changed: update Vesper Relay (git pull), or the "
                    f"adapter in {module}") if missing else "")
    if backend == "none":
        add(f"{name} login", SKIP, f"no sandbox: {binary} uses its own login on this machine")
        return flags_ok
    login = adapter.capabilities.sandbox_login
    where = (f"{login[1]} in the Keychain or secrets file" if login[0] == "env" else login[1])
    login_ok = add(f"{name} login", OK if probe.login_ready(login) else FAIL,
                   f"sandbox login found ({where})" if probe.login_ready(login) else f"No sandbox login: {where}",
                   "" if probe.login_ready(login) else adapter.login_help[:1].upper() + adapter.login_help[1:])
    return flags_ok and login_ok


def in_image(argv, engine, program, probe, marker=False):
    """Run ``argv`` in the sandbox image (no network, the usual hardening) with a temporary
    folder from Vesper's state directory as /work, as runs are mounted."""
    from .sandbox import Job
    place = probe.state()
    try:
        place.mkdir(parents=True, mode=0o700, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="doctor-", dir=place) as work:
            if marker:
                (Path(work) / MARKER).write_text("ok\n", encoding="utf-8")
            job = Job("check", tuple(argv), Path(work), True, network="none")
            argv = engine.run_argv(job, "vesper-doctor-" + uuid4().hex[:12], "none")
            return probe.run([program, *argv[1:]], timeout=120)
    except (OSError, BuilderError) as exc:
        return 1, str(exc)


def tail(text, limit=300):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else "..." + text[-limit:]


def render(report):
    """The report as text: one line per check, and a fix line under every failure or warning."""
    marks = {OK: "ok  ", WARN: "warn", FAIL: "FAIL", SKIP: "skip"}
    width = max((len(item["check"]) for item in report["checks"]), default=0)
    lines = ["vesper doctor"]
    for item in report["checks"]:
        lines.append(f"  {marks[item['status']]}  {item['check']:<{width}}  {item['detail']}")
        if item["fix"] and item["status"] in (FAIL, WARN):
            lines.append(f"        {'':<{width}}  fix: {item['fix']}")
    failures = sum(item["status"] == FAIL for item in report["checks"])
    lines.append("All checks passed." if not failures else
                 f"{failures} check{'s' if failures != 1 else ''} failed: run each fix above, then vesper doctor again.")
    return "\n".join(lines)
