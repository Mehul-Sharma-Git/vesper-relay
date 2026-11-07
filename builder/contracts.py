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


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), f"Invalid tree: {root}")
    records = {}
    for path in sorted(root.rglob("*")):
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


def validate(data, checks_inventory):
    require(isinstance(data, dict) and nonempty(data.get("title")) and nonempty(data.get("delivery")),
            "Contract needs a title and delivery target")
    requirements = records(data, "requirements")
    checks = records(data, "checks")
    jobs = records(data, "jobs")
    for item in checks.values():
        script = safe_path(item.get("script"))
        require(script.endswith(".py") and script in checks_inventory, f"Check script missing: {script}")
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
    pending = set(jobs)
    while pending:
        ready = {key for key in pending if not (set(jobs[key]["depends_on"]) & pending)}
        require(ready, "Job dependencies contain a cycle")
        pending -= ready
    return data


def review_bundle(root):
    plans = inventory(root / "plan")
    checks = inventory(root / "checks")
    seed = inventory(root / "seed")
    for name in ("product.md", "design.md", "architecture.md", "decisions.md"):
        require(name in plans and reviewed_text(root / "plan", name, plans).strip(),
                f"Missing plan artifact: {name}")
    contract = reviewed_contract(root / "plan", plans, checks)
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
        require(bundle.get("intake", {}).get("mode") == "maintenance", "Repair needs a managed Vesper baseline")
        packet = json.loads(reviewed_text(root / "plan", "repair.json", plans))
        validate_repair(contract, packet)
        bundle["repair"] = packet
    return contract, bundle


def validate_maintenance(root, contract, checks, seed):
    require(any(item["id"] == "VESPER_REGRESSION" and item["script"] == "vesper_regression.py"
                for item in contract["checks"]), "Maintenance requires the VESPER_REGRESSION check")
    require(reviewed_text(root / "checks", "vesper_regression.py", checks) == MAINTENANCE_GATE,
            "Maintenance regression script changed")
    baseline = {path.removeprefix("tests/"): value for path, value in seed.items()
                if path.startswith("tests/")}
    frozen = {path.removeprefix("baseline_tests/"): value for path, value in checks.items()
              if path.startswith("baseline_tests/")}
    require(baseline and baseline == frozen, "Maintenance baseline tests changed")
