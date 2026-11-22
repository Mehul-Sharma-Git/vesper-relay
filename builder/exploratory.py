"""Exploratory QA session (P3-T5): QA tries to break a frontend candidate the way people do.

Gates check what the plan promised; an exploratory session looks for what nobody wrote down.
After a frontend job's candidate passes its gates, at focused and full depth, QA explores a
throwaway copy of it (with a shell and Playwright only inside a sandbox backend) and tries
each probe in PROBES. QA's folder holds:

    app/       a copy of the tested candidate: QA may build and run it there; it is never promoted
    plan/      the approved plan, for what the product promises
    report/    what QA writes:
                 exploratory.md    the report people read, with each bug's repro steps
                 exploratory.json  the same findings, structured (below), and an account of every probe
                 proposed-checks/  optional: <CHECK_ID>.py, a gate script for a bug that matters

exploratory.json is {"summary", "probes": {probe: what was tried and seen}, "findings": [...]};
each finding has severity (blocking: a bug that matters; advisory), category (the review
categories), probe, path (a screen or file), scenario, evidence, recommendation, repro (the
steps), optionally consequence and proposed_check (a check ID with its script in
proposed-checks/).

Findings enter the backlog (P2-T7) as `noted` items with their category and severity: the session
never rejects or holds a candidate (its gates and the independent review decide). A bug that matters
becomes a check only through `add-check` (P2-T6), which the owner confirms; the session keeps the
proposed script and prints the command. The report and proposals are kept under
`.builder/attempts/<attempt>/exploratory/<session>/` and recorded on the attempt in the run's state.
"""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from uuid import uuid4

from .contracts import BuilderError, fingerprint, inventory, require

PROBES = ("empty-input", "long-text", "emoji", "double-click", "back-button", "slow-network", "two-tabs",
          "keyboard-only")
DEPTHS = ("focused", "full")
REPORT, FINDINGS, PROPOSED = "exploratory.md", "exploratory.json", "proposed-checks"
SEVERITIES = ("blocking", "advisory")
REQUIRED = ("severity", "category", "probe", "path", "scenario", "evidence", "recommendation", "repro")
OPTIONAL = ("consequence", "proposed_check")
REPORT_LIMIT = 200_000
SCRIPT_LIMIT = 256_000
TEXT_LIMIT = 4000
FINDING_LIMIT = 50
TIMEOUT = 600
CHECK_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")

TASK = """You are QA, running an exploratory session on job {job}'s candidate. Its gates passed; your
job is to find what they do not check, the way real people break things.

Your folder holds app/ (a throwaway copy of the candidate: build and run it there; it is never
shipped), plan/ (the approved plan: what the product promises) and report/ (where you write).
{tools}
Try every probe on the main journeys, on a phone and a laptop viewport:

- empty-input: submit empty and whitespace-only fields
- long-text: very long text (thousands of characters, one unbroken word)
- emoji: emoji, combined emoji (family, flags, skin tones) and right-to-left text
- double-click: double clicks and repeated submits on every action
- back-button: the browser back and forward buttons in the middle of a journey
- slow-network: a slow or failing network (delay or abort requests with Playwright's route)
- two-tabs: the same data open in two tabs, changed in both
- keyboard-only: every journey with the keyboard alone: focus order, visible focus, Enter and Escape

Write, in report/:

1. {report}: a short report people read. For each bug: a title, the probe, the repro steps
   (numbered, from a fresh start), what you saw and what the plan promises instead.
2. {findings}: {{"summary": "...", "probes": {{<each probe above>: "what you tried and saw, or why
   it could not be run"}}, "findings": [{{"severity": "blocking" (a bug that matters) or "advisory",
   "category": one of {categories}, "probe": a probe above or "other", "path": the screen or file,
   "scenario", "consequence", "evidence" (what you observed), "recommendation", "repro" (the
   numbered steps), and optionally "proposed_check"}}]}}.
3. For a bug that matters, a gate that fails on it: report/{proposed}/<CHECK_ID>.py (a Python
   gate run as `python3 -I <script> <candidate dir>`, exit 0 for pass), named by the finding's
   "proposed_check". The owner decides whether to add it with add-check; nothing is added for you.

Label each claim [verified] (you ran it), [inferred] or [assumed]. Do not report a probe you did
not run as passed.
"""
SHELL = ("You have a shell inside the sandbox: run the app from app/ as plan/architecture.md says, on\n"
         "127.0.0.1, and drive it with Playwright (installed for Node and Python, with Chromium).\n")
NO_SHELL = ("You have no shell in this session (no sandbox backend), so you cannot run the app: read the\n"
            "code, label what you find [inferred], and say for each probe that it was not run.\n")


def why_not(state, job):
    """Why this job's candidate gets no exploratory session, or None."""
    if job["role"] != "frontend":
        return (f"The exploratory session explores a frontend job's candidate; job {job['id']} is a "
                f"{job['role']} job")
    depth = state["bundle"].get("planning", {}).get("depth")
    if depth not in DEPTHS:
        return ("The exploratory session runs at focused and full depth; this run is at "
                + (f"{depth} depth" if depth else "no planning depth"))
    return None


def target(runner, state):
    """(job, attempt, tested candidate) for the session, or a refusal saying why not."""
    attempt = state["active"]
    require(attempt and "review" in attempt,
            "No tested candidate: the exploratory session runs once a frontend job's candidate passes its "
            "gates (submit it, or use run --explore)")
    contract = runner.frozen_contract(state)
    job = next(item for item in contract["jobs"] if item["id"] == attempt["job"])
    reason = why_not(state, job)
    require(not reason, reason)
    candidate, _ = runner.reviewed_candidate(state, attempt)
    return job, attempt, candidate


def text(value, name, limit=TEXT_LIMIT):
    require(isinstance(value, str) and value.strip(), f"{FINDINGS}: {name} must be non-empty text")
    require(len(value) <= limit, f"{FINDINGS}: {name} is longer than {limit} characters")
    return value


def validate(data, scripts):
    """The checked report; ``scripts`` are the proposed check scripts QA wrote ({check ID: path})."""
    from .review_gate import CATEGORIES
    require(isinstance(data, dict), f"{FINDINGS} must hold a JSON object")
    require(set(data) <= {"summary", "probes", "findings"}, f"{FINDINGS}: unknown keys "
            + ", ".join(sorted(set(data) - {"summary", "probes", "findings"})))
    text(data.get("summary"), "summary")
    probes = data.get("probes")
    require(isinstance(probes, dict), f"{FINDINGS}: probes must be an object with an account of each probe")
    missing = [name for name in PROBES if name not in probes]
    require(not missing, f"{FINDINGS}: say what was tried for every probe; missing: " + ", ".join(missing))
    require(set(probes) <= set(PROBES), f"{FINDINGS}: unknown probes: " + ", ".join(sorted(set(probes) - set(PROBES))))
    for name in PROBES:
        text(probes[name], f"probes.{name}")
    findings = data.get("findings")
    require(isinstance(findings, list) and len(findings) <= FINDING_LIMIT,
            f"{FINDINGS}: findings must be a list of at most {FINDING_LIMIT}")
    named = set()
    for number, item in enumerate(findings, 1):
        where = f"finding {number}"
        require(isinstance(item, dict), f"{FINDINGS}: {where} must be an object")
        unknown = set(item) - set(REQUIRED) - set(OPTIONAL)
        require(not unknown, f"{FINDINGS}: {where} has unknown keys: " + ", ".join(sorted(unknown)))
        require(item.get("severity") in SEVERITIES, f"{FINDINGS}: {where} severity must be blocking or advisory")
        require(item.get("category") in CATEGORIES,
                f"{FINDINGS}: {where} category must be one of " + ", ".join(CATEGORIES))
        require(item.get("probe") in (*PROBES, "other"), f"{FINDINGS}: {where} probe must be one of "
                + ", ".join((*PROBES, "other")))
        for name in ("path", "scenario", "evidence", "recommendation", "repro"):
            text(item.get(name), f"{where} {name}")
        if "consequence" in item:
            text(item["consequence"], f"{where} consequence")
        if "proposed_check" in item:
            check = item["proposed_check"]
            require(isinstance(check, str) and CHECK_ID.fullmatch(check),
                    f"{FINDINGS}: {where} proposed_check must be a check ID (a letter, then letters, digits, _ or -)")
            require(check in scripts, f"{FINDINGS}: {where} proposes {check}, but report/{PROPOSED}/{check}.py "
                                      "is missing")
            require(check not in named, f"{FINDINGS}: {check} is proposed twice")
            named.add(check)
    return data


def read_report(folder):
    """(markdown, report data, {check ID: script path}) from QA's report/ folder, checked."""
    manifest = inventory(folder)  # refuses links and special files
    files = {path for path, (digest, _) in manifest.items() if digest is not None}
    for name in (REPORT, FINDINGS):
        require(name in files, f"QA wrote no report/{name}")
    for name in (REPORT, FINDINGS):
        require((folder / name).stat().st_size <= REPORT_LIMIT, f"report/{name} is larger than {REPORT_LIMIT} bytes")
    markdown = (folder / REPORT).read_text(encoding="utf-8")
    require(markdown.strip(), f"report/{REPORT} is empty")
    try:
        data = json.loads((folder / FINDINGS).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise BuilderError(f"report/{FINDINGS} is not valid JSON: {exc}") from exc
    scripts = {}
    for path in files:
        parts = PurePosixPath(path).parts
        if len(parts) == 2 and parts[0] == PROPOSED and parts[1].endswith(".py"):
            scripts[parts[1][:-3]] = folder / path
    data = validate(data, scripts)
    used = {item["proposed_check"] for item in data["findings"] if "proposed_check" in item}
    for check in used:
        require(scripts[check].stat().st_size <= SCRIPT_LIMIT,
                f"report/{PROPOSED}/{check}.py is larger than {SCRIPT_LIMIT} bytes")
    return markdown, data, {check: scripts[check] for check in used}


def explore(runner, brain, launcher, trust_host, timeout=TIMEOUT, state=None):
    """One exploratory session on the active tested candidate. Run under the runner's lock.
    Returns what was found, where the report is, and the add-check command for each proposed check."""
    from .brains import launch, tools
    from .decisions import record_exploratory
    from .qa import boundary
    from .runner import copy_file, copy_tree, read_tail, stamp
    from .sandbox import Sandbox
    from .team import profile, render
    require(type(timeout) is int and 1 <= timeout <= 1800, "--timeout must be 1 to 1800 seconds")
    state = state if state is not None else runner.state()
    job, attempt, candidate = target(runner, state)
    session = uuid4().hex
    folder = runner.attempt_dir(attempt) / "exploratory" / session
    folder.mkdir(parents=True)
    sandboxed = isinstance(launcher, Sandbox)
    shell = "shell" in tools(brain, "worker", None, sandboxed)
    log = folder / "qa.log"
    with tempfile.TemporaryDirectory(prefix="explore-", dir=folder) as temporary:
        work = Path(temporary) / "workspace"
        work.mkdir()
        copy_tree(candidate, work / "app")
        copy_tree(runner.approval(state) / "plan", work / "plan")
        (work / "report").mkdir()
        packs = runner.knowledge_copy(state, Path(temporary) / "knowledge")
        from .review_gate import CATEGORIES
        prompt = render(profile("qa")) + "\n\n" + TASK.format(
            job=job["id"], tools=SHELL if shell else NO_SHELL, report=REPORT, findings=FINDINGS,
            proposed=PROPOSED, categories=", ".join(CATEGORIES))
        # QA writes its report, so it runs as a worker (shell only in a sandbox), in a copy it may change.
        code = launch(brain, "worker", launcher, trust_host, work=work, input_text=prompt, log=log, timeout=timeout,
                      ledger={"run": runner.root, "job": job["id"], "role": "qa"}, knowledge=packs)
        said = brain.adapter.summary(read_tail(log, limit=REPORT_LIMIT)) if log.is_file() else ""
        require(code == 0, f"QA brain {brain.name} exited {code}\n{said[-3500:]}")
        markdown, data, scripts = read_report(work / "report")
        copy_file(work / "report" / REPORT, folder / REPORT)
        copy_file(work / "report" / FINDINGS, folder / FINDINGS)
        kept = {}
        for check, path in scripts.items():
            (folder / PROPOSED).mkdir(exist_ok=True)
            kept[check] = folder / PROPOSED / f"{check}.py"
            copy_file(path, kept[check])
    # The session worked on a copy: the tested candidate and its baseline must be as they were.
    runner.reviewed_candidate(state, attempt)
    require(fingerprint(inventory(candidate)) == attempt["review"]["candidate_digest"],
            "Tested candidate changed during the exploratory session")
    ids = record_exploratory(runner.root, attempt, session, data["findings"])
    by_check = {item["proposed_check"]: finding_id for item, finding_id in zip(data["findings"], ids)
                if "proposed_check" in item}
    relative = lambda path: str(path.relative_to(runner.root))
    proposals = [{"check": check, "finding": by_check[check], "script": relative(path),
                  "command": (f"vesper --project {runner.root} add-check --id {check} --script {path} "
                              f"--jobs <unfinished jobs> --reason \"{by_check[check]}: exploratory session bug\"")}
                 for check, path in kept.items()]
    record = {"session": session, "at": stamp(), "brain": brain.name, "boundary": boundary(launcher), "shell": shell,
              "report": relative(folder / REPORT), "report_digest": sha256(markdown.encode("utf-8")).hexdigest(),
              "summary": data["summary"], "probes": data["probes"], "findings": ids,
              "proposed_checks": {item["check"]: item["script"] for item in proposals}}
    attempt.setdefault("exploratory", []).append(record)
    runner.save(state)
    return {"job": job["id"], "attempt": attempt["id"], "session": session, "report": record["report"],
            "boundary": record["boundary"], "shell": shell, "summary": data["summary"],
            "findings": [{"id": finding_id, **{key: item[key] for key in ("severity", "category", "probe", "path")}}
                         for item, finding_id in zip(data["findings"], ids)],
            "proposed_checks": proposals,
            "next": ("Findings are noted in the backlog (status lists them); none holds the candidate. To make a "
                     "bug that matters a check, the owner runs the add-check command shown, after this "
                     "candidate's review.")}


__all__ = ["PROBES", "explore", "why_not"]
