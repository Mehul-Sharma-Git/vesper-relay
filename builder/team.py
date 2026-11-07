"""The portable role catalog used by both provider adapters."""

from pathlib import Path

from .contracts import fingerprint, nonempty, require

ROOT = Path(__file__).resolve().parents[1] / "team"
PROFILES = {
    "planner": ("consult", "discovery", ()),
    "designer": ("consult", "interaction-design", ("webgl-motion",)),
    "frontend": ("write", "frontend-delivery", ("react", "webgl-motion")),
    "backend": ("write", "backend-delivery", ("sqlite", "postgres")),
    "qa": ("consult", "acceptance-evidence", ("react", "sqlite", "postgres", "webgl-motion")),
    "reviewer": ("review", "candidate-review", ("security-diff",)),
    "technical-lead": ("consult", "interface-coordination", ("sqlite", "postgres", "security-diff")),
}


def catalog():
    return {role: {"access": access, "default_skill": core, "optional_skills": list(extra)}
            for role, (access, core, extra) in PROFILES.items()}


def profile(role, selected=()):
    require(isinstance(role, str) and role in PROFILES, f"Unknown team role: {role}")
    access, core, extra = PROFILES[role]
    require(isinstance(selected, (list, tuple)) and all(isinstance(item, str) for item in selected),
            f"Invalid skills for {role}")
    require(len(selected) == len(set(selected)), f"Duplicate skills for {role}")
    for skill in selected:
        require(skill in extra, f"Skill {skill} is unavailable for {role}")
    result = {
        "role": role, "access": access,
        "instructions": (ROOT / "roles" / (role + ".md")).read_text(encoding="utf-8"),
        "skills": {skill: (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
                   for skill in (core, *selected)},
    }
    return {**result, "revision": fingerprint(result)}


def freeze_team(contract):
    require(type(contract["team"]) is int and contract["team"] == 1, "Unsupported team contract version")
    jobs = {}
    for job in contract["jobs"]:
        selected = profile(job["role"], job.get("skills", []))
        require(selected["access"] == "write", f"Role {job['role']} is not a writing role")
        require(job.get("review", "standard") in ("standard", "security"),
                f"Unsupported review level for {job['id']}")
        jobs[job["id"]] = selected
    return {"jobs": jobs, "reviewer": profile("reviewer"),
            "security_reviewer": profile("reviewer", ["security-diff"])}


def render(profile_data):
    text = [f"## Specialist role: {profile_data['role']}", profile_data["instructions"]]
    for skill, instructions in profile_data["skills"].items():
        text.extend((f"## Skill: {skill}", instructions))
    return "\n\n".join(text)


def validate_design(spec):
    require(isinstance(spec, dict) and all(nonempty(spec.get(key)) for key in
            ("audience", "primary_task", "representative_content", "chosen", "reason", "avoid")),
            "Design brief needs audience, task, real content, a chosen direction, rationale, and patterns to avoid")
    options = spec.get("directions")
    require(isinstance(options, list) and 2 <= len(options) <= 4 and all(
        isinstance(item, dict) and all(nonempty(item.get(key)) for key in
                                      ("name", "composition", "benefit", "tradeoff")) for item in options),
        "Compare two to four visual directions with composition, benefit, and tradeoff")
    names = {item["name"] for item in options}
    compositions = {item["composition"].strip().casefold() for item in options}
    require(len(names) == len(options) == len(compositions) and spec["chosen"] in names,
            "Each design direction needs a distinct name and composition, with one selected")
    for key in ("narrow", "wide", "focus", "motion", "browser_evidence"):
        require(nonempty(spec.get(key)), f"Design brief is missing {key}")
    states = spec.get("states")
    require(isinstance(states, dict) and states and all(nonempty(value) for value in states.values()),
            "Describe the applicable interaction states")
