"""Plain-language approval sheets (P2-T2): what a human confirms, built only from the program's
own records for that action, so the sheet describes exactly what the confirmation locks."""
from pathlib import Path

from .approvals import Sheet, changed_since, lines_text, short_digest, what_changed_text
from .planning import proposed_risks

RISK = "Accepted risk: owner must confirm"
TOP_FINDINGS = 5


def one_line(text, limit=120):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def in_full(text):
    """Whitespace collapsed, never shortened: the owner accepts exactly these words."""
    return " ".join(str(text).split())


def short_form(title, facts, changed, digest):
    """The dialog form: the essentials, always with what changed and the short digest."""
    return "\n".join([title, *facts, "", changed, "", f"Digest: {short_digest(digest)}",
                      "Choose \"Show full sheet\" to read every field."]) + "\n"


# Plan approval ------------------------------------------------------------------------------

def plan_sheet(root, contract, bundle, digest, store):
    from .approvals import tree_entries
    files = tree_entries(root, bundle)
    changed, _ = changed_since(store, "approve-plan", str(root), files)
    changed = what_changed_text(changed, first="first approval")
    intake = bundle.get("intake") or {}
    repository = (intake.get("repository") or {}).get("path")
    mode = f"{intake.get('mode', 'change')} change to the repository at {repository}" if repository else "new build"
    planning = bundle.get("planning") or {}
    critique = bundle.get("plan_critique")
    findings = (critique or {}).get("report", {}).get("findings", [])
    blockers = [item for item in findings if item.get("severity") == "blocking"]
    # Approving accepts every listed risk: those the critic marks for the owner and, P2-T7, every
    # security or data advisory. Blockers the owner accepted with `decide` are listed with their reason.
    risks = [item for item in findings if item.get("severity") == "advisory" and (
        str(item.get("recommendation", "")).startswith(RISK) or item.get("category") in ("security", "data"))]
    decided = []
    if critique:
        from .decisions import accepted_plan_blockers
        decided = accepted_plan_blockers(root, critique)
    manifest = planning.get("manifest") or {}
    proposed = proposed_risks(manifest)  # P2-T5: each list item the plan proposes as a risk
    if planning.get("depth") == "skip":
        verdict = ("Critique: none (skip depth). Recorded reason: "
                   + one_line(planning.get("manifest", {}).get("rationale", "not given"), 200))
    elif critique:
        report = critique["report"]
        verdict = (f"Critique: {report['verdict']}, {len(blockers)} blocker{'' if len(blockers) == 1 else 's'}"
                   + (f", {len(decided)} accepted by you" if decided else "")
                   + f" (reviewer {report.get('reviewer', 'not stated')}, {critique.get('provider', 'operator')})")
    else:
        verdict = f"Critique: not run yet (required before approval at {planning.get('depth', 'this')} depth)"
    lines = ["Vesper Relay: approve this plan", "",
             f"Delivers: {contract['title']}: {one_line(contract['delivery'], 200)}", f"Mode: {mode}", "",
             "Requirements (each promise and the gate that proves it):"]
    lines += [f"  {item['id']}: {one_line(item['description'], 160)} → {', '.join(item['checks'])}"
              for item in contract["requirements"]]
    lines += ["", "Jobs (who changes what):"]
    for job in contract["jobs"]:
        after = f", after {', '.join(job['depends_on'])}" if job.get("depends_on") else ""
        lines.append(f"  {job['id']} ({job['role']}{after}): {one_line(job['goal'])}")
        lines.append(f"    may change only: {', '.join(job['paths'])}")
    lines += [""]
    if planning:
        lines.append(f"Planning: {planning['depth']} depth, manifest version {manifest.get('version')}")
    lines.append(verdict)
    from .qa import sheet_lines
    from .runner import Runner
    lines += sheet_lines(Runner(Path(root)), bundle)  # P3-T3: which checks are proven to fail
    recorded = [item["id"] for item in contract["checks"] if item.get("blocking", True) is False]
    if recorded:
        lines.append("Recorded only, never blocking (such as mutation scores): " + ", ".join(recorded))
    advisories = [item for item in findings if item.get("severity") == "advisory" and item not in risks]
    for item in blockers + advisories[:TOP_FINDINGS]:
        lines.append(f"  {item['severity']}: {item.get('path', '')}: {one_line(item.get('recommendation', ''))}")
    lines += ["", "Risks you accept by approving:"]
    if risks or proposed or decided:
        lines += [f"  - {item['id']} (blocker you accepted): {in_full(item['recommendation'])} "
                  f"({item.get('path', '')}). Your reason: {in_full(item['decision']['reason'])}" for item in decided]
        lines += [f"  - {one_line(item['recommendation'], 400)} ({item.get('path', '')})" for item in risks]
        lines += [f"  - {item['id']}: {in_full(item['item'])}. Reason: {in_full(item['accept'])} "
                  f"(plan/planning.json {item['section']})" for item in proposed]
        lines.append("  Confirming this approval is your acceptance of each risk above.")
    else:
        lines.append("  none listed")
    wireframes = sorted(name for name in bundle.get("plan", {}) if "wireframe" in name.lower())
    lines += ["", changed, "",
              "Look further: the plan/ and checks/ folders of this run"
              + (f"; wireframes: {', '.join('plan/' + name for name in wireframes[:6])}" if wireframes else ""),
              f"Digest: {short_digest(digest)}"]
    facts = [f"Delivers: {contract['title']}", f"{len(contract['requirements'])} requirements, "
             f"{len(contract['jobs'])} jobs", verdict, f"Risks you accept: {len(risks) + len(proposed) + len(decided)}"]
    return Sheet("\n".join(lines) + "\n", short_form("Vesper Relay: approve this plan", facts, changed, digest),
                 files)


# Patch apply and repair commit ----------------------------------------------------------------

def line_changes(before, after, names):
    """{name: (added, removed)} between two snapshot folders."""
    import difflib
    counts = {}
    for name in names:
        old, new = Path(before) / name, Path(after) / name
        try:
            a = old.read_text(encoding="utf-8").splitlines() if old.is_file() else []
            b = new.read_text(encoding="utf-8").splitlines() if new.is_file() else []
        except UnicodeError:
            counts[name] = None
            continue
        added = removed = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag in ("replace", "delete"):
                removed += i2 - i1
            if tag in ("replace", "insert"):
                added += j2 - j1
        counts[name] = (added, removed)
    return counts


def changed_files(after, names):
    from .approvals import entry
    return [entry(Path(after) / name, name) if (Path(after) / name).is_file()
            else {"path": name, "sha256": None, "size": 0, "lines": 0} for name in names]


def verdicts(state):
    rows = []
    for item in state["attempts"]:
        if item.get("outcome") == "accepted":
            review = item.get("review") or {}
            rows.append(f"  {item['job']}: " + (f"{review['verdict']} ({review.get('provider', 'operator')})"
                                                 if review.get("verdict") else "no independent review")
                        + (f"; you accepted {', '.join(item['accepted_risks'])} as risks"
                           if item.get("accepted_risks") else ""))
    return rows or ["  none recorded"]


def file_rows(counts):
    rows = []
    for name, value in counts.items():
        rows.append(f"  {name}: " + ("binary" if value is None else f"+{value[0]} −{value[1]} lines"))
    return rows


def patch_sheet(store, repository, branch, summary, before, after, state):
    counts = line_changes(before, after, summary["files"])
    files = changed_files(after, summary["files"])
    changed = what_changed_text(changed_since(store, "apply-patch", repository, files)[0])
    lines = ["Vesper Relay: apply this reviewed patch", "", f"Repository: {repository}", f"Branch: {branch}",
             "", "Files and lines:", *file_rows(counts), "", "Independent review:", *verdicts(state), "",
             changed, "", f"Patch digest: {short_digest(summary['digest'])}"]
    facts = [f"Repository: {repository} ({branch})", f"{len(counts)} file{'' if len(counts) == 1 else 's'}: "
             + ", ".join(counts)[:200]]
    return Sheet("\n".join(lines) + "\n", short_form(lines[0], facts, changed, summary["digest"]), files)


def repair_sheet(store, repository, summary, before, after, state):
    counts = line_changes(before, after, summary["files"])
    files = changed_files(after, summary["files"])
    seed = state["bundle"]["seed"]
    tests = [name for name in summary["files"] if name.startswith("tests/") and name not in seed]
    changed = what_changed_text(changed_since(store, "commit-repair", repository, files)[0])
    failure = state["bundle"].get("repair", {}).get("failure_id", "not recorded")
    lines = ["Vesper Relay: commit this repair to a local repair branch", "", f"Failure: {failure}",
             f"Repository: {repository}", "", "Files and lines:", *file_rows(counts), "",
             "Tests added: " + (", ".join(tests) if tests else "none"), "", "Independent review:",
             *verdicts(state), "", changed, "", f"Patch digest: {short_digest(summary['digest'])}"]
    facts = [f"Failure: {failure}", f"{len(counts)} file{'' if len(counts) == 1 else 's'}, "
             f"{len(tests)} test{'' if len(tests) == 1 else 's'} added"]
    return Sheet("\n".join(lines) + "\n", short_form(lines[0], facts, changed, summary["digest"]), files)


# Attesting independence ---------------------------------------------------------------------

def attest_sheet(store, subject, what, report, adapter=None):
    from .approvals import text_digest
    digest = text_digest(report)
    findings = report.get("findings", [])
    blockers = sum(1 for item in findings if item.get("severity") == "blocking")
    files = [{"path": "report.json", "sha256": digest, "size": len(str(report)), "lines": None}]
    changed = what_changed_text(changed_since(store, "attest-independence", subject, files)[0])
    lines = ["Vesper Relay: attest an independent review", "", f"Review of: {what}",
             f"Report: {short_digest(digest)}",
             f"Reviewer session it claims: {report.get('reviewer') or 'not stated'}",
             f"Adapter it claims: {adapter or report.get('adapter') or 'not stated (operator-supplied report)'}",
             f"Verdict: {report.get('verdict')}, {blockers} blocker{'' if blockers == 1 else 's'}", "",
             "By confirming you vouch: this report came from a separate reviewer session, not the author.", "",
             changed]
    facts = [f"Review of: {what}", f"Verdict: {report.get('verdict')}, {blockers} blockers",
             "You vouch: this report came from a separate reviewer session, not the author."]
    return Sheet("\n".join(lines) + "\n", short_form(lines[0], facts, changed, digest), files), digest


# Adding a check after approval (P2-T6) -------------------------------------------------------

def add_check_sheet(contract, record, digest, folder, changed, earlier, files, source=None):
    """Each new check's id and its script or command, its jobs and the reason, all from the
    amendment record the confirmation locks."""
    import shlex
    from .approvals import entry
    check = record["check"]
    if "script" in check:
        size = lines_text(entry(source, check["script"])["lines"]) if source else "size not known"
        how = f"Script: {check['script']} ({size}), run as python3 -I -B {check['script']} CANDIDATE"
        where = f".builder/amendments/{folder}/checks/{check['script']}"
    else:
        how = f"Command: {shlex.join(check['command'])}, run in a throwaway copy of the candidate"
        where = f".builder/amendments/{folder}/amendment.json"
    jobs = ", ".join(record["jobs"])
    changed = what_changed_text(changed)
    lines = ["Vesper Relay: add a check after approval", "", f"Run: {contract['title']}", "",
             f"New check: {check['id']}", f"  {how}",
             f"  Must pass on: {jobs} (the last job to finish also runs every gate)",
             f"  Reason: {in_full(record['reason'])}", "",
             "Nothing approved is removed or edited: every approved check still runs on its jobs.",
             f"Checks added earlier in this run: {earlier}", "", changed, "",
             f"Look further: {where}",
             f"Approved plan: {short_digest(record['approval'])}", f"Digest: {short_digest(digest)}"]
    facts = [f"New check: {check['id']}", one_line(how), f"Must pass on: {jobs}",
             f"Reason: {one_line(record['reason'])}"]
    return Sheet("\n".join(lines) + "\n", short_form(lines[0], facts, changed, digest), files)


# Accepting a risk (P2-T7) -------------------------------------------------------------------------

def risk_sheet(store, subject, item, accepts, reason, digest):
    """The finding in plain words, its severity and source, and exactly what is being accepted."""
    from .decisions import describe
    files = [{"path": f"findings/{item['id']}", "sha256": digest, "size": 0, "lines": None}]
    changed = what_changed_text(changed_since(store, "accept-risk", subject, files)[0])
    kind = f"{item['category']} {'blocker' if item['severity'] == 'blocking' else 'advisory'}"
    if item.get("suspected"):
        kind = f"{item['category']} suspected blocker (no repro, so it did not block)"  # P3-T4
    # P3-T4: a dismissal confirms on this sheet too; its text says what is dismissed.
    title = "Vesper Relay: dismiss a finding" if accepts.startswith("You dismiss") else "Vesper Relay: accept a risk"
    lines = [title, "", f"Finding {item['id']}: {kind}, from {describe(item)}",
             f"  Where: {item.get('path') or 'not stated'}"]
    if item.get("scenario"):
        lines.append(f"  When: {in_full(item['scenario'])}")
    if item.get("consequence"):
        lines.append(f"  Then: {in_full(item['consequence'])}")
    lines += [f"  What the reviewer found: {in_full(item.get('evidence', 'not stated'))}"]
    if item.get("repro"):
        lines.append(f"  How to reproduce it: {in_full(item['repro'])}")
    lines += [f"  What the reviewer recommends: {in_full(item['recommendation'])}", "",
              f"What you accept: {accepts}", f"Your reason: {in_full(reason)}", "",
              "The finding stays on record; only your confirmation accepts it.", "", changed, "",
              f"Digest: {short_digest(digest)}"]
    facts = [f"Finding {item['id']}: {kind}, from {describe(item)}",
             f"Found: {one_line(item.get('evidence', ''))}", f"You accept: {one_line(accepts, 200)}",
             f"Your reason: {one_line(reason)}"]
    return Sheet("\n".join(lines) + "\n", short_form(lines[0], facts, changed, digest), files)
