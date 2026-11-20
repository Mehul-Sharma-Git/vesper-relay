"""Usage ledger and plan-limit estimates (P2-T3).

The owner pays a fixed fee and has session and weekly limits, so estimates are in % of those
limits and wall time, never dollars. Vendors do not publish exact plan numbers, so Vesper
calibrates from the owner's own runs:

- every AI call adds a line to ``<state_home>/usage.jsonl`` (run, job, role, brain, adapter,
  model, effort, start, end, and tokens when the adapter reports them);
- ``vesper usage record --account claude --session 42 --week 13`` adds an observed plan reading;
- each pair of readings with calls between them gives one sample of "% per 1k tokens" for the
  account (and for its model when the calls used one model). A session reset between two
  readings (the % went down) is no sample for that limit.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
import os

from .contracts import BuilderError, require

ACCOUNTS = {"claude-code": "claude", "codex": "chatgpt", "gemini-cli": "gemini"}
LIMITS = ("session", "week")
CONFIDENT = 5  # calibrated runs before an estimate is more than "low" confidence


def ledger_path():
    from .learning import state_home
    return state_home() / "usage.jsonl"


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (path.parent / (path.name + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def append(entry, path=None):
    path = path or ledger_path()
    with locked(path):
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.chmod(path, 0o600)
    return entry


FIELDS = {"call": ("account", "start", "end"), "reading": ("account", "at", "session", "week")}


def well_formed(item):
    fields = FIELDS.get(item.get("kind")) if isinstance(item, dict) else None
    return bool(fields) and all(item.get(name) is not None for name in fields) and (
        item["kind"] != "reading" or all(isinstance(item[name], (int, float)) for name in LIMITS))


def entries(path=None):
    """The ledger's rows; a torn line or a row missing a field is skipped, never fatal."""
    path = path or ledger_path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue  # a torn last line from an interrupted write
        if well_formed(item):
            rows.append(item)
    return rows


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def total_tokens(counts):
    """One number from an adapter's usage block (flat, or per model as Gemini reports it)."""
    if not counts:
        return None
    if isinstance(counts, dict):
        values = [total_tokens(value) if isinstance(value, dict) else value for value in counts.values()]
        numbers = [value for value in values if type(value) is int]
        return sum(numbers) if numbers else None
    return None


def record_call(*, run, job, role, brain, start, end, counts):
    """Called once per AI call (``brains.launch``)."""
    return append({"kind": "call", "run": str(run) if run else None, "job": job, "role": role,
                   "brain": brain.name, "adapter": brain.adapter.name,
                   "account": ACCOUNTS.get(brain.adapter.name, brain.adapter.name),
                   "model": brain.model, "effort": brain.effort, "start": start, "end": end,
                   "tokens": total_tokens(counts), "token_detail": counts or None})


def record_reading(account, session, week):
    known = sorted(set(ACCOUNTS.values()))
    account = account.strip().lower() if isinstance(account, str) else ""
    require(account in known, "Name the account: claude, chatgpt or gemini")
    for name, value in (("session", session), ("week", week)):
        require(isinstance(value, (int, float)) and 0 <= value <= 100,
                f"The {name} reading must be a percentage between 0 and 100")
    return append({"kind": "reading", "account": account, "session": session, "week": week,
                   "at": now()})


# Calibration ---------------------------------------------------------------------------------

def calibrate(rows):
    """{(account, model or None): [{"session": rate or None, "week": rate or None, "tokens": n}]},
    rates in % per 1k tokens, one sample per pair of consecutive readings with calls between."""
    calls = [row for row in rows if row.get("kind") == "call"]
    samples = {}
    for account in sorted({row["account"] for row in rows if row.get("kind") == "reading"}):
        readings = sorted((row for row in rows if row.get("kind") == "reading" and row["account"] == account),
                          key=lambda row: row["at"])
        for before, after in zip(readings, readings[1:]):
            window = [call for call in calls if call.get("account") == account
                      and before["at"] <= call["start"] and call["end"] <= after["at"]]
            if not window or any(not call.get("tokens") for call in window):
                continue  # nothing ran, or some call's tokens are unknown
            tokens = sum(call["tokens"] for call in window)
            sample = {"tokens": tokens}
            for limit in LIMITS:
                rise = after[limit] - before[limit]
                sample[limit] = rise / (tokens / 1000) if rise >= 0 else None  # a reset is no sample
            models = {call.get("model") for call in window}
            keys = [(account, None)] + ([(account, models.pop())] if len(models) == 1 and None not in models else [])
            for key in dict.fromkeys(keys):
                samples.setdefault(key, []).append(sample)
    return samples


def samples_for(calibration, account, model):
    return calibration.get((account, model)) or calibration.get((account, None)) or []


def percent_band(calibration, account, model, tokens, limit):
    """(low, high) % of `limit` for `tokens`, from the lowest and highest calibrated rates."""
    rates = [sample[limit] for sample in samples_for(calibration, account, model) if sample.get(limit) is not None]
    if not rates:
        return None
    return (min(rates) * tokens / 1000, max(rates) * tokens / 1000)


def confidence(samples):
    count = len(samples)
    return "low" if count < CONFIDENT else "medium" if count < 2 * CONFIDENT else "high"


# Estimates -----------------------------------------------------------------------------------

def spread(values):
    return (min(values), max(values)) if values else None


def estimate(contract, bundle, rows, *, brains, reserve=25):
    """Jobs, AI calls, tokens, wall time and % of each account's limits for an approved plan, as
    low–high bands. ``brains`` maps a role to the Brain that will run it."""
    team = "team" in bundle
    planning = bundle.get("planning") or {}
    critique = planning.get("depth") not in (None, "skip") and not bundle.get("plan_critique")
    plan = []  # (role, account, model, low calls, high calls)
    for job in contract["jobs"]:
        attempts = job.get("max_attempts", 2)
        plan.append(("worker", job["role"], brains(job["role"]), 1, attempts))
        if team:
            plan.append(("reviewer", "reviewer", brains("reviewer"), 1, attempts))
    if critique:
        plan.append(("reviewer", "critic", brains("reviewer"), 1, 1))
    calls = [row for row in rows if row.get("kind") == "call"]
    calibration = calibrate(rows)
    durations = {}
    tokens_by_kind = {}
    for call in calls:
        kind = "worker" if call.get("role") not in ("reviewer", "critic", "consult") else "reviewer"
        try:
            seconds = (datetime.fromisoformat(call["end"]) - datetime.fromisoformat(call["start"])).total_seconds()
        except (KeyError, TypeError, ValueError):
            continue
        durations.setdefault(kind, []).append(seconds)
        if call.get("tokens"):
            tokens_by_kind.setdefault((kind, call.get("account")), []).append(call["tokens"])
    result = {"jobs": len(contract["jobs"]), "calls": [sum(item[3] for item in plan), sum(item[4] for item in plan)],
              "reserve_percent": reserve, "accounts": {}}
    seconds = [0.0, 0.0]
    known_time = True
    for kind, _, brain, low, high in plan:
        span = spread(durations.get(kind, []))
        if span is None:
            known_time = False
        else:
            seconds[0] += low * span[0]
            seconds[1] += high * span[1]
        account = ACCOUNTS.get(brain.adapter.name, brain.adapter.name) if brain else "unassigned"
        entry = result["accounts"].setdefault(account, {"calls": [0, 0], "tokens": [0, 0], "models": set(),
                                                        "known_tokens": True})
        entry["calls"][0] += low
        entry["calls"][1] += high
        entry["models"].add(brain.model if brain else None)
        per_call = spread(tokens_by_kind.get((kind, account), []))
        if per_call is None:
            entry["known_tokens"] = False
        else:
            entry["tokens"][0] += low * per_call[0]
            entry["tokens"][1] += high * per_call[1]
    result["wall_time_seconds"] = [round(value) for value in seconds] if known_time else None
    for account, entry in result["accounts"].items():
        models = entry.pop("models")
        model = models.pop() if len(models) == 1 else None
        if not entry.pop("known_tokens"):
            entry["tokens"] = None
        samples = samples_for(calibration, account, model)
        entry["calibrated"] = bool(samples) and entry["tokens"] is not None
        if not entry["calibrated"]:
            continue
        entry["confidence"] = confidence(samples)
        entry["calibrated_runs"] = len(samples)
        for limit in LIMITS:
            low = percent_band(calibration, account, model, entry["tokens"][0], limit)
            high = percent_band(calibration, account, model, entry["tokens"][1], limit)
            if low and high:
                entry[limit] = [round(low[0], 1), round(high[1], 1)]
        if "session" in entry:
            usable = max(1, 100 - reserve)
            entry["sessions_needed"] = max(1, math.ceil(entry["session"][1] / usable))
    return result


def minutes(seconds):
    return f"{max(1, round(seconds / 60))} min"


def render(result):
    """The estimate as plain text, for `estimate` and the plan sheet."""
    low, high = result["calls"]
    lines = [f"Estimate: {result['jobs']} job{'' if result['jobs'] == 1 else 's'}, {low}–{high} AI calls"]
    time = result.get("wall_time_seconds")
    lines.append("  wall time: " + (f"{minutes(time[0])}–{minutes(time[1])}" if time else "unknown (no earlier calls)"))
    for account, entry in sorted(result["accounts"].items()):
        tokens = entry.get("tokens")
        size = f"{tokens[0]:,}–{tokens[1]:,} tokens" if tokens else "tokens unknown"
        if account == "unassigned":
            lines.append(f"  unassigned: {entry['calls'][0]}–{entry['calls'][1]} calls whose role has no brain "
                         "in the config yet ([roles] or --brain), so no plan % is shown")
            continue
        if not entry.get("calibrated"):
            lines.append(f"  {account}: {entry['calls'][0]}–{entry['calls'][1]} calls, {size}; uncalibrated "
                         "(record plan readings with `vesper usage record` before and after runs)")
            continue
        parts = [f"{account}: {size}"]
        if "session" in entry:
            parts.append("session {:.1f}–{:.1f}%".format(*entry["session"]))
        if "week" in entry:
            parts.append("weekly {:.1f}–{:.1f}%".format(*entry["week"]))
        if "sessions_needed" in entry:
            parts.append(f"{entry['sessions_needed']} session{'' if entry['sessions_needed'] == 1 else 's'} "
                         f"needed (keeping a {result['reserve_percent']}% reserve)")
        parts.append(f"confidence {entry['confidence']} ({entry['calibrated_runs']} calibrated runs)")
        lines.append("  " + ", ".join(parts))
    return "\n".join(lines)


def configured_brains():
    """Role → Brain from the config, as `run` would choose them; None when no brain is mapped."""
    from .brains import Selection
    selection = Selection()

    def brain(role):
        try:
            return selection.reviewer(lambda: selection.worker("frontend")) if role == "reviewer" \
                else selection.worker(role)
        except BuilderError:
            return None
    return brain


def for_project(contract, bundle):
    from .brains import load_settings
    try:
        reserve = load_settings().get("limits.reserve_percent", 25)
        return estimate(contract, bundle, entries(), brains=configured_brains(), reserve=reserve)
    except BuilderError as exc:
        return {"error": str(exc)}


# Limit-aware scheduling (P2-T4) ---------------------------------------------------------------

from datetime import timedelta  # noqa: E402

WINDOWS = {"session": timedelta(hours=5), "week": timedelta(days=7)}


def parse_time(text):
    when = datetime.fromisoformat(text)
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def last_reading(rows, account):
    readings = [row for row in rows if row.get("kind") == "reading" and row["account"] == account]
    return max(readings, key=lambda row: row["at"]) if readings else None


def next_reset(rows, account, limit, now):
    """When the `limit` window should next reset: the last recorded reset (a reading lower than
    the one before it) plus whole windows, the first after `now`. None when no reset is recorded."""
    readings = sorted((row for row in rows if row.get("kind") == "reading" and row["account"] == account),
                      key=lambda row: row["at"])
    resets = [later for earlier, later in zip(readings, readings[1:]) if later[limit] < earlier[limit]]
    if not resets:
        return None
    reset = parse_time(resets[-1]["at"])
    while reset <= now:
        reset += WINDOWS[limit]
    return reset


def wait_until(hhmm, *, clock=None, sleep=None):
    """`run --start-after HH:MM`: wait for the next local HH:MM (today, else tomorrow)."""
    import re
    import sys
    import time
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", hhmm or "")
    require(match, "--start-after takes a 24-hour time, for example 07:30")
    clock = clock or (lambda: datetime.now().astimezone())
    sleep = sleep or time.sleep
    now = clock().astimezone()  # HH:MM is local time
    target = now.replace(hour=int(match[1]), minute=int(match[2]), second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    print(f"vesper: waiting until {target:%Y-%m-%d %H:%M} before starting", file=sys.stderr, flush=True)
    while clock() < target:
        sleep(min(300, (target - clock()).total_seconds()))
    return target


def limit_check(contract, bundle, job, rows, *, brains, reserve, now):
    """(pause or None, notes). Pause when the last plan reading, the usage logged since it and the
    high end of this job's estimate would cross 100% minus the reserve, for any account and limit."""
    notes = []
    threshold = 100 - reserve
    result = estimate(dict(contract, jobs=[job]), {**bundle, "plan_critique": True}, rows, brains=brains,
                      reserve=reserve)
    calibration = calibrate(rows)
    model = {}
    for role in (job["role"], *(("reviewer",) if "team" in bundle else ())):
        brain = brains(role)
        if brain:
            model.setdefault(ACCOUNTS.get(brain.adapter.name, brain.adapter.name), set()).add(brain.model)
    for account, entry in sorted(result["accounts"].items()):
        if account == "unassigned":
            continue
        reading = last_reading(rows, account)
        if reading is None:
            notes.append(f"{account}: no plan reading yet, so {job['id']} started without a limit check "
                         "(record one with `vesper usage record`)")
            continue
        if not entry.get("calibrated"):
            notes.append(f"{account}: uncalibrated, so {job['id']} started without a limit check")
            continue
        models = model.get(account, {None})
        chosen = models.pop() if len(models) == 1 else None
        for limit in LIMITS:
            if limit not in entry:
                continue
            # A window that reset after the reading starts again from 0 at the reset.
            reset_since = next_reset(rows, account, limit, parse_time(reading["at"]))
            if reset_since and reset_since <= now:
                base, start = 0.0, reset_since.astimezone(timezone.utc).isoformat(timespec="seconds")
            else:
                base, start = reading[limit], reading["at"]
            since = sum(row.get("tokens") or 0 for row in rows if row.get("kind") == "call"
                        and row.get("account") == account and parse_time(row["start"]) >= parse_time(start))
            used = percent_band(calibration, account, chosen, since, limit)[1] if since else 0.0
            projected = base + used + entry[limit][1]
            if projected > threshold:
                reset = next_reset(rows, account, limit, now)
                local = reset.astimezone() if reset else None
                soon = bool(reset) and reset - now < timedelta(hours=23)
                return {"job": job["id"], "account": account, "limit": limit,
                        "last_reading": base, "used_since": round(used, 1),
                        "job_estimate": entry[limit][1], "projected": round(projected, 1),
                        "threshold": threshold,
                        "resets_at": reset.isoformat(timespec="minutes") if reset else None,
                        "resets_at_local": local.strftime("%Y-%m-%d %H:%M") if local else None,
                        "start_after": (local + timedelta(minutes=1)).strftime("%H:%M") if soon else None,
                        "resume": (f"run again after {local:%Y-%m-%d %H:%M} (local time), for example "
                                   f"`run --start-after {(local + timedelta(minutes=1)):%H:%M}`" if soon else
                                   f"run again after {local:%Y-%m-%d %H:%M} (local time)" if local else
                                   "record a new plan reading once the window has reset, then run again")}, notes
    return None, notes
