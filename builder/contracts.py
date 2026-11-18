"""Local product contracts and content-addressed file inventories."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import stat

from .maintenance import MAINTENANCE_GATE


class BuilderError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise BuilderError(message)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise BuilderError(f"Cannot read {path}: {exc}") from exc


def reviewed_text(root, name, records):
    data = (root / name).read_bytes()
    require(sha256(data).hexdigest() == records[name][0], f"Reviewed file changed: {name}")
    return data.decode("utf-8")


def reviewed_contract(root, plan, checks):
    name = "contract.json"
    require(name in plan, "Missing plan artifact: contract.json")
    try:
        data = json.loads(reviewed_text(root, name, plan))
    except ValueError as exc:
        raise BuilderError(f"Invalid contract JSON: {exc}") from exc
    return validate(data, checks)


def fingerprint(data):
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode()).hexdigest()


def tree_paths(root, ignore):
    """Every path under root, parents first, except top-level entries named in ignore."""
    for top in sorted(root.iterdir()):
        if top.name in ignore:
            continue
        yield top
        if top.is_dir() and not top.is_symlink():
            yield from sorted(top.rglob("*"))


def inventory(root, ignore=()):
    """Content and mode of every file and directory. Top-level entries named in ignore
    (build output such as node_modules) are skipped unread, links and all; everything
    else must be a plain file or directory with a safe name."""
    require(root.is_dir() and not root.is_symlink(), f"Invalid tree: {root}")
    records = {}
    for path in tree_paths(root, frozenset(ignore)):
        relative = path.relative_to(root).as_posix()
        safe_path(relative)
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            records[relative] = [None, stat.S_IMODE(info.st_mode)]
            continue
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                f"Linked or special path is unsupported: {relative}")
        with path.open("rb") as file:
            records[relative] = [sha256_stream(file), stat.S_IMODE(info.st_mode)]
    return records


def sha256_stream(file):
    digest = sha256()
    for block in iter(lambda: file.read(1 << 20), b""):
        digest.update(block)
    return digest.hexdigest()


def safe_path(value):
    require(isinstance(value, str) and value and "\\" not in value,
            f"Invalid relative path: {value!r}")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.parts and path.as_posix() == value
            and all(part not in {"..", ".git", ".builder", "__pycache__", "node_modules"}
                    and not any(ord(character) < 32 for character in part)
                    for part in path.parts), f"Invalid relative path: {value!r}")
    return value


def owned(path, boundaries):
    return any(path == item or path.startswith(item + "/") for item in boundaries)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def id_list(value, label, *, empty=False):
    require(isinstance(value, list) and (value or empty)
            and all(isinstance(item, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", item)
                    for item in value) and len(value) == len(set(value)), f"Invalid {label}")
    return value


def records(data, label):
    value = data.get(label)
    require(isinstance(value, list) and value and all(isinstance(item, dict) for item in value),
            f"Expected nonempty {label}")
    id_list([item.get("id") for item in value], f"{label} IDs")
    return {item["id"]: item for item in value}


# Every gate gets these from the runner (runner.gate_environment); gate_env may not replace them.
GATE_FIXED_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "PYTHONDONTWRITEBYTECODE",
                  "XDG_CACHE_HOME", "GOCACHE", "GOPATH",
                  # Set when the contract has build setup: the run's shared dependency caches.
                  "GOMODCACHE", "PNPM_STORE_DIR", "npm_config_store_dir")
PROGRAM_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._+-]{0,127}")
SECRET_NAME = re.compile(r"(?i)(key|token|secret|password|credential|auth)")


def validate_gate_env(value):
    """Names (never values) of host variables copied into every gate; secrets are refused."""
    from .providers import PROVIDER_CREDENTIALS
    require(isinstance(value, list)
            and all(isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name)
                    for name in value) and len(value) == len(set(value)),
            "Invalid gate_env: use a list of distinct environment variable names")
    credentials = {name for names in PROVIDER_CREDENTIALS.values() for name in names}
    for name in value:
        require(not SECRET_NAME.search(name) and name not in credentials,
                f"gate_env must not pass credentials: {name}")
        require(name not in GATE_FIXED_ENV, f"gate_env cannot replace {name}")
    return value


def validate_command(command, label):
    """An argv whose program is found by name on PATH, never by path."""
    require(isinstance(command, list) and command and len(command) <= 256
            and all(isinstance(arg, str) and len(arg) <= 4096 and "\0" not in arg for arg in command),
            f"Invalid command for {label}: use a list of argument strings")
    require(PROGRAM_NAME.fullmatch(command[0]),
            f"{label[0].upper() + label[1:]} command must start with a bare program name, not a path: {command[0]!r}")


IGNORE_NAME = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9._-]{0,127}")


def validate_build(value, jobs):
    """Top-level build output to ignore, and the commands that install toolchain dependencies."""
    require(isinstance(value, dict) and set(value) <= {"ignore", "setup", "timeout"},
            'Invalid build: use {"ignore": [names], "setup": [[program, args...]], "timeout": seconds}')
    ignore = value.get("ignore", [])
    require(isinstance(ignore, list) and len(ignore) <= 32 and len(ignore) == len(set(ignore))
            and all(isinstance(name, str) and IGNORE_NAME.fullmatch(name)
                    and name not in {".", "..", ".git", ".builder"} for name in ignore),
            "Invalid build ignore: use distinct top-level directory names such as node_modules or dist")
    setup = value.get("setup", [])
    require(isinstance(setup, list) and len(setup) <= 16,
            "Invalid build setup: use a list of commands, each a list of argument strings")
    for command in setup:
        validate_command(command, "build setup")
    if "timeout" in value:
        require(type(value["timeout"]) is int and 1 <= value["timeout"] <= 1800,
                "Invalid build timeout: use whole seconds, 1 to 1800")
    for job in jobs.values():
        inside = [path for path in job["paths"] if owned(path, ignore)]
        require(not inside, f"Job {job['id']} writes inside ignored build directory: {', '.join(inside)}")
    return value


def validate_check(item, checks_inventory):
    """A gate is a Python script in checks/ or an argv whose program is found by name, never by path."""
    name = item["id"]
    require(("script" in item) != ("command" in item), f"Check {name} needs exactly one of script or command")
    if "script" in item:
        require("overlay" not in item, f"Check {name}: an overlay needs a command gate")
        script = safe_path(item["script"])
        require(script.endswith(".py") and script in checks_inventory, f"Check script missing: {script}")
    else:
        validate_command(item["command"], f"check {name}")
        if "overlay" in item:
            overlay = item["overlay"]
            require(isinstance(overlay, dict) and set(overlay) == {"from", "to"},
                    f"Invalid overlay for check {name}: use {{\"from\": \"<dir in checks/>\", \"to\": \"<dir>\"}}")
            source = safe_path(overlay["from"])
            require(checks_inventory.get(source, [""])[0] is None
                    and any(path.startswith(source + "/") and value[0] is not None
                            for path, value in checks_inventory.items()),
                    f"Overlay directory missing or empty in checks/: {source}")
            if overlay["to"] != ".":
                safe_path(overlay["to"])
    if "timeout" in item:
        require(type(item["timeout"]) is int and 1 <= item["timeout"] <= 1800,
                f"Invalid timeout for check {name}: use whole seconds, 1 to 1800")


def validate(data, checks_inventory):
    require(isinstance(data, dict) and nonempty(data.get("title")) and nonempty(data.get("delivery")),
            "Contract needs a title and delivery target")
    if "gate_env" in data:
        validate_gate_env(data["gate_env"])
    requirements = records(data, "requirements")
    checks = records(data, "checks")
    jobs = records(data, "jobs")
    for item in checks.values():
        validate_check(item, checks_inventory)
    gate_ids = set(checks)
    for item in requirements.values():
        require(nonempty(item.get("description")), f"Missing description for {item['id']}")
        require(set(id_list(item.get("checks"), "requirement checks")) <= gate_ids,
                f"Unknown check for {item['id']}")
    used_checks = set()
    for job in jobs.values():
        require(nonempty(job.get("role")) and nonempty(job.get("goal")),
                f"Missing role or goal for {job['id']}")
        paths = job.get("paths")
        require(isinstance(paths, list) and paths, f"Missing writable paths for {job['id']}")
        for path in paths:
            safe_path(path)
        require(set(id_list(job.get("depends_on"), "dependencies", empty=True)) <= jobs.keys(),
                f"Unknown dependency for {job['id']}")
        assigned = set(id_list(job.get("checks"), "job checks"))
        require(assigned <= gate_ids, f"Unknown job check for {job['id']}")
        used_checks.update(assigned)
        for key, default, low, high in (("max_attempts", 2, 1, 5), ("timeout", 180, 1, 1800)):
            value = job.get(key, default)
            require(type(value) is int and low <= value <= high, f"Invalid {key} for {job['id']}")
    require(used_checks == gate_ids, "Every approved check must be assigned to a job")
    if "build" in data:
        validate_build(data["build"], jobs)
    pending = set(jobs)
    while pending:
        ready = {key for key in pending if not (set(jobs[key]["depends_on"]) & pending)}
        require(ready, "Job dependencies contain a cycle")
        pending -= ready
    return data


def review_bundle(root, *, include_critique=True):
    plans = inventory(root / "plan")
    checks = inventory(root / "checks")
    seed = inventory(root / "seed")
    for name in ("product.md", "design.md", "architecture.md", "decisions.md"):
        require(name in plans and reviewed_text(root / "plan", name, plans).strip(),
                f"Missing plan artifact: {name}")
    contract = reviewed_contract(root / "plan", plans, checks)
    ignored = [name for name in contract.get("build", {}).get("ignore", []) if name in seed]
    require(not ignored, "Seed contains ignored build directory: " + ", ".join(ignored)
            + ". Ignored directories are never promoted, so the result would drop those files.")
    bundle = {"plan": plans, "checks": checks, "seed": seed}
    if "team" in contract:
        from .team import freeze_team
        bundle["team"] = freeze_team(contract)
    if (root / ".vesper.json").is_file():
        managed = read_json(root / ".vesper.json")
        require(isinstance(managed, dict) and isinstance(managed.get("intake"), dict),
                "Invalid managed intake metadata")
        require("intake.json" in plans, "Missing managed plan intake")
        intake = json.loads(reviewed_text(root / "plan", "intake.json", plans))
        require(intake == managed["intake"], "Managed intake metadata changed")
        require(not intake.get("team_contract") or "team" in bundle,
                "This run requires a team contract and independent candidate review")
        if intake["repository"]:
            require(managed.get("seed_digest") == fingerprint(seed), "Managed baseline changed after intake")
            require("repository.json" in plans and
                    json.loads(reviewed_text(root / "plan", "repository.json", plans)) == intake["repository"],
                    "Managed repository metadata changed")
        if intake["mode"] == "maintenance":
            validate_maintenance(root, contract, checks, seed)
        bundle["intake"] = intake
    if "team" in bundle:
        from .team import validate_design
        design_required = contract.get("design_required", False)
        require(type(design_required) is bool, "design_required must be a boolean")
        mode = bundle.get("intake", {}).get("mode")
        if design_required or mode in ("build", "design") and any(
                job["role"] == "frontend" for job in contract["jobs"]):
            require("design.json" in plans, "Visual work needs plan/design.json with distinct design directions")
            validate_design(json.loads(reviewed_text(root / "plan", "design.json", plans)))
            bundle["design_review"] = True
    if "repair.json" in plans:
        from .repair import validate_repair
        require(not contract.get("build", {}).get("setup"), "Vesper repairs cannot run build setup")
        require(bundle.get("intake", {}).get("mode") == "maintenance", "Repair needs a managed Vesper baseline")
        packet = json.loads(reviewed_text(root / "plan", "repair.json", plans))
        validate_repair(contract, packet)
        bundle["repair"] = packet
    if "intake" in bundle:
        from .planning import validate_planning, attach_critique
        version = bundle["intake"].get("planning_version", 1)
        require(type(version) is int and version == 1, "Unsupported managed planning version")
        bundle["planning"] = validate_planning(root, contract, bundle)
        if include_critique and bundle["planning"]["depth"] != "skip":
            attach_critique(root, bundle)
    return contract, bundle


def validate_maintenance(root, contract, checks, seed):
    require(any(item["id"] == "VESPER_REGRESSION" and item.get("script") == "vesper_regression.py"
                for item in contract["checks"]), "Maintenance requires the VESPER_REGRESSION check")
    require(reviewed_text(root / "checks", "vesper_regression.py", checks) == MAINTENANCE_GATE,
            "Maintenance regression script changed")
    baseline = {path.removeprefix("tests/"): value for path, value in seed.items()
                if path.startswith("tests/")}
    frozen = {path.removeprefix("baseline_tests/"): value for path, value in checks.items()
              if path.startswith("baseline_tests/")}
    require(baseline and baseline == frozen, "Maintenance baseline tests changed")
