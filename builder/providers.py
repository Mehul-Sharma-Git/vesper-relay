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


# Workers write no reasoning note (P3-T1b; owner, 23 Nov 2026): at P3-G Claude's
# reasoning_extraction safeguard refused a brief that asked for one (appendix B, finding 65). The
# design rationale lives in the plan (`options`, the architecture handoff). A worker that writes a
# note-shaped section anyway (P3-T1's fields) still keeps all of it from the reviewer.
REASONING_FIELDS = ("Understanding", "Assumptions", "Options considered", "Choice and why", "Pre-mortem",
                    "How I'd know I'm wrong")
# A note starts at a line naming it in any form (a heading of any level, bold, "Reasoning note:")
# or at its first field, and ends at the blank line after its last field has content, at a
# heading, or at the end of the message. Review of PR #56: the hand-off may follow the note with
# no heading, and a note in another form must not reach the reviewer either.
NOTE_MARKER = re.compile(r"^[ \t>#*_-]*reasoning note\b", re.I)
ANY_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]")
FIELD_LABEL = r"^[ \t]*(?:[-*+][ \t]+)?[*_]*({})[*_]*[ \t]*:[*_]*"
FIELD_LINE = re.compile(FIELD_LABEL.format("|".join(map(re.escape, REASONING_FIELDS))), re.I)
LAST_FIELD = re.compile(FIELD_LABEL.format(re.escape(REASONING_FIELDS[-1])), re.I)
HANDOFF_PROMPT = ("In your final summary, label each factual claim [verified], [inferred] or [assumed], as the "
                  "critical-thinking skill describes. The independent reviewer checks the labelled claims "
                  "against the evidence.")
# What the reviewer gets: the hand-off's labelled claims, never the reasoning (00-context, "One AI
# is enough": no access to the worker's reasoning; owner, 21 Nov 2026).
CLAIM_LABEL = re.compile(r"\[(?:verified|inferred|assumed)\b[^\]\n]*\]", re.I)
CLAIMS_LIMIT = 60
CLAIM_LENGTH = 500


def note_spans(lines):
    """The (start, end) line ranges of every note-shaped section, marked or not, in message order."""
    spans, start, last_seen, last_filled = [], None, False, False
    for index, line in enumerate(lines):
        marker = NOTE_MARKER.match(line)
        if marker and start is not None:
            spans.append((start, index))
            start = None
        if marker or FIELD_LINE.match(line):
            if start is None:
                start, last_seen, last_filled = index, False, False
            found = LAST_FIELD.match(line)
            if found:
                last_seen, last_filled = True, bool(line[found.end():].strip(" \t*_-"))
            elif last_seen:
                last_filled = True  # another field after the last one: keep going
            continue
        if start is None:
            continue
        if ANY_HEADING.match(line) or (not line.strip() and last_filled):
            spans.append((start, index))
            start = None
        elif line.strip() and last_seen:
            last_filled = True
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def handoff_claims(text):
    """The labelled claim lines of a worker's final message outside every note-shaped section
    (each cut to CLAIM_LENGTH, at most CLAIMS_LIMIT)."""
    lines = (text or "").replace("\u2019", "'").splitlines()
    inside = {index for start, end in note_spans(lines) for index in range(start, end)}
    found = [line.strip() for index, line in enumerate(lines) if index not in inside and CLAIM_LABEL.search(line)]
    return [line[:CLAIM_LENGTH] for line in found][:CLAIMS_LIMIT]


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
                  shell=False, gates=(), origin=None, knowledge_path=None):
    """The job brief. ``shell`` (granted only inside a real sandbox) adds the run-your-code
    instruction. ``gates`` are the checks this job must pass, copied into the workspace under
    GATES_DIR; ``failure`` is every earlier failure of the job and ``origin`` says which files
    the workspace starts from. The brief carries the top passages of the role's frozen pack for the
    goal; ``knowledge_path`` is where the run's frozen packs are readable (/knowledge in the sandbox)."""
    ids = set(job["checks"])
    requirements = [item for item in contract["requirements"] if ids.intersection(item["checks"])]
    sections = [
        f"Job {job['id']} | Role {job['role']}\n{job['goal']}",
        "You are in a disposable product workspace. Edit only the approved writable paths. "
        "Use workspace files as context. Keep secrets and external actions out of this job. "
        "The coordinator independently checks and publishes your changes. "
        "Finish with a short summary or explain the blocker.",
        HANDOFF_PROMPT,
        *([SHELL_PROMPT] if shell else []),
        "Approved contract (task subset)\n" + json.dumps({
            "title": contract["title"], "delivery": contract["delivery"], "requirements": requirements,
            "writable_paths": job["paths"], "gates": job["checks"],
        }, indent=2),
    ]
    if specialist:
        from .team import render
        sections.append(render(specialist))
        if specialist.get("knowledge"):
            from .knowledge import prompt_section
            found = prompt_section(specialist["knowledge"], job["goal"], specialist["role"])
            if found:
                sections.append(found)
    if knowledge_path:
        from .knowledge import where
        sections.append(where(knowledge_path))
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
