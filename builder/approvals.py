"""Human-only approvals (P2-T2): confirmers, confirmation records and "what changed".

A protected action (approving a plan, applying a patch, committing a repair, attesting that a
report came from an independent reviewer, adding a check after approval, accepting a risk) runs only after
a human confirms it on a plain-language sheet. The confirmer is chosen in the personal config:

    [approvals]
    confirmer = "tty"            # or "macos-dialog"

`tty` shows the sheet and a short random code in a terminal and refuses when standard input is
not a terminal (an AI's tool calls run without one). `macos-dialog` shows a short form of the
sheet in a native dialog, with a "Show full sheet" button. Both make approval a deliberate human
act; neither is authentication against an AI that controls the machine itself.

The only way around a confirmer is the test-only VESPER_TEST_CONFIRMER variable, which names a
stand-in program; `vesper doctor` warns whenever it is set.
"""
from contextlib import contextmanager
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from typing import NamedTuple

from .contracts import BuilderError, read_json, require

TEST_CONFIRMER = "VESPER_TEST_CONFIRMER"
CONFIRMERS = ("tty", "macos-dialog")
LATER = ("mcp-elicitation", "dashboard")
ACTIONS = {
    "approve-plan": "Approving this plan",
    "apply-patch": "Applying this patch",
    "commit-repair": "Committing this repair",
    "attest-independence": "Attesting this review",
    "add-check": "Adding this check",
    "accept-risk": "Accepting this risk",
}
CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DIALOG = """on run argv
    set reply to display dialog (item 1 of argv) with title "Vesper Relay" buttons {"Show full sheet", "Cancel", "Approve"} default button "Cancel" cancel button "Cancel" giving up after 900
    if gave up of reply then return "Cancel"
    return button returned of reply
end run"""


class Sheet(NamedTuple):
    full: str     # every field, shown before any confirmation
    short: str    # a dialog-sized form that always keeps "what changed" and the short digest
    files: list   # [{path, sha256, size, lines}] of what the confirmation locks


# Confirmers ---------------------------------------------------------------------------

def new_code():
    return "".join(secrets.choice(CODE_LETTERS) for _ in range(4))


def refused(action, why=""):
    return BuilderError(f"{ACTIONS[action]} was not confirmed by a human{': ' + why if why else ''}")


def tty_confirm(action, sheet, stdin=None, stderr=None):
    """The full sheet and a short code in a terminal; the human types the code back."""
    stdin, stderr = stdin or sys.stdin, stderr or sys.stderr
    require(stdin.isatty(), f"{ACTIONS[action]} needs a human at a terminal, and standard input is not a terminal. "
                            "Ask the owner to run this command in their own terminal, or set "
                            '[approvals] confirmer = "macos-dialog" in ~/.config/vesper/config.toml')
    code = new_code()
    stderr.write(sheet.full.rstrip() + f"\n\nTo confirm, type {code} and press Return (anything else cancels): ")
    stderr.flush()
    if stdin.readline().strip().upper() != code:
        raise refused(action, "the code did not match")


def osascript(argv):
    done = subprocess.run(argv, capture_output=True, text=True, timeout=1000)
    return done.stdout.strip() if done.returncode == 0 else "Cancel"


def dialog_confirm(action, sheet, run=osascript, platform=None):
    """A native macOS dialog with the short sheet; "Show full sheet" opens the full one."""
    require((platform or sys.platform) == "darwin", "The macos-dialog confirmer needs macOS")
    for _ in range(5):
        answer = run(["osascript", "-e", DIALOG, sheet.short.rstrip()])
        if answer == "Approve":
            return
        if answer != "Show full sheet":
            raise refused(action, "the dialog was cancelled")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", prefix="vesper-sheet-", delete=False,
                                         encoding="utf-8") as file:
            file.write(sheet.full)
        os.chmod(file.name, 0o600)
        run(["open", "-t", file.name])
    raise refused(action, "no decision")


def stand_in_confirm(action, sheet, digest, program):
    """Test only: the stand-in gets the action, the digest and the full sheet; exit 0 confirms."""
    try:
        done = subprocess.run([program, action], input=sheet.full, text=True, capture_output=True, timeout=120,
                              env={**os.environ, "VESPER_CONFIRM_DIGEST": digest})
    except (OSError, subprocess.SubprocessError) as exc:
        raise refused(action, f"the test confirmer failed: {exc}") from exc
    if done.returncode != 0:
        raise refused(action, "the test confirmer said no")


def configured_confirmer():
    from .brains import load_settings
    return load_settings().get("approvals.confirmer", "tty")


def confirm(action, subject, digest, sheet, *, environ=None, confirmer=None, stdin=None):
    """Ask a human to confirm `action` on `subject`, bound to `digest`; return the record to keep
    once the action has succeeded. Raises when the human does not confirm."""
    from .runner import stamp
    environ = os.environ if environ is None else environ
    require(action in ACTIONS, f"Unknown protected action {action}")
    program = environ.get(TEST_CONFIRMER)
    if program:
        stand_in_confirm(action, sheet, digest, program)
        used = "test-stand-in"
    else:
        used = confirmer or configured_confirmer()
        if used == "tty":
            tty_confirm(action, sheet, stdin=stdin)
        elif used == "macos-dialog":
            dialog_confirm(action, sheet)
        elif used in LATER:
            raise BuilderError(f"The {used} confirmer is not available yet; use tty or macos-dialog")
        else:
            raise BuilderError(f"Unknown confirmer {used!r}; use tty or macos-dialog")
    return {"action": action, "subject": subject, "digest": digest, "confirmer": used, "at": stamp(),
            "files": sheet.files}


# Records --------------------------------------------------------------------------------

def run_store(root):
    """Confirmations about one run: plan approval, attesting its reviews, adding checks, accepting risks."""
    return Path(root) / ".builder" / "confirmations.json"


def repository_store():
    """Confirmations about a repository, across runs: patch apply, repair commit."""
    from .learning import state_home
    return state_home() / "confirmations.json"


@contextmanager
def locked(store):
    store.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (store.parent / (store.name + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def records(store):
    if not store.is_file():
        return []
    data = read_json(store)
    require(isinstance(data, list), f"Invalid confirmation records in {store}")
    return data


def last(store, action, subject):
    """The newest human confirmation of `action` on `subject`, or None. Sheets read this; only a
    confirmation moves it, never printing a sheet."""
    matches = [item for item in records(store) if item.get("action") == action and item.get("subject") == subject]
    return matches[-1] if matches else None


def keep(store, record):
    from .runner import atomic_json
    with locked(store):
        atomic_json(store, records(store) + [record])
        store.chmod(0o600)


# Files and changes ------------------------------------------------------------------------

def entry(path, name):
    data = Path(path).read_bytes()
    lines = None if b"\0" in data else data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    return {"path": name, "sha256": sha256(data).hexdigest(), "size": len(data), "lines": lines}


def tree_entries(root, bundle, areas=("plan", "checks", "seed")):
    """The confirmed file list for a plan: every file in plan/, checks/ and seed/."""
    return [entry(Path(root) / area / name, f"{area}/{name}")
            for area in areas for name, (digest, _) in sorted(bundle.get(area, {}).items()) if digest is not None]


def changes(previous, current):
    """Files added, removed and edited between two confirmed file lists."""
    before = {item["path"]: item for item in previous}
    after = {item["path"]: item for item in current}
    return {
        "added": [{"path": name, "lines": after[name]["lines"]} for name in sorted(after.keys() - before.keys())],
        "removed": [{"path": name, "lines": before[name]["lines"]} for name in sorted(before.keys() - after.keys())],
        "edited": [{"path": name, "lines_before": before[name]["lines"], "lines_after": after[name]["lines"]}
                   for name in sorted(before.keys() & after.keys())
                   if before[name]["sha256"] != after[name]["sha256"]],
    }


def lines_text(count):
    return "binary" if count is None else f"{count} line{'' if count == 1 else 's'}"


def what_changed_text(changed, first="first confirmation"):
    """The "what changed" section of every sheet."""
    if changed is None:
        return f"What changed: {first}"
    if not any(changed.values()):
        return "What changed: nothing since the last confirmation"
    rows = ["What changed since the last confirmation:"]
    for item in changed["added"]:
        name = item if isinstance(item, str) else item["path"]
        rows.append(f"  added   {name}" + ("" if isinstance(item, str) else f" ({lines_text(item['lines'])})"))
    for item in changed["removed"]:
        name = item if isinstance(item, str) else item["path"]
        rows.append(f"  removed {name}" + ("" if isinstance(item, str) else f" ({lines_text(item['lines'])})"))
    for item in changed["edited"]:
        before, after = item["lines_before"], item["lines_after"]
        span = "binary" if None in (before, after) else f"{before} → {after} lines"
        rows.append(f"  edited  {item['path']} ({span})")
    return "\n".join(rows)


def changed_since(store, action, subject, files):
    """(changes or None, the previous record or None) against the last confirmation."""
    previous = last(store, action, subject)
    return (changes(previous.get("files", []), files) if previous else None), previous


def short_digest(value):
    return value[:12]


def text_digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
