"""Advisory backlog and decision gate (P2-T7): reviewers find and explain, the owner decides.

Every finding of a plan critique, a job review or an exploratory QA session (P3-T5) is listed in
`<run>/.builder/backlog.json` with an ID (F1, F2, ...) and shown in `status`. A finding's status says
what happens to it:

    noted              an advisory the owner can read; nothing waits for it
    returned           a blocker the runner sent back to the worker automatically (attempts remained)
    awaiting_decision  the owner decides: a plan-critique blocker; a security or data advisory (also
                       on a rejected candidate); the blockers of a job whose attempts are used up; an
                       exploratory blocker or security or data finding, which joins the candidate's
                       decisions when its review finishes (P3-T5; never returned without the owner)
    fix                the owner sent the plan or the job back for correction
    accepted           the owner accepted it as a risk, with a reason (a protected action), or the
                       owner's confirmed plan approval accepted it from the plan sheet
    dismissed          the owner dismissed a job finding as not a defect, with a reason (a protected
                       action; P3-T4): the candidate goes on as with an accepted risk, and reviewer
                       calibration counts the finding as a false alarm
    superseded         the plan it was about was revised before a decision

The backlog is a view for people. What the gates trust is digest-bound: a plan finding's text comes
from the critique report (part of the approval digest), and a job finding's from the review kept in
the run's state, where each attempt also records which findings wait and the owner's decisions. An
acceptance counts only when its digest, recomputed from that text, matches a human confirmation on
record. `decide FINDING_ID --fix` sends the plan back, returns the job for correction (counts as a
retry) or grants a job out of attempts one more; `decide FINDING_ID --accept-risk --reason "..."`
is human-only: the confirmer shows the risk sheet first. `decide FINDING_ID --dismiss --reason "..."`
is the same for a job finding the owner judges wrong. A job-review blocker without a repro is a
suspected advisory (P3-T4) and waits for the owner too.
"""
from pathlib import Path

from .contracts import fingerprint, read_json, require
from .review_gate import DECISION_CATEGORIES

FILE = "backlog.json"
RISK = "Accepted risk: owner must confirm"
TEXT = ("scenario", "consequence", "evidence", "recommendation", "repro")
FIELDS = ("severity", "category", "path", *TEXT, "suspected")


def store(root):
    return Path(root) / ".builder" / FILE


def load(root):
    path = store(root)
    if not path.is_file():
        return {"items": []}
    data = read_json(path)
    require(isinstance(data, dict) and isinstance(data.get("items"), list), f"Invalid backlog in {path}")
    return data


def save(root, data):
    from .runner import atomic_json
    path = store(root)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    atomic_json(path, data)


def awaiting(root):
    return [item["id"] for item in load(root)["items"] if item["status"] == "awaiting_decision"]


def owner_decides(finding):
    """A blocker, a security or data advisory, or a risk the critic says only the owner can accept."""
    return (finding["severity"] == "blocking" or finding.get("category") in DECISION_CATEGORIES
            or str(finding.get("recommendation", "")).startswith(RISK) or bool(finding.get("suspected")))


def sync(data, key, finding, status, **where):
    """The item for `key`, its finding text (re)copied from the digest-bound record; the status and
    decision of an existing item are kept."""
    found = next((item for item in data["items"] if item["key"] == key), None)
    text = {name: finding[name] for name in FIELDS if name in finding}
    if found:
        for name in FIELDS:
            found.pop(name, None)
        found.update(where, **text)
        return found
    item = {"id": f"F{len(data['items']) + 1}", "key": key, **where, **text, "status": status, "decision": None}
    data["items"].append(item)
    return item


def mark(root, ids, status, decisions=None):
    data = load(root)
    for item in data["items"]:
        if item["id"] in ids:
            item["status"] = status
            if decisions is not None:
                item["decision"] = decisions.get(item["id"])
    save(root, data)


# Acceptances ---------------------------------------------------------------------------------------

def subject(root, finding_id):
    return f"{root}#{finding_id}"


def acceptance_digest(item, accepts, reason):
    from .approvals import text_digest
    return text_digest({"finding": {key: item[key] for key in ("id", "source", *FIELDS) if key in item},
                        "accepts": accepts, "reason": reason,
                        "where": item.get("packet_digest") or item.get("attempt")})


def confirmed(root, item, decision):
    """An acceptance counts only when its digest, recomputed from the digest-bound finding, matches
    the human confirmation recorded for it."""
    from .approvals import last, run_store
    if not decision or decision.get("kind") != "accept-risk":
        return False
    digest = acceptance_digest(item, decision.get("accepts"), decision.get("reason"))
    record = last(run_store(root), "accept-risk", subject(root, item["id"]))
    return decision.get("digest") == digest and bool(record) and record.get("digest") == digest


def accept_risk(root, item, reason, accepts):
    """The protected part: the human confirms on the risk sheet. Returns the decision and a
    callable that records the confirmation once the decision is saved."""
    from .approvals import confirm, keep, run_store
    from .sheets import risk_sheet
    digest = acceptance_digest(item, accepts, reason)
    store_path = run_store(root)
    sheet = risk_sheet(store_path, subject(root, item["id"]), item, accepts, reason, digest)
    confirmation = confirm("accept-risk", subject(root, item["id"]), digest, sheet)
    decision = {"kind": "accept-risk", "by": "owner decision", "reason": reason, "accepts": accepts,
                "digest": digest, "confirmer": confirmation["confirmer"], "at": confirmation["at"]}
    return decision, lambda: keep(store_path, confirmation)


# Plan critique -------------------------------------------------------------------------------------

def record_critique(root, critique):
    """List a plan critique's findings (text from the critique report); findings of earlier packets
    that still waited are superseded. Returns the items in report order."""
    data = load(root)
    digest = critique["packet_digest"]
    for item in data["items"]:
        if item["source"] == "plan-critique" and item["packet_digest"] != digest \
                and item["status"] == "awaiting_decision":
            item["status"] = "superseded"
    items = [sync(data, f"plan:{digest}:{index}", finding,
                  "awaiting_decision" if owner_decides(finding) else "noted",
                  source="plan-critique", packet_digest=digest)
             for index, finding in enumerate(critique["report"]["findings"])]
    save(root, data)
    return items


def plan_findings(root, critique):
    """(finding from the report, its item) for each finding of this critique."""
    return list(zip(critique["report"]["findings"], record_critique(root, critique)))


def undecided_plan_blockers(root, critique):
    """Why `approve` must wait: each finding sent back, and each blocker without a confirmed acceptance."""
    reasons = []
    for finding, item in plan_findings(root, critique):
        if item["status"] == "fix":
            reasons.append(f"{item['id']} was sent back: revise the plan and run review-plan again")
        elif finding["severity"] == "blocking" and not confirmed(root, item, item.get("decision")):
            reasons.append(f"{item['id']} awaits your decision: decide {item['id']} --fix, or "
                           f"--accept-risk --reason \"...\"")
    return reasons


def accepted_plan_blockers(root, critique):
    return [item for finding, item in plan_findings(root, critique)
            if finding["severity"] == "blocking" and confirmed(root, item, item.get("decision"))]


def accepted_by_approval(root, critique, digest):
    """The plan sheet listed these; the owner's confirmed approval accepts them. Returns every
    accepted plan finding for the state."""
    from .runner import stamp
    pairs = plan_findings(root, critique)
    data = load(root)
    by_id = {item["id"]: item for item in data["items"]}
    accepted = []
    for finding, listed in pairs:
        item = by_id[listed["id"]]
        if confirmed(root, item, item.get("decision")):
            accepted.append({"id": item["id"], "by": "owner decision", "reason": item["decision"]["reason"]})
        elif finding["severity"] == "advisory" and owner_decides(finding):
            item["status"] = "accepted"
            item["decision"] = {"kind": "accept-risk", "by": "plan approval", "digest": digest, "at": stamp()}
            accepted.append({"id": item["id"], "by": "plan approval", "reason": None})
    save(root, data)
    return accepted


def decide_plan(runner, finding_id, fix, reason):
    from .contracts import review_bundle
    from .runner import stamp
    require(not runner.state_file.exists(), "The plan is already approved")
    listed = next((item for item in load(runner.root)["items"] if item["id"] == finding_id), None)
    require(listed and listed["source"] == "plan-critique", f"Unknown finding {finding_id}; `status` lists the backlog")
    _, bundle = review_bundle(runner.root)
    critique = bundle.get("plan_critique")
    require(critique and critique["packet_digest"] == listed["packet_digest"],
            f"The plan has changed since {finding_id} was found; run review-plan for the revised plan")
    finding, item = next(pair for pair in plan_findings(runner.root, critique) if pair[1]["id"] == finding_id)
    require(item["status"] == "awaiting_decision" and owner_decides(finding),
            f"{finding_id} does not await a decision (it is {item['status']})")
    if fix:
        mark(runner.root, {finding_id}, "fix", {finding_id: {"kind": "fix", "reason": reason, "at": stamp()}})
    else:
        what = "blocker" if finding["severity"] == "blocking" else "finding"
        accepts = (f"The plan can be approved with this {what} unfixed. Approving the plan still needs your "
                   "confirmation on the plan sheet, which lists this acceptance.")
        decision, keep = accept_risk(runner.root, item, reason, accepts)
        mark(runner.root, {finding_id}, "accepted", {finding_id: decision})
        keep()
    return runner.status()


# Job reviews ---------------------------------------------------------------------------------------

def record_review(root, attempt, findings, *, rejected, exhausted):
    """List a job review's findings; return (every finding's ID in report order, the IDs that wait
    for the owner). The caller keeps both on the attempt in the run's state."""
    data = load(root)
    ids, waiting = [], []
    for index, finding in enumerate(findings):
        if not owner_decides(finding):
            status = "noted"
        elif finding["severity"] == "blocking" and rejected and not exhausted:
            status = "returned"
        else:
            status = "awaiting_decision"
        item = sync(data, f"review:{attempt['id']}:{index}", finding, status, source="job-review",
                    job=attempt["job"], attempt=attempt["id"])
        ids.append(item["id"])
        if status == "awaiting_decision":
            waiting.append(item["id"])
    save(root, data)
    return ids, waiting


# Exploratory sessions ------------------------------------------------------------------------------

def record_exploratory(root, attempt, session, findings):
    """List an exploratory QA session's findings (P3-T5) with their category, severity, probe and
    repro; return (their IDs in report order, the IDs the owner decides). P2-T7's rule applies: a
    blocker or a security or data finding awaits the owner. The attempt in the run's state keeps both."""
    data = load(root)
    ids, waiting = [], []
    for index, finding in enumerate(findings):
        decides = owner_decides(finding)
        item = sync(data, f"explore:{session}:{index}", finding, "awaiting_decision" if decides else "noted",
                    source="exploratory", job=attempt["job"], attempt=attempt["id"], session=session,
                    probe=finding["probe"],
                    **({"proposed_check": finding["proposed_check"]} if "proposed_check" in finding else {}))
        ids.append(item["id"])
        if decides:
            waiting.append(item["id"])
    save(root, data)
    return ids, waiting


def exploratory_waiting(attempt):
    """The exploratory findings on this attempt that the owner decides (from the run's state)."""
    return [name for session in attempt.get("exploratory", []) for name in session.get("awaiting", [])]


def open_decisions(attempt):
    """The findings on this attempt that still wait for the owner (from the run's state)."""
    decided = attempt.get("decisions", {})
    return [name for name in attempt.get("awaiting_decision", []) if name not in decided]


def job_item(attempt, finding_id):
    """A job finding as the state recorded it: from the review, or from an exploratory session (P3-T5)."""
    if finding_id in attempt.get("finding_ids", []):
        finding, source = attempt["review"]["findings"][attempt["finding_ids"].index(finding_id)], "job-review"
    else:
        finding = next(session["items"][session["findings"].index(finding_id)]
                       for session in attempt.get("exploratory", []) if finding_id in session["findings"])
        source = "exploratory"
    return {"id": finding_id, "source": source, "job": attempt["job"], "attempt": attempt["id"],
            **{name: finding[name] for name in FIELDS if name in finding}}


def all_accepted(root, attempt):
    """Every finding the attempt waited on has a confirmed owner acceptance."""
    decisions = attempt.get("decisions", {})
    return all(confirmed(root, job_item(attempt, name), decisions.get(name))
               for name in attempt.get("awaiting_decision", []))


def sent_back(attempt, ids):
    return " ".join(f"{name} ({item['path']}): {item.get('evidence', '')} {item['recommendation']}"
                    for name in ids for item in [job_item(attempt, name)])


def decide_job(runner, state, attempt, finding_id, fix, reason, dismiss=False):
    from .runner import stamp
    contract = runner.frozen_contract(state)
    job = next(job for job in contract["jobs"] if job["id"] == attempt["job"])
    pending = state["active"] is attempt
    if not pending:
        previous = runner.attempts_for(state, job)
        require(not state["active"] and previous and previous[-1] is attempt and job["id"] not in state["completed"],
                f"{finding_id}'s candidate no longer awaits a decision")
    exhausted = not pending and len(runner.attempts_for(state, job)) >= runner.budget_for(state, job)
    waiting = open_decisions(attempt)
    item = job_item(attempt, finding_id)
    decisions = attempt.setdefault("decisions", {})
    if fix:
        # One fix sends the candidate back with everything that still waited on it.
        for name in waiting:
            decisions[name] = {"kind": "fix", "reason": reason, "at": stamp(),
                               **({} if name == finding_id else {"with": finding_id})}
        note = f"The owner sent back for correction: {sent_back(attempt, waiting)}"
        if pending:
            runner.finish(state, "rejected", note, "review")
        else:
            attempt["reason"] = (attempt.get("reason", "") + "\n" + note).strip()
            runner.save(state)
        if len(runner.attempts_for(state, job)) >= runner.budget_for(state, job):
            state.setdefault("retry_grants", []).append(
                {"job": job["id"], "reason": f"Owner decision: fix {finding_id}", "at": stamp()})
            runner.save(state)
        mark(runner.root, set(waiting), "fix", decisions)
        return runner.status()
    what = "blocker" if item["severity"] == "blocking" else "finding"
    if pending:
        accepts = f"Job {job['id']}'s candidate is accepted with this {what} unfixed"
    elif exhausted:
        accepts = f"Job {job['id']}'s last candidate, which the reviewer rejected, is accepted with this {what} unfixed"
    else:
        accepts = (f"Job {job['id']} goes on to its next attempt with this {what} accepted as a risk; the "
                   "rejected candidate itself is not accepted")
    others = [name for name in waiting if name != finding_id]
    if others:
        accepts += f", once you have also decided {', '.join(others)}"
    if dismiss:
        # The text the owner confirms says it is a dismissal, so the digest binds that too.
        accepts = f"You dismiss this {what} as not a defect. " + accepts
    decision, keep = accept_risk(runner.root, item, reason, accepts + ".")
    if dismiss:
        decision["dismissed"] = True
    decisions[finding_id] = decision
    runner.save(state)
    mark(runner.root, {finding_id}, "dismissed" if dismiss else "accepted", decisions)
    keep()
    if dismiss and item["source"] == "job-review":
        # Calibration measures the reviewer; an exploratory finding is QA's (P3-T5).
        from . import calibration
        found = calibration.outcomes(calibration.rows(runner.root)).get(finding_id)
        calibration.append(runner.root, [{**{key: value for key, value in (found or {}).items() if key != "at"},
                                          "finding": finding_id, "job": attempt["job"], "attempt": attempt["id"],
                                          "outcome": "dismissed"}])
    if not others and (pending or exhausted):
        require(all_accepted(runner.root, attempt), "An accepted finding has no matching human confirmation on record")
        accepted = list(attempt["awaiting_decision"])
        if pending:
            runner.accept_decided(state, accepted)
        else:
            runner.accept_rejected(state, job, attempt, accepted)
    return runner.status()


# Deciding ------------------------------------------------------------------------------------------

def decide(runner, finding_id, *, fix=False, accept=False, dismiss=False, reason=None):
    """The owner's decision on one finding. Run under the runner's lock."""
    require(fix + accept + dismiss == 1, "Choose one decision: --fix, --accept-risk or --dismiss")
    reason = reason.strip() if isinstance(reason, str) else ""
    require(fix or reason, ("--dismiss needs --reason: say why it is not a defect" if dismiss
                            else "--accept-risk needs --reason: say why the risk is acceptable"))
    if runner.state_file.exists():
        state = runner.state()
        attempts = ([state["active"]] if state["active"] else []) + state["attempts"]
        attempt = next((item for item in attempts if finding_id in open_decisions(item)), None)
        if attempt is None:
            listed = next((item for item in load(runner.root)["items"] if item["id"] == finding_id), None)
            require(listed, f"Unknown finding {finding_id}; `status` lists the backlog")
            require(not (listed["source"] == "exploratory" and listed["status"] == "awaiting_decision"),
                    f"{finding_id} joins the candidate's decisions when its review finishes: run review-candidate "
                    "first, then decide it")
            raise_not_waiting(finding_id, listed)
        return decide_job(runner, state, attempt, finding_id, fix, reason, dismiss)
    require(not dismiss, "--dismiss is for job review findings; decide a plan critique finding with --fix or "
                         "--accept-risk")
    return decide_plan(runner, finding_id, fix, reason)


def raise_not_waiting(finding_id, listed):
    require(False, f"{finding_id} does not await a decision (it is {listed['status']})")


def describe(item):
    """Where a finding came from, in plain words."""
    if item["source"] == "plan-critique":
        return "the independent plan critique"
    if item["source"] == "exploratory":
        return f"the exploratory QA session on job {item['job']}"
    return f"the independent review of job {item['job']}"
