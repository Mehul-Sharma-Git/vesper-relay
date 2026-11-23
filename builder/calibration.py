"""Reviewer calibration (P3-T4): what became of each job-review finding.

Each run keeps `.builder/calibration.jsonl`, one JSON object per line, appended only:

    unknown    the finding was recorded (every job-review finding starts here)
    confirmed  the job came back and the fix changed the finding's path
    dismissed  the owner dismissed it as not a defect (`decide F --dismiss`, human-confirmed)

A finding's latest line is its outcome. Each line names the lenses that raised the finding
(`combined` for a single review). Precision per lens is confirmed / (confirmed + dismissed);
findings still unknown are counted but not in the ratio. `vesper learn` reports it over every
run in the state folder.
"""
import json
from pathlib import Path

FILE = "calibration.jsonl"
OUTCOMES = ("unknown", "confirmed", "dismissed")


def path(root):
    return Path(root) / ".builder" / FILE


def append(root, rows):
    """Add rows (each with finding, lens, outcome and what else is known) to the run's file."""
    from .runner import stamp
    if not rows:
        return
    target = path(root)
    target.parent.mkdir(mode=0o700, exist_ok=True)
    with target.open("a", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps({"at": stamp(), **row}, ensure_ascii=False) + "\n")


def rows(root):
    """Every row of the run's file, oldest first; a damaged line is skipped, never fatal."""
    target = path(root)
    if not target.is_file() or target.is_symlink():
        return []
    found = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("finding"), str) and row.get("outcome") in OUTCOMES:
            found.append(row)
    return found


def outcomes(found):
    """{finding ID: its latest row}."""
    latest = {}
    for row in found:
        latest[row["finding"]] = row
    return latest


def finding_path(value):
    """A finding's file path without a trailing :line or :line:column."""
    text = str(value or "")
    while ":" in text and text.rsplit(":", 1)[1].isdigit():
        text = text.rsplit(":", 1)[0]
    return text


def tally(latest, counts=None):
    """Add each finding's outcome to its lenses' counts."""
    counts = {} if counts is None else counts
    for row in latest.values():
        lenses = row.get("lens") if isinstance(row.get("lens"), list) and row.get("lens") else ["combined"]
        for lens in lenses:
            entry = counts.setdefault(str(lens), dict.fromkeys(("confirmed", "dismissed", "unknown"), 0))
            entry[row["outcome"]] += 1
    return counts


def ratios(counts):
    """Each lens's counts with its precision (None until something is confirmed or dismissed)."""
    result = {}
    for lens in sorted(counts):
        entry = {key: counts[lens][key] for key in ("confirmed", "dismissed", "unknown")}
        decided = entry["confirmed"] + entry["dismissed"]
        entry["precision"] = round(entry["confirmed"] / decided, 3) if decided else None
        result[lens] = entry
    return result


def precision(found):
    """Precision per lens for one run's rows."""
    return ratios(tally(outcomes(found)))


def across(runs_folder):
    """Precision per lens over every run folder under ``runs_folder``."""
    counts = {}
    folder = Path(runs_folder)
    if folder.is_dir():
        for run in sorted(folder.iterdir()):
            if run.is_dir() and not run.is_symlink():
                tally(outcomes(rows(run)), counts)
    return ratios(counts)
