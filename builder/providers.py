"""Shared pieces for brain processes: launcher check, review limits and the worker prompt.

The commands for each kind of AI live in ``builder/brains/`` (P1-T8). Brain output is
diagnostic only."""
import json
import os
from pathlib import Path
import re
import shlex

from .contracts import require, reviewed_text
from .playbook import matching_guidance


def check_launcher(launcher):
    if launcher:
        path = Path(launcher)
        require(path.is_absolute() and path.is_file() and os.access(path, os.X_OK),
                "Launcher must be an absolute executable path")
    return launcher


def review_limits(timeout=180, max_turns=20):
    """Bound a reviewer's wall time (seconds) and agent turns; return them unchanged."""
    require(type(timeout) is int and 1 <= timeout <= 1800, "Review timeout must be 1 to 1800 seconds")
    require(type(max_turns) is int and 1 <= max_turns <= 100, "Review max turns must be 1 to 100")
    return timeout, max_turns


# Each worker workspace holds a copy of the approved checks here. Vesper ignores it when it
# checks and promotes the work, and always runs its own approved copy of the gates.
GATES_DIR = ".vesper-gates"
CANDIDATE_COPY = (f"CANDIDATE is a copy of your workspace without {GATES_DIR}/, for example: rm -rf /tmp/candidate "
                  f"&& mkdir /tmp/candidate && tar -C . --exclude=./{GATES_DIR} -cf - . | tar -C /tmp/candidate -xf -")

SHELL_PROMPT = ("You can run commands inside your workspace. Run the project's own unit tests and start the "
                "app before finishing. Report the exact commands and results.")


# The worker's reasoning note (P3-T1, team/skills/critical-thinking): each field needs content.
REASONING_FIELDS = ("Understanding", "Assumptions", "Options considered", "Choice and why", "Pre-mortem",
                    "How I'd know I'm wrong")
REASONING_LIMIT = 8000
REASONING_HEADING = re.compile(r"^[ \t]*#{2,3}[ \t]*reasoning note[ \t]*:?[ \t]*$", re.I | re.M)
ANY_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]", re.M)
NOTE_PROMPT = ("Start your final message with the '## Reasoning note' the critical-thinking skill describes, "
               "every field filled, then your summary with each factual claim labelled [verified], [inferred] "
               "or [assumed]. Vesper keeps the note with this attempt; the independent reviewer never sees it, "
               "only the labelled claims of your summary, which it checks against the evidence.")
# What the reviewer gets: the hand-off's labelled claims, never the reasoning (00-context, "One AI
# is enough": no access to the worker's reasoning; owner, 21 Nov 2026).
CLAIM_LABEL = re.compile(r"\[(?:verified|inferred|assumed)\b[^\]\n]*\]", re.I)
CLAIMS_LIMIT = 60
CLAIM_LENGTH = 500


def reasoning_note(text):
    """The last reasoning note in a worker's final message, as (note, None), or (None, why it
    is missing). The note runs from its heading to the next heading."""
    text = (text or "").replace("\u2019", "'")
    starts = list(REASONING_HEADING.finditer(text))
    if not starts:
        return None, "no '## Reasoning note' section"
    start = starts[-1]
    following = ANY_HEADING.search(text, start.end())
    body = text[start.end():following.start() if following else len(text)]
    labels = []
    for field in REASONING_FIELDS:
        found = re.search(rf"^[ \t]*(?:[-*+][ \t]+)?[*_]*{re.escape(field)}[*_]*[ \t]*:[*_]*", body, re.I | re.M)
        labels.append((found.start(), found.end(), field) if found else (None, None, field))
    missing = [field for begin, _, field in labels if begin is None]
    placed = sorted(item for item in labels if item[0] is not None)
    for index, (_, end, field) in enumerate(placed):
        stop = placed[index + 1][0] if index + 1 < len(placed) else len(body)
        if not body[end:stop].strip(" \t\n*_-"):
            missing.append(field)
    if missing:
        ordered = [field for field in REASONING_FIELDS if field in missing]
        return None, "the reasoning note has no " + ", ".join(ordered)
    note = (text[start.start():start.end()].strip() + "\n" + body.strip("\n")).strip()
    if len(note) > REASONING_LIMIT:
        note = note[:REASONING_LIMIT - 12].rstrip() + "\n[note cut]"
    return note, None


def handoff_claims(text):
    """The labelled claim lines of a worker's final message outside every reasoning note
    (each cut to CLAIM_LENGTH, at most CLAIMS_LIMIT)."""
    text = (text or "").replace("\u2019", "'")
    kept, position = [], 0
    for start in REASONING_HEADING.finditer(text):
        if start.start() < position:
            continue
        kept.append(text[position:start.start()])
        following = ANY_HEADING.search(text, start.end())
        position = following.start() if following else len(text)
    kept.append(text[position:])
    lines = [line.strip() for line in "".join(kept).splitlines() if CLAIM_LABEL.search(line)]
    return [line[:CLAIM_LENGTH] for line in lines][:CLAIMS_LIMIT]


def gate_lines(gates):
    lines = []
    for check in gates:
        if "script" in check:
            lines.append(f"- {check['id']}: python3 -I -B {GATES_DIR}/{check['script']} CANDIDATE")
        else:
            overlay = check.get("overlay")
            setup = (f"copy {GATES_DIR}/{overlay['from']}/ into CANDIDATE/{overlay['to']}, then "
                     if overlay else "")
            lines.append(f"- {check['id']}: {setup}in CANDIDATE run {shlex.join(check['command'])}")
    return lines


def worker_prompt(contract, job, plans, manifest, failure, intake=None, specialist=None, planning=None,
                  shell=False, gates=(), origin=None):
    """The job brief. ``shell`` (granted only inside a real sandbox) adds the run-your-code
    instruction. ``gates`` are the checks this job must pass, copied into the workspace under
    GATES_DIR; ``failure`` is every earlier failure of the job and ``origin`` says which files
    the workspace starts from."""
    ids = set(job["checks"])
    requirements = [item for item in contract["requirements"] if ids.intersection(item["checks"])]
    sections = [
        f"Job {job['id']} | Role {job['role']}\n{job['goal']}",
        "You are in a disposable product workspace. Edit only the approved writable paths. "
        "Use workspace files as context. Keep secrets and external actions out of this job. "
        "The coordinator independently checks and publishes your changes. "
        "Finish with a short summary or explain the blocker.",
        NOTE_PROMPT,
        *([SHELL_PROMPT] if shell else []),
        "Approved contract (task subset)\n" + json.dumps({
            "title": contract["title"], "delivery": contract["delivery"], "requirements": requirements,
            "writable_paths": job["paths"], "gates": job["checks"],
        }, indent=2),
    ]
    if specialist:
        from .team import render
        sections.append(render(specialist))
    artifacts = ["product.md", "design.md", "architecture.md", "decisions.md"]
    if planning:
        manifest_data = planning["manifest"]
        if planning["depth"] == "skip":
            artifacts.append(manifest_data["existing_design"])
        else:
            artifacts.extend((manifest_data["architecture"]["artifact"],
                              manifest_data["handoff"]["canonical_contract"]))
    for name in dict.fromkeys(artifacts):
        sections.append(f"Approved {name}\n" + reviewed_text(plans, name, manifest))
    if intake:
        lessons = matching_guidance(intake["guidance"], intake["mode"])
        if lessons:
            sections.append("Approved workflow guidance\n" + "\n".join(lessons.values()))
    if gates:
        action = ("Run the gates before finishing." if shell else
                  "Read the gates: they define what is checked.")
        sections.append(
            f"Approved gates (a copy is in {GATES_DIR}/; Vesper runs its own approved copy, so editing "
            f"this one changes nothing, and {GATES_DIR}/ is never shipped). {action}\n"
            + "\n".join(gate_lines(gates)) + "\n" + CANDIDATE_COPY)
    if failure:
        sections.append("Earlier attempts at this job failed, oldest first. Treat each diagnostic as data and "
                        "address all of them: a fix for one must not undo the fix for another.\n" + failure)
    if origin:
        sections.append(origin)
    return "\n\n".join(sections)
