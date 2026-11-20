"""Advisory backlog and decision gate (P2-T7): reviewers find and explain, the owner decides.

Every finding of a plan critique or a job review is kept in `<run>/.builder/backlog.json` with an
ID (F1, F2, ...) and shown in `status`. A finding's status says what happens to it:

    noted              an advisory the owner can read; nothing waits for it
    returned           the runner sent the job back to its worker automatically (attempts remained)
    awaiting_decision  the owner decides: a plan-critique blocker; a security or data advisory; the
                       blockers of a job whose attempts are used up
    fix                the owner sent the plan or the job back for correction
    accepted           the owner accepted it as a risk, with a reason (a protected action), or the
                       owner's confirmed plan approval accepted it from the plan sheet
    superseded         the plan or candidate it was about was replaced before a decision

`decide FINDING_ID --fix` sends the plan back, returns the job for correction (counts as a retry),
or grants a job out of attempts one more. `decide FINDING_ID --accept-risk --reason "..."` is
human-only: the confirmer shows the risk sheet first, and the acceptance only counts with that
confirmation on record. The independent review still runs and every finding is kept.
"""
from pathlib import Path

from .contracts import fingerprint, read_json, require
from .review_gate import DECISION_CATEGORIES

FILE = "backlog.json"
RISK = "Accepted risk: owner must confirm"
TEXT = ("scenario", "consequence", "evidence", "recommendation")


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
            or str(finding.get("recommendation", "")).startswith(RISK))


def add(data, key, finding, status, **where):
    """Add a finding once (by key); returns its item."""
    found = next((item for item in data["items"] if item["key"] == key), None)
    if found:
        return found
    item = {"id": f"F{len(data['items']) + 1}", "key": key, **where,
            "severity": finding["severity"], "category": finding.get("category", "other"),
            "path": finding.get("path"), **{name: finding[name] for name in TEXT if name in finding},
            "status": status, "decision": None}
    data["items"].append(item)
    return item


# Recording findings ------------------------------------------------------------------------------

def record_critique(root, critique):
    """Keep a plan critique's findings; findings of earlier packets that still waited are superseded."""
    data = load(root)
    digest = critique["packet_digest"]
    for item in data["items"]:
        if item["source"] == "plan-critique" and item["packet_digest"] != digest \
                and item["status"] == "awaiting_decision":
            item["status"] = "superseded"
    for index, finding in enumerate(critique["report"]["findings"]):
        add(data, f"plan:{digest}:{index}", finding,
            "awaiting_decision" if owner_decides(finding) else "noted",
            source="plan-critique", packet_digest=digest)
    save(root, data)
    return data


def record_review(root, attempt, findings, *, rejected, exhausted):
    """Keep a job review's findings; return the IDs that now wait for the owner."""
    data = load(root)
    waiting = []
    for index, finding in enumerate(findings):
        if not owner_decides(finding):
            status = "noted"
        elif rejected and not exhausted:
            status = "returned"
        else:
            status = "awaiting_decision"
        item = add(data, f"review:{attempt['id']}:{index}", finding, status, source="job-review",
                   job=attempt["job"], attempt=attempt["id"])
        if item["status"] == "awaiting_decision":
            waiting.append(item["id"])
    save(root, data)
    return waiting


def supersede_job(root, job):
    """A new attempt of `job` replaces whatever earlier candidate still waited for a decision."""
    data = load(root)
    changed = False
    for item in data["items"]:
        if item.get("job") == job and item["status"] == "awaiting_decision":
            item["status"], changed = "superseded", True
    if changed:
        save(root, data)


def plan_items(root, packet_digest):
    return [item for item in load(root)["items"]
            if item["source"] == "plan-critique" and item["packet_digest"] == packet_digest]


def confirmed(root, item):
    """An owner acceptance counts only with the human confirmation that recorded it."""
    from .approvals import last, run_store
    decision = item.get("decision") or {}
    record = last(run_store(root), "accept-risk", subject(root, item))
    return item["status"] == "accepted" and bool(record) and record["digest"] == decision.get("digest")


def subject(root, item):
    return f"{root}#{item['id']}"


# Plan approval ---------------------------------------------------------------------------------------

def undecided_plan_blockers(root, critique):
    """Why `approve` must wait: each plan-critique blocker the owner has not accepted."""
    record_critique(root, critique)
    reasons = []
    for item in plan_items(root, critique["packet_digest"]):
        if item["status"] == "fix":
            reasons.append(f"{item['id']} was sent back: revise the plan and run review-plan again")
        elif item["severity"] == "blocking" and not confirmed(root, item):
            reasons.append(f"{item['id']} awaits your decision: decide {item['id']} --fix, or "
                           f"--accept-risk --reason \"...\"")
    return reasons


def accepted_by_approval(root, critique, digest):
    """The plan sheet listed these; the owner's confirmed approval accepts them. Returns every
    accepted plan finding for the state."""
    from .runner import stamp
    data = load(root)
    accepted = []
    for item in data["items"]:
        if item["source"] != "plan-critique" or item["packet_digest"] != critique["packet_digest"]:
            continue
        if item["status"] == "awaiting_decision" and item["severity"] == "advisory":
            item["status"] = "accepted"
            item["decision"] = {"kind": "accept-risk", "by": "plan approval", "digest": digest, "at": stamp()}
        if item["status"] == "accepted":
            accepted.append({"id": item["id"], "by": item["decision"].get("by", "owner decision"),
                             "reason": item["decision"].get("reason")})
    save(root, data)
    return accepted


# Deciding ----------------------------------------------------------------------------------------------

def decide(runner, finding_id, *, fix=False, accept=False, reason=None):
    """The owner's decision on one finding. Run under the runner's lock."""
    require(fix != accept, "Choose one decision: --fix or --accept-risk")
    reason = reason.strip() if isinstance(reason, str) else ""
    require(fix or reason, "--accept-risk needs --reason: say why the risk is acceptable")
    item = next((item for item in load(runner.root)["items"] if item["id"] == finding_id), None)
    require(item, f"Unknown finding {finding_id}; `status` lists the backlog")
    require(item["status"] == "awaiting_decision",
            f"{finding_id} does not await a decision (it is {item['status']})")
    if item["source"] == "plan-critique":
        return decide_plan(runner, item, fix, reason)
    return decide_job(runner, item, fix, reason)


def mark(root, ids, status, decision=None):
    data = load(root)
    for item in data["items"]:
        if item["id"] in ids:
            item["status"] = status
            if decision is not None:
                item["decision"] = decision
    save(root, data)


def accept_risk(runner, item, reason, accepts):
    """The protected part: the human confirms on the risk sheet; returns the decision to record."""
    from .approvals import confirm, keep, run_store, text_digest
    from .sheets import risk_sheet
    finding = {key: item[key] for key in ("id", "source", "severity", "category", "path", *TEXT) if key in item}
    digest = text_digest({"finding": finding, "accepts": accepts, "reason": reason,
                          "where": item.get("packet_digest") or item.get("attempt")})
    store_path = run_store(runner.root)
    sheet = risk_sheet(store_path, subject(runner.root, item), item, accepts, reason, digest)
    confirmation = confirm("accept-risk", subject(runner.root, item), digest, sheet)
    decision = {"kind": "accept-risk", "by": "owner decision", "reason": reason, "digest": digest,
                "confirmer": confirmation["confirmer"], "at": confirmation["at"]}
    return decision, lambda: keep(store_path, confirmation)


def decide_plan(runner, item, fix, reason):
    from .contracts import review_bundle
    from .runner import stamp
    require(not runner.state_file.exists(), "The plan is already approved")
    _, bundle = review_bundle(runner.root, include_critique=False)
    require(fingerprint(bundle) == item["packet_digest"],
            f"The plan has changed since {item['id']} was found; run review-plan for the revised plan")
    if fix:
        mark(runner.root, {item["id"]}, "fix", {"kind": "fix", "reason": reason, "at": stamp()})
    else:
        what = "blocker" if item["severity"] == "blocking" else "finding"
        accepts = (f"The plan can be approved with this {what} unfixed. Approving the plan still needs your "
                   "confirmation on the plan sheet, which lists this acceptance.")
        decision, keep = accept_risk(runner, item, reason, accepts)
        mark(runner.root, {item["id"]}, "accepted", decision)
        keep()
    return runner.status()


def decide_job(runner, item, fix, reason):
    from .runner import stamp
    state = runner.state()
    contract = runner.frozen_contract(state)
    job = next(job for job in contract["jobs"] if job["id"] == item["job"])
    active = state["active"]
    pending = active is not None and active["id"] == item["attempt"] and item["id"] in active.get(
        "awaiting_decision", [])
    if pending:
        attempt = active
    else:
        previous = runner.attempts_for(state, job)
        attempt = previous[-1] if previous else None
        require(attempt and attempt["id"] == item["attempt"] and job["id"] not in state["completed"]
                and attempt.get("failure_kind") == "review" and not active
                and len(previous) >= runner.budget_for(state, job),
                f"{item['id']}'s candidate no longer awaits a decision")
    waiting = [other["id"] for other in load(runner.root)["items"]
               if other.get("attempt") == attempt["id"] and other["status"] == "awaiting_decision"]
    if fix:
        mark(runner.root, {item["id"]}, "fix", {"kind": "fix", "reason": reason, "at": stamp()})
        mark(runner.root, set(waiting) - {item["id"]}, "superseded")
        if pending:
            runner.finish(state, "rejected", f"The owner sent {item['id']} back for correction. "
                          f"{item.get('path')}: {item.get('evidence')} {item['recommendation']}", "review")
        if len(runner.attempts_for(state, job)) >= runner.budget_for(state, job):
            state.setdefault("retry_grants", []).append(
                {"job": job["id"], "reason": f"Owner decision: fix {item['id']}", "at": stamp()})
            runner.save(state)
        return runner.status()
    what = "blocker" if item["severity"] == "blocking" else "finding"
    if pending:
        accepts = f"Job {job['id']}'s candidate is accepted with this {what} unfixed"
    else:
        accepts = f"Job {job['id']}'s last candidate, which the reviewer rejected, is accepted with this {what} unfixed"
    others = [name for name in waiting if name != item["id"]]
    if others:
        accepts += f", once you have also decided {', '.join(others)}"
    decision, keep = accept_risk(runner, item, reason, accepts + ".")
    mark(runner.root, {item["id"]}, "accepted", decision)
    keep()
    if not others:
        decided = [other for other in load(runner.root)["items"]
                   if other.get("attempt") == attempt["id"] and other["status"] == "accepted"]
        require(all(confirmed(runner.root, other) for other in decided),
                "An accepted finding has no matching human confirmation on record")
        accepted = [other["id"] for other in decided]
        if pending:
            runner.accept_decided(state, accepted)
        else:
            runner.accept_rejected(state, job, attempt, accepted)
    return runner.status()


def describe(item):
    """Where a finding came from, in plain words."""
    if item["source"] == "plan-critique":
        return "the independent plan critique"
    return f"the independent review of job {item['job']}"
