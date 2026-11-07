"""Local feedback from verified runs. Only shipped, typed rules become guidance."""
from collections import Counter
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path

from .contracts import read_json, require
from .playbook import RULES, matching_guidance
from .runner import atomic_json


def state_home():
    default = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "vesper-relay"
    return Path(os.environ.get("VESPER_STATE_DIR", default)).expanduser().resolve()


def memory():
    path = state_home() / "learning.json"
    data = read_json(path) if path.is_file() else {"runs": {}, "active": []}
    require(isinstance(data, dict) and isinstance(data.get("runs"), dict)
            and isinstance(data.get("active"), list)
            and all(isinstance(values, list) and all(isinstance(rule, str) and rule in RULES for rule in values)
                    for values in [data["active"], *data["runs"].values()]),
            "Learning history is invalid. Repair or move aside learning.json.")
    return data


def summary(data):
    signals = Counter(rule for rules in data["runs"].values() for rule in rules)
    result = {"signals": dict(signals),
              "proposals": [rule for rule in RULES if signals[rule] >= 2 and rule not in data["active"]],
              "active": list(data["active"])}
    if data.get("repairs"):
        result["repairs"] = list(data["repairs"].values())
    return result


def guidance(mode):
    return matching_guidance(memory()["active"], mode)


@contextmanager
def memory_lock():
    home = state_home()
    home.mkdir(parents=True, mode=0o700, exist_ok=True)
    with (home / "learning.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield home / "learning.json", memory()


def record(runner):
    status = runner.status()
    require(status["status"] == "complete", "Learning requires a fully verified run")
    state = runner.state()
    found = set()
    accepted = set(status["completed"])
    for attempt in status["attempts"]:
        if attempt["job"] not in accepted or attempt["outcome"] != "rejected":
            continue
        if any(result["exit_code"] != 0 for result in attempt["checks"]):
            found.add("reproduce-first")
        if attempt.get("reason", "").startswith("Changes outside job scope:"):
            found.add("confirm-file-scope")
    with memory_lock() as (path, data):
        data["runs"][state["approval_id"]] = sorted(found)
        atomic_json(path, data)
        return summary(data)


def promote(rule):
    with memory_lock() as (path, data):
        require(rule in summary(data)["proposals"],
                "Promote a proposed rule supported by two independent verified runs")
        data["active"].append(rule)
        atomic_json(path, data)
        return summary(data)


def record_repair(approval_id, result):
    with memory_lock() as (path, data):
        data.setdefault("repairs", {})[approval_id] = {
            key: result[key] for key in ("base", "branch", "commit", "digest")
        }
        atomic_json(path, data)
