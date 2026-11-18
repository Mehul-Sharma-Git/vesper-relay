"""The secrets store for sandbox logins: macOS Keychain first, then a private secrets file.

Config files never hold secrets. A brain whose ``sandbox_login`` is an environment variable
gets its value from here, and the value reaches only the container engine's own process
environment (the container sees it by name, ``-e NAME``), never a command line.

- Keychain: ``security add-generic-password -s vesper-relay -a NAME -w``
- File: ``~/.config/vesper/secrets.env``, ``NAME=value`` lines, readable only by you (mode 600)

``store`` (used by ``vesper setup``) writes either one. The Keychain gets the value through
``security -i`` on standard input, so it never appears on a command line.
"""
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

from ..contracts import require

# What the Keychain route accepts: login tokens and API keys, with nothing ``security -i``
# would split or unquote. Anything else goes to the secrets file.
KEYCHAIN_VALUE = re.compile(r"[A-Za-z0-9._~+/=:-]{1,4096}")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

SERVICE = "vesper-relay"


def default_file(environ=os.environ):
    home = Path(environ["HOME"]) if environ.get("HOME") else Path.home()
    return home / ".config" / "vesper" / "secrets.env"


def keychain_program(environ=os.environ):
    """The macOS ``security`` command on this PATH, or None (not a Mac, or not found)."""
    if sys.platform != "darwin":
        return None
    return shutil.which("security", path=environ.get("PATH", os.defpath))


def keychain(name, environ=os.environ):
    """The value stored in the macOS Keychain under service vesper-relay, or None."""
    security = keychain_program(environ)
    if not security:
        return None
    result = subprocess.run([security, "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
                            capture_output=True, text=True, timeout=30)
    value = result.stdout.rstrip("\n")
    return value if result.returncode == 0 and value else None


def from_file(name, path):
    path = Path(path)
    if not path.exists():
        return None
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), f"Secrets file must be a regular file: {path}")
    require(stat.S_IMODE(info.st_mode) & 0o077 == 0 and info.st_uid == os.getuid(),
            f"Secrets file {path} must be yours and readable only by you (chmod 600, mode 600)")
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.lstrip().startswith("#") and key.strip() == name:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            return value or None
    return None


def read(name, path=None, environ=os.environ):
    """A login value by name: Keychain, then the secrets file; None when neither has it."""
    return keychain(name, environ) or from_file(name, path or default_file(environ))


def store(name, value, where, environ=os.environ):
    """Save a login value in the Keychain (``where="keychain"``) or the private secrets file."""
    require(NAME.fullmatch(name or ""), f"Invalid login name {name!r}")
    require(isinstance(value, str) and value and "\n" not in value and "\r" not in value
            and value == value.strip(), f"{name} must be one line without surrounding spaces")
    if where == "keychain":
        security = keychain_program(environ)
        require(security, "The macOS Keychain is not available here; store it in the secrets file")
        require(KEYCHAIN_VALUE.fullmatch(value), f"{name} has characters the Keychain route does not accept; "
                                                 "store it in the secrets file")
        command = f"add-generic-password -U -s {SERVICE} -a {name} -w {value}\n"
        subprocess.run([security, "-i"], input=command, capture_output=True, text=True, timeout=30,
                       env={key: environ[key] for key in ("PATH", "HOME", "USER", "LOGNAME") if key in environ})
        require(keychain(name, environ) == value, f"The Keychain did not store {name}")
        return "keychain"
    require(where == "file", f"Unknown secrets store {where!r}")
    path = default_file(environ)
    from_file(name, path)  # an existing file must already be private and yours
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [line for line in lines if line.partition("=")[0].strip() != name]
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".secrets-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:  # mkstemp creates it with mode 600
            output.write("".join(line + "\n" for line in [*kept, f"{name}={value}"]))
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    require(from_file(name, path) == value, f"The secrets file did not store {name}")
    return "file"
