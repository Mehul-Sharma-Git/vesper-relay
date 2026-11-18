"""Personal and project config files (TOML, standard library only).

Personal: ``~/.config/vesper/config.toml`` (or ``--config PATH`` / ``VESPER_CONFIG``)
holds the user's own matters: brains, roles, sandbox, limits, defaults, tools, paths.
Project: ``vesper.toml`` in the target repository (committed) holds the project's
matters: stack, hosting, checks. Each section belongs to exactly one level (``LEVELS``),
so every key resolves as: command flag > its own file > built-in default.

Config files never hold secrets: any key whose name looks like one is refused.
Planning depth is not a config key; it comes from ``plan/planning.json``.
"""
import json
import os
from pathlib import Path
import re
import tomllib

from .contracts import BuilderError, require
from .providers import review_limits

PROJECT_FILE = "vesper.toml"
MAX_BYTES = 256_000

# The explicit table of which section, and so which key, belongs to which level.
LEVELS = {
    "brains": "personal", "roles": "personal", "sandbox": "personal", "limits": "personal",
    "defaults": "personal", "tools": "personal", "paths": "personal",
    "stack": "project", "hosting": "project", "checks": "project",
}

# Built-in defaults; the review limits match the CLI's --review-timeout/--review-max-turns.
DEFAULTS = {
    "limits.reserve_percent": 25,
    "limits.review_max_turns": 20,
    "limits.review_timeout": 180,
    "sandbox.backend": "docker",
}

SANDBOX_BACKENDS = ("docker", "podman", "none")
FLAG = "a command flag"
SECRET_WORDS = ("token", "secret", "password", "credential")
SECRET_STORE = ("Config files hold no secrets: store it in the macOS Keychain or in "
                "~/.config/vesper/secrets.env (readable only by you, mode 600)")


def personal_path(explicit=None, environ=os.environ):
    """Return (path, explicit): --config wins, then VESPER_CONFIG, then the default."""
    if explicit:
        return Path(explicit), True
    if environ.get("VESPER_CONFIG"):
        return Path(environ["VESPER_CONFIG"]).expanduser(), True
    home = Path(environ["HOME"]) if environ.get("HOME") else Path.home()
    return home / ".config" / "vesper" / "config.toml", False


def secret_like(name):
    """True when a key name looks like it holds a secret (key, token, secret, ...)."""
    for part in re.split(r"[^a-z0-9]+", str(name).lower()):
        if any(word in part for word in SECRET_WORDS) or re.search(r"keys?$", part):
            return True
    return False


def refuse_secret(name, where):
    if secret_like(name.rsplit(".", 1)[-1]):
        raise BuilderError(f"Refusing config key '{name}' in {where}: it looks like a secret. "
                           f"{SECRET_STORE}")


def child(prefix, key, where):
    """Name one nested key; a quoted key may not hide a dot (or a secret) inside it."""
    require(key and "." not in key,
            f"Config key {key!r} under {prefix} in {where} may not contain '.' or be empty")
    name = f"{prefix}.{key}"
    refuse_secret(name, where)
    return name


def scan_list(items, name, where):
    for item in items:
        if isinstance(item, dict):
            for key, value in item.items():
                scan_list([value], child(name, key, where), where)
        elif isinstance(item, list):
            scan_list(item, name, where)


def flatten(table, prefix, where, out):
    for key, value in table.items():
        name = child(prefix, key, where)
        if isinstance(value, dict):
            flatten(value, name, where, out)
        else:
            if isinstance(value, list):
                scan_list(value, name, where)
            out[name] = value
    return out


def read_file(path, level, required=False):
    """Read one config file into flat dotted keys; return (values, found)."""
    path = Path(path)
    if not path.exists():
        require(not required, f"Config file not found: {path}")
        return {}, False
    require(path.is_file(), f"Config path is not a file: {path}")
    require(path.stat().st_size <= MAX_BYTES, f"Config file is too large: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise BuilderError(f"Invalid TOML in {path}: {exc}") from None
    values = {}
    for section, table in data.items():
        refuse_secret(section, path)
        require(section in LEVELS, f"Unknown config section [{section}] in {path}; known: "
                + ", ".join(LEVELS))
        require(isinstance(table, dict), f"Config key '{section}' in {path} must be a [section] table")
        if LEVELS[section] != level:
            home = ("the project file vesper.toml" if LEVELS[section] == "project"
                    else "the personal file (~/.config/vesper/config.toml)")
            raise BuilderError(f"[{section}] belongs in {home}, not {path}")
        flatten(table, section, path, values)
    return values, True


def parse_flag(text):
    """Parse a ``KEY=VALUE`` command flag; the value is read as TOML, else as a string."""
    key, sep, raw = str(text).partition("=")
    key = key.strip()
    parts = key.split(".")
    require(sep and len(parts) >= 2 and all(parts), f"Config flag must be SECTION.KEY=VALUE: {text}")
    require("\n" not in raw and "\r" not in raw, f"Config flag value must be one line: {key}")
    require(parts[0] in LEVELS, f"Unknown config section [{parts[0]}] in flag {text}")
    for index in range(1, len(parts) + 1):
        refuse_secret(".".join(parts[:index]), FLAG)
    try:
        value = tomllib.loads(f"v = {raw}")["v"]
    except tomllib.TOMLDecodeError:
        value = raw
    # An inline table or array is scanned exactly like the same value in a file.
    if isinstance(value, dict):
        flatten(value, key, FLAG, {})
    elif isinstance(value, list):
        scan_list(value, key, FLAG)
    return key, value


def validate(values):
    """Check the effective values the core already understands."""
    for key in values:
        for other in values:
            require(not other.startswith(key + "."), f"Config key {key} is both a value and a table")
    backend = values.get("sandbox.backend")
    require(backend in SANDBOX_BACKENDS,
            "sandbox.backend must be one of " + ", ".join(SANDBOX_BACKENDS))
    reserve = values.get("limits.reserve_percent")
    require(type(reserve) is int and 0 <= reserve <= 100,
            "limits.reserve_percent must be a whole number from 0 to 100")
    review_limits(values.get("limits.review_timeout"), values.get("limits.review_max_turns"))
    brains = set()
    for key in values:
        section, *rest = key.split(".")
        if section == "brains":
            require(len(rest) >= 2, f"{key} must be a [brains.NAME] table")
            brains.add(rest[0])
    for brain in sorted(brains):
        use = values.get(f"brains.{brain}.use")
        require(isinstance(use, str) and use.strip(),
                f"brains.{brain}.use must name an adapter (for example \"claude-code\")")
    for key, value in values.items():
        section, *rest = key.split(".")
        if section == "roles":
            require(len(rest) == 1, f"{key} must be ROLE = \"BRAIN\" under [roles]")
            require(isinstance(value, str) and value in brains,
                    f"{key} names brain {value!r}, which is not defined under [brains]")


def load_config(personal, project, flags=(), explicit=False):
    """Resolve every key: flag > its own file > built-in default; return values and sources."""
    files = {}
    effective = {key: {"value": value, "source": "default"} for key, value in DEFAULTS.items()}
    for level, path, required in (("personal", personal, explicit), ("project", project, False)):
        values, found = read_file(path, level, required)
        files[level] = {"path": str(path), "found": found}
        for key, value in values.items():
            effective[key] = {"value": value, "source": level, "file": str(path)}
    for key, value in flags:
        leaves = flatten(value, key, FLAG, {}) if isinstance(value, dict) else {key: value}
        for leaf, leaf_value in leaves.items():
            effective[leaf] = {"value": leaf_value, "source": "flag"}
    validate({key: entry["value"] for key, entry in effective.items()})
    return {"files": files, "values": dict(sorted(effective.items()))}


def show(config=None, repo=None, flags=(), environ=os.environ):
    """`vesper config show`: every effective value and where it came from, as JSON data."""
    personal, explicit = personal_path(config, environ)
    project = Path(repo or Path.cwd()).resolve() / PROJECT_FILE
    result = load_config(personal, project, [parse_flag(flag) for flag in flags], explicit)
    return json.loads(json.dumps(result, default=str))
