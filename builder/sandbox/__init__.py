"""Pluggable sandbox: run workers, reviewers, consultants and gates in a locked container.

Backends: ``docker`` (the default), ``podman``, and ``none`` (no sandbox: the host, as
``--trust-host``; an explicit opt-in that warns on every run). The runner hands a backend a
``Job`` and never calls a container engine itself. An external ``--launcher`` stays
available for custom setups.

Every job runs in the image built from ``sandbox/Dockerfile`` as a non-root user, with a
read-only root filesystem, no capabilities, ``no-new-privileges``, memory and PID limits,
and private ``/tmp`` and home. Only the job's own directories are mounted; never the host
home, SSH keys or the engine's socket, and never the host environment.

| Operation | Mounts | Network |
| --- | --- | --- |
| ``worker`` | work copy read-write at /work | the brain's provider hosts only (egress proxy) |
| ``reviewer``, ``consult`` | review or baseline copy read-only at /work; /out for the reply | provider hosts only |
| ``setup`` | work copy and dependency cache read-write | open |
| ``check`` | gate dir (checks/ and candidate/) read-only | none (loopback works) |
| ``check-command`` | throwaway work copy read-write, dependency cache read-only | none |
"""
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple
from uuid import uuid4

from ..contracts import require
from . import secrets

BACKENDS = ("docker", "podman", "none")
SANDBOX_DIR = Path(__file__).resolve().parents[2] / "sandbox"
IMAGE = "vesper-sandbox"
HOME = "/home/vesper"
MEMORY = "4g"
PIDS = "1024"
PROXY_PORT = 8888
NETWORKS = {"worker": "egress", "reviewer": "egress", "consult": "egress",
            "setup": "open", "check": "none", "check-command": "none"}
# What the engine's own command-line process may see (it is not the container's environment).
ENGINE_ENV = ("PATH", "HOME", "LANG", "TMPDIR", "USER", "LOGNAME", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME",
              "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY",
              "CONTAINER_HOST", "CONTAINERS_CONF")
LOGIN_DIR = "/run/vesper-login"
# Copies a read-only login file into the private home, so the CLI can write next to it.
LOGIN_COPY = 'mkdir -p "$(dirname "$HOME/$1")" && cp "$2" "$HOME/$1" && shift 2 && exec "$@"'
HOST_NAME = re.compile(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")


class Job(NamedTuple):
    operation: str          # a key of NETWORKS
    argv: tuple             # run inside the sandbox; the program is a bare name on the image's PATH
    work: Path              # host directory mounted at /work
    work_readonly: bool = False
    mounts: tuple = ()      # (host path, container path, read-only) beyond /work
    env: tuple = ()         # (name, value) pairs set inside; never secrets
    secrets: tuple = ()     # login variable names, values from the secrets store
    hosts: tuple = ()       # the only hosts an egress job may reach, through the proxy
    network: str = "none"   # none, egress or open
    login_help: str = ""    # how to create a missing login


def image_tag():
    """The image name for this checkout: changes whenever the image definition changes."""
    digest = sha256((SANDBOX_DIR / "Dockerfile").read_bytes()).hexdigest()[:12]
    return f"{IMAGE}:{digest}"


def agent_job(operation, argv, work, *, out=None, login=None, hosts=(), env=(), login_help=""):
    """A brain process: the worker edits /work; reviewers and consultants read it and reply in /out."""
    require(operation in ("worker", "reviewer", "consult"), f"Not a brain operation: {operation}")
    mounts, names = [], ()
    if out is not None:
        mounts.append((Path(out), "/out", False))
    if login:
        kind, value = login
        if kind == "env":
            names = (value,)
        else:
            require(value.startswith("~/"), f"A login file must live under the home directory: {value}")
            source = f"{LOGIN_DIR}/{Path(value).name}"
            mounts.append((Path(value).expanduser(), source, True))
            # The host file is never written; a token the CLI refreshes stays in the sandbox.
            argv = ("sh", "-c", LOGIN_COPY, "vesper-login", value[2:], source, *argv)
    return Job(operation, tuple(argv), Path(work), operation != "worker", tuple(mounts), tuple(env), names,
               tuple(hosts), NETWORKS[operation], login_help)


def gate_environment(gate_env=(), dependencies=False, extra=None, environ=os.environ):
    """The gate's variables inside the sandbox: caches in /tmp, the shared cache at /cache,
    and the contract's declared gate_env names with their host values."""
    env = {"PYTHONDONTWRITEBYTECODE": "1", "XDG_CACHE_HOME": "/tmp/cache", "GOCACHE": "/tmp/cache/go-build",
           "GOPATH": "/tmp/go"}
    if dependencies:
        env.update(GOMODCACHE="/cache/go-mod", PNPM_STORE_DIR="/cache/pnpm-store",
                   pnpm_config_store_dir="/cache/pnpm-store", npm_config_store_dir="/cache/pnpm-store")
    env.update({name: environ[name] for name in gate_env if name in environ})
    env.update(extra or {})
    return tuple(sorted(env.items()))


def check_job(home, script, gate_env=()):
    """A Python gate: home holds checks/ and candidate/, both read-only."""
    return Job("check", ("python3", "-I", "-B", f"/work/checks/{script}", "/work/candidate"), Path(home), True,
               env=gate_environment(gate_env), network=NETWORKS["check"])


def command_job(operation, argv, work, *, dependencies=None, gate_env=(), extra=None):
    """Build setup (network open, cache writable) or a command gate (no network, cache read-only)."""
    require(operation in ("setup", "check-command"), f"Not a command operation: {operation}")
    mounts = ((Path(dependencies), "/cache", operation != "setup"),) if dependencies else ()
    return Job(operation, tuple(argv), Path(work), False, mounts,
               gate_environment(gate_env, bool(dependencies), extra), network=NETWORKS[operation])


class Sandbox:
    """A backend. ``run`` returns the job's exit status like ``process.run_process``."""
    name = ""

    def check(self):
        """Fail early, before any work, when the backend can't run here. Returns self."""
        raise NotImplementedError

    def preflight(self, job):
        """Fail before any work when the job could not start (a missing login, for example)."""

    def run(self, job, *, input_text, log, timeout, on_start=None):
        raise NotImplementedError


class Container(Sandbox):
    """An OCI engine with a Docker-compatible command line."""
    program = ""
    open_network = "bridge"

    def __init__(self, image=None):
        self.image = image

    def tag(self):
        return self.image or image_tag()

    def hardening(self):
        uid, gid = (os.getuid(), os.getgid()) if os.getuid() != 0 else (10001, 10001)
        return ["--init", "--user", f"{uid}:{gid}", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--memory", MEMORY, "--pids-limit", PIDS,
                "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=2g,mode=1777",
                "--tmpfs", f"{HOME}:rw,exec,nosuid,nodev,size=1g,mode=1777", "--label", "vesper-relay=sandbox"]

    @staticmethod
    def mount(source, target, readonly):
        text = str(source)
        require(Path(source).is_absolute() and "," not in text and "\n" not in text,
                f"Sandbox mounts need an absolute path without a comma: {text}")
        return ["--mount", f"type=bind,source={text},target={target}" + (",readonly" if readonly else "")]

    def run_argv(self, job, name, network, proxy=None):
        """The engine command for one job (pure: no engine is called)."""
        argv = [self.program, "run", "--rm", "-i", "--name", name, *self.hardening(), "--network", network]
        for source, target, readonly in ((job.work, "/work", job.work_readonly), *job.mounts):
            argv += self.mount(source, target, readonly)
        argv += ["--workdir", "/work", "-e", f"HOME={HOME}"]
        for key, value in job.env:
            require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) and "\n" not in str(value),
                    f"Invalid sandbox variable {key}")
            argv += ["-e", f"{key}={value}"]
        if proxy:
            address = f"http://{proxy}:{PROXY_PORT}"
            for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
                argv += ["-e", f"{key}={address}"]
            argv += ["-e", "NO_PROXY=localhost,127.0.0.1", "-e", "no_proxy=localhost,127.0.0.1"]
        for key in job.secrets:
            argv += ["-e", key]  # the value comes from the engine process's environment
        return argv + [self.tag(), *job.argv]

    def cli_environment(self, job, environ=os.environ, store=None):
        """The engine process's environment: its own settings plus the job's login values."""
        env = {key: environ[key] for key in ENGINE_ENV if key in environ}
        for key in job.secrets:
            value = secrets.read(key, store)
            require(value, f"No sandbox login {key}: {job.login_help}")
            env[key] = value
        for source, target, _ in job.mounts:
            if target.startswith(LOGIN_DIR + "/"):
                require(source.is_file(), f"No sandbox login file {source}: {job.login_help}")
        return env

    def preflight(self, job):
        self.cli_environment(job)

    @staticmethod
    def proxy_files(hosts):
        """tinyproxy settings: HTTPS tunnels (CONNECT to port 443) to the listed hosts only."""
        require(hosts and all(HOST_NAME.fullmatch(host) for host in hosts), "Brain hosts must be plain host names")
        config = "\n".join((f"Port {PROXY_PORT}", "Listen 0.0.0.0", "Timeout 900", "MaxClients 64",
                            "Allow 0.0.0.0/0", "ConnectPort 443", "FilterType ere", "FilterURLs Off",
                            "FilterDefaultDeny Yes", 'Filter "/etc/vesper-proxy/filter"', "LogLevel Notice",
                            "DisableViaHeader Yes", ""))
        # Host names hold only letters, digits, "-" and "."; escape the dots (POSIX ERE has no "\\-").
        filters = "".join("^" + host.replace(".", "\\.") + "$\n" for host in hosts)
        return config, filters

    def engine(self, env, *args, check=False):
        result = subprocess.run([self.program, *args], env=env, capture_output=True, text=True, timeout=120)
        require(not check or result.returncode == 0,
                f"{self.program} {args[0]} failed: {(result.stderr or result.stdout).strip()[:400]}")
        return result

    def check(self):
        program = shutil.which(self.program, path=os.environ.get("PATH", os.defpath))
        require(program, f"{self.program} not found on PATH: install it, start it, or choose another sandbox "
                         "(--sandbox docker|podman|none)")
        self.program = program
        result = subprocess.run([program, "image", "inspect", self.tag()], capture_output=True, text=True,
                                env={key: os.environ[key] for key in ENGINE_ENV if key in os.environ}, timeout=120)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            require("no such" not in detail.lower() and "not found" not in detail.lower()
                    and "unknown" not in detail.lower(),
                    f"Sandbox image {self.tag()} is not built for {self.name}: run "
                    f"`vesper sandbox build --backend {self.name}`")
            require(False, f"{self.name} could not be reached (is it running?): {detail[:400]}")
        return self

    def start_proxy(self, job, name, env, cleanup):
        network, proxy = f"{name}-net", f"{name}-proxy"
        self.engine(env, "network", "create", "--internal", network, check=True)
        cleanup.append(("network", "rm", network))
        settings = Path(tempfile.mkdtemp(prefix="vesper-proxy-", dir=job.work.parent))
        cleanup.append(("dir", settings))
        config, filters = self.proxy_files(job.hosts)
        (settings / "tinyproxy.conf").write_text(config, encoding="utf-8")
        (settings / "filter").write_text(filters, encoding="utf-8")
        for path in (settings, settings / "tinyproxy.conf", settings / "filter"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        self.engine(env, "run", "-d", "--rm", "--name", proxy, *self.hardening(), "--network", self.open_network,
                    *self.mount(settings, "/etc/vesper-proxy", True), self.tag(),
                    "tinyproxy", "-d", "-c", "/etc/vesper-proxy/tinyproxy.conf", check=True)
        cleanup.append(("rm", "-f", proxy))
        self.engine(env, "network", "connect", network, proxy, check=True)
        return network, proxy

    def run(self, job, *, input_text, log, timeout, on_start=None):
        from ..process import run_process
        env = self.cli_environment(job)
        name = "vesper-" + uuid4().hex[:16]
        cleanup = []
        try:
            proxy = None
            if job.network == "egress":
                network, proxy = self.start_proxy(job, name, env, cleanup)
            else:
                network = {"none": "none", "open": self.open_network}[job.network]
            return run_process(self.run_argv(job, name, network, proxy), cwd=job.work, input_text=input_text,
                               env=env, log=log, timeout=timeout, on_start=on_start or (lambda _: None))
        finally:
            # Killing the engine's client does not stop its container: remove it by name.
            self.engine(env, "rm", "-f", name)
            for item in reversed(cleanup):
                if item[0] == "dir":
                    shutil.rmtree(item[1], ignore_errors=True)
                else:
                    self.engine(env, *item)

    def build(self, platform=None):
        """Build the image for this machine (or ``platform``); returns the engine's exit status."""
        self.program = shutil.which(self.program) or self.program
        args = [self.program, "build", "-t", self.tag()]
        if platform:
            args += ["--platform", platform]
        return subprocess.run([*args, str(SANDBOX_DIR)]).returncode


class Docker(Container):
    name = "docker"
    program = "docker"


class Podman(Container):
    name = "podman"
    program = "podman"
    open_network = "podman"

    def hardening(self):
        # Rootless Podman maps your user to root inside; keep-id keeps your own uid instead.
        return [*super().hardening(), "--userns=keep-id"]


def warn_no_sandbox():
    print("vesper: WARNING: no sandbox (--sandbox none / --trust-host). Brains and gates run on this "
          "machine as your user, with your network and files. Use it only on a disposable machine.",
          file=sys.stderr)


def backend(name):
    """The backend for a name; ``none`` is no sandbox (returns None after the warning)."""
    require(name in BACKENDS, "sandbox.backend must be one of " + ", ".join(BACKENDS))
    if name == "none":
        warn_no_sandbox()
        return None
    return {"docker": Docker, "podman": Podman}[name]()
