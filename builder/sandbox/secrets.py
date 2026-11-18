"""The secrets store for sandbox logins: macOS Keychain first, then a private secrets file.

Config files never hold secrets. A brain whose ``sandbox_login`` is an environment variable
gets its value from here, and the value reaches only the container engine's own process
environment (the container sees it by name, ``-e NAME``), never a command line.

- Keychain: ``security add-generic-password -s vesper-relay -a NAME -w``
- File: ``~/.config/vesper/secrets.env``, ``NAME=value`` lines, readable only by you (mode 600)
"""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from ..contracts import require

SERVICE = "vesper-relay"


def default_file(environ=os.environ):
    home = Path(environ["HOME"]) if environ.get("HOME") else Path.home()
    return home / ".config" / "vesper" / "secrets.env"


def keychain(name):
    """The value stored in the macOS Keychain under service vesper-relay, or None."""
    security = shutil.which("security") if sys.platform == "darwin" else None
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


def read(name, path=None):
    """A login value by name: Keychain, then the secrets file; None when neither has it."""
    return keychain(name) or from_file(name, path or default_file())
