import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_local import initialize
from builder.brains import ADAPTERS, Brain
from builder.contracts import BuilderError
from builder.runner import Runner
from builder.team import profile
import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)


SKIP_SECTIONS = ("problem", "assumptions", "estimate")
FOCUSED_SECTIONS = ("risks", "stack", "threat_model", "reachability", "concurrency", "failure_paths")
FULL_SECTIONS = ("options", "components", "phases")


def skip_sections(jobs=1):
    return {"problem": {"why": "A stale write overwrites newer data.", "success": "A stale write is refused.",
                        "non_goals": ["No new conflict screen"]},
            "assumptions": [{"assumption": "Only the version check regressed",
                             "confirm": "The gate fails on the seed", "when": "Before approval"}],
            "estimate": {"jobs": jobs, "summary": "Estimate: 1 job, 2–4 AI calls; uncalibrated"}}


def focused_sections():
    return {"risks": [{"risk": "The fix also refuses fresh writes", "check": "G"},
                      {"risk": "Clock skew between devices", "mitigation": "Versions are counters, not times"}],
            "stack": "existing repo",
            "threat_model": {"trusted": ["The owner's devices"], "in_scope": ["Stale writes from a second device"],
                             "out_of_scope": ["Someone on the network"]},
            "reachability": [{"id": "A1", "item": "The owner's browser", "gates": ["G"]},
                             {"id": "A2", "item": "Devices on the home Wi-Fi", "accept": "One owner, no login (D3)"}],
            "concurrency": [{"id": "C1", "item": "Two devices write the same record", "gates": ["G"]},
                            {"id": "C2", "item": "Two servers on one file", "accept": "One server per file"}],
            "failure_paths": [{"items": ["R", "C1"], "scenario": "Write with an old version",
                               "assertion": "409 and the record is unchanged",
                               "catches": "A guard that compares the count instead of the version", "gates": ["G"]}]}


def full_sections():
    components = {name: {"decision": "no"} for name in ("cache", "queue", "cdn", "realtime", "search")}
    components["storage"] = {"decision": "now", "reason": "SQLite holds the records"}
    return {"options": {"approaches": [{"name": "Version column", "tradeoffs": "One integer per row"},
                                       {"name": "Row lock", "tradeoffs": "Blocks the second device"}],
                        "recommendation": "Version column", "reason": "No waiting, detects stale writes"},
            "components": components,
            "phases": [{"name": "Fix", "goal": "Restore the version check"}]}


def narrow(root, version=2):
    data = {"version": version, "impact": dict.fromkeys(
        ("new_system", "data", "security", "integrations", "deployment", "cross_layer"), False),
        "rationale": "Restore existing behavior in one established pattern.",
        "authors": ["planner-session"], "existing_design": "architecture.md"}
    if version == 2:
        data.update(skip_sections())
    (root / "plan" / "planning.json").write_text(json.dumps(data))
    return data


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run"
        initialize(self.root, "Fix established behavior")
        intake = {"mode": "bug", "repository": None, "guidance": {}, "team_contract": 1,
                  "planning_version": 1}
        (self.root / ".vesper.json").write_text(json.dumps({"intake": intake}))
        (self.root / "plan/intake.json").write_text(json.dumps(intake))
        for name in ("product", "architecture", "design", "decisions"):
            (self.root / "plan" / (name + ".md")).write_text("Restore the existing version check.")
        contract = {"team": 1, "title": "Version fix", "delivery": "local patch",
                    "requirements": [{"id": "R", "description": "Reject stale writes", "checks": ["G"]}],
                    "checks": [{"id": "G", "script": "gate.py"}],
                    "jobs": [{"id": "J", "role": "backend", "goal": "Restore version check",
                              "paths": ["server.py"], "depends_on": [], "checks": ["G"]}]}
        (self.root / "plan/contract.json").write_text(json.dumps(contract))
        (self.root / "checks/gate.py").write_text("assert True")
        self.runner = Runner(self.root)

    def full(self, version=2):
        data = narrow(self.root, version)
        data["impact"]["security"] = True
        data["architecture"] = {"owner": "technical-lead", "author": "architect-session",
            "revision": profile("technical-lead")["revision"], "artifact": "architecture.md",
            "inputs": ["product.md", "decisions.md"], "consumers": ["backend", "qa"]}
        data["authors"].append("architect-session")
        data["handoff"] = {"canonical_contract": "architecture.md", "acknowledged_by": ["backend", "qa"]}
        if version == 2:
            data.update(focused_sections(), **full_sections())
        self.write(data)
        return data

    def focused(self):
        data = self.full()
        data["impact"]["security"] = False
        data["impact"]["cross_layer"] = True
        for name in FULL_SECTIONS:
            data.pop(name)
        self.write(data)
        return data

    def intake_version(self, version):
        for path in (self.root / ".vesper.json", self.root / "plan/intake.json"):
            value = json.loads(path.read_text())
            value.get("intake", value)["planning_version"] = version
            path.write_text(json.dumps(value))

    def write(self, data):
        (self.root / "plan/planning.json").write_text(json.dumps(data))

    def report(self, verdict="approve"):
        packet = self.runner.review()["packet_digest"]
        return {"phase": "plan", "packet_digest": packet, "reviewer": "critic-session",
                "verdict": verdict, "summary": "Checked version and retry semantics.",
                "evidence": {"requirements": "product.md requires stale-write rejection.",
                             "architecture": "architecture.md keeps SQLite as state owner.",
                             "checks": "gate.py covers the approved invariant."},
                "findings": [] if verdict == "approve" else [{"severity": "blocking", "category": "correctness",
                    "path": "plan/architecture.md:1", "scenario": "Retry after lost response",
                    "consequence": "Duplicate write", "evidence": "No retry identity specified",
                    "recommendation": "Specify the stable request identity."}]}

    def test_new_run_cannot_approve_without_impact_record(self):
        with self.assertRaisesRegex(BuilderError, "planning.json"):
            self.runner.review()

    def test_narrow_skip_retains_team_candidate_review(self):
        narrow(self.root)
        self.runner.approve(self.runner.review()["digest"])
        state = self.runner.state()
        self.assertEqual(state["bundle"]["planning"]["depth"], "skip")
        self.assertIn("reviewer", state["bundle"]["team"])

    def test_backend_security_requires_architect_and_critique(self):
        data = narrow(self.root)
        data["impact"]["security"] = True
        self.write(data)
        with self.assertRaisesRegex(BuilderError, "architecture handoff"):
            self.runner.review()
        self.full()
        with self.assertRaisesRegex(BuilderError, "plan critique"):
            self.runner.approve(self.runner.review()["digest"])

    def test_independent_critique_and_changed_checks_invalidate_approval(self):
        from builder.planning import review_plan
        self.full()
        report = self.report()
        with self.assertRaisesRegex(BuilderError, "independent"):
            review_plan(self.runner, report=report)
        with self.assertRaisesRegex(BuilderError, "author"):
            review_plan(self.runner, report={**report, "reviewer": "architect-session"}, external_attested=True)
        review_plan(self.runner, report=report, external_attested=True)
        old = self.runner.review()["digest"]
        (self.root / "checks/gate.py").write_text("assert 1 == 1")
        with self.assertRaises(BuilderError):
            self.runner.approve(old)
        with self.assertRaisesRegex(BuilderError, "plan critique"):
            self.runner.approve(self.runner.review()["digest"])
        review_plan(self.runner, report=self.report(), external_attested=True)
        self.runner.prove_checks()  # P3-T3: focused and full depth prove the checks
        self.runner.approve(self.runner.review()["digest"])
        self.assertEqual(self.runner.state()["bundle"]["plan_critique"]["report"]["reviewer"], "critic-session")

    def test_blocker_cannot_approve_and_retry_is_bounded(self):
        from builder.planning import review_plan
        self.full()
        for _ in range(3):
            review_plan(self.runner, report=self.report("request_changes"), external_attested=True)
        with self.assertRaisesRegex(BuilderError, "plan critique"):
            self.runner.approve(self.runner.review()["digest"])
        with self.assertRaisesRegex(BuilderError, "limit"):
            review_plan(self.runner, report=self.report(), external_attested=True)

    def test_focused_cross_layer_and_marker_removal_cannot_bypass(self):
        data = self.full()
        data["impact"]["security"] = False
        data["impact"]["cross_layer"] = True
        self.write(data)
        self.assertEqual(self.runner.review()["files"]["planning"]["depth"], "focused")
        # Removing the version marker does not exempt a managed draft.
        for path in (self.root / ".vesper.json", self.root / "plan/intake.json"):
            value = json.loads(path.read_text())
            (value.get("intake", value)).pop("planning_version")
            path.write_text(json.dumps(value))
        (self.root / "plan/planning.json").unlink()
        with self.assertRaisesRegex(BuilderError, "planning.json"):
            self.runner.approve("anything")

    def test_canonical_contract_reaches_worker(self):
        from builder.planning import review_plan
        data = self.full()
        data["handoff"]["canonical_contract"] = "api-contract.md"
        self.write(data)
        (self.root / "plan/api-contract.md").write_text("Conflict uses the current version envelope.")
        review_plan(self.runner, report=self.report(), external_attested=True)
        self.runner.prove_checks()  # P3-T3: focused and full depth prove the checks
        self.runner.approve(self.runner.review()["digest"])
        self.assertIn("current version envelope", Path(self.runner.prepare()["brief"]).read_text())

    # P2-T5: required plan sections by depth (planning manifest version 2) ----------------------

    def test_version_2_requires_each_section_its_depth_needs_and_names_it(self):
        cases = (("skip", lambda: narrow(self.root), SKIP_SECTIONS),
                 ("focused", self.focused, SKIP_SECTIONS + FOCUSED_SECTIONS),
                 ("full", self.full, SKIP_SECTIONS + FOCUSED_SECTIONS + FULL_SECTIONS))
        for depth, build, required in cases:
            with self.subTest(depth=depth):
                data = build()
                self.assertEqual(self.runner.review()["files"]["planning"]["depth"], depth)
                for name in required:
                    self.write({key: value for key, value in data.items() if key != name})
                    with self.assertRaisesRegex(BuilderError, rf"{depth} depth.*: {name}\b"):
                        self.runner.review()
                self.write(data)

    def test_version_2_plans_with_their_sections_are_accepted_at_each_depth(self):
        from builder.planning import review_plan
        narrow(self.root)  # skip: no risks, stack, lists or options needed
        self.runner.approve(self.runner.review()["digest"])
        self.assertEqual(self.runner.state()["bundle"]["planning"]["manifest"]["version"], 2)
        for build in (self.focused, self.full):
            with self.subTest(depth=build.__name__):
                self.setUp()
                build()
                review_plan(self.runner, report=self.report(), external_attested=True)
                self.runner.prove_checks()  # P3-T3: focused and full depth prove the checks
                self.runner.approve(self.runner.review()["digest"])

    def test_version_1_manifests_still_validate_for_version_1_runs_only(self):
        narrow(self.root, version=1)
        self.runner.review()
        self.full(version=1)
        self.runner.review()
        self.intake_version(2)  # what `vesper start` writes for new runs
        with self.assertRaisesRegex(BuilderError, "version 2"):
            self.runner.review()
        narrow(self.root, version=1)
        with self.assertRaisesRegex(BuilderError, "version 2"):
            self.runner.review()
        self.intake_version(3)
        with self.assertRaisesRegex(BuilderError, "Unsupported managed planning version"):
            self.runner.review()

    def test_an_approved_version_1_run_still_resumes(self):
        narrow(self.root, version=1)
        self.runner.approve(self.runner.review()["digest"])
        self.assertIn("Restore version check", Path(self.runner.prepare()["brief"]).read_text())

    def test_list_items_need_a_known_gate_or_a_risk_with_a_reason(self):
        data = self.focused()
        bad = {
            "unknown gate": ("reachability", 0, {"gates": ["G_NOPE"]}),
            "gate or a risk": ("concurrency", 1, {"gates": ["G"]}),        # both
            "gate or a risk ": ("concurrency", 0, {"gates": None}),         # neither
            "reason": ("reachability", 1, {"accept": " "}),
            "assertion": ("failure_paths", 0, {"assertion": ""}),
            "requirement or a listed item": ("failure_paths", 0, {"items": ["R9"]}),
            "check or a mitigation": ("risks", 0, {"mitigation": "Also this"}),
        }
        for message, (section, index, change) in bad.items():
            with self.subTest(message=message):
                broken = json.loads(json.dumps(data))
                item = broken[section][index]
                for key, value in change.items():
                    if value is None:
                        item.pop(key)
                    else:
                        item[key] = value
                self.write(broken)
                with self.assertRaisesRegex(BuilderError, f"{section}.*{message.strip()}"):
                    self.runner.review()
        duplicate = json.loads(json.dumps(data))
        duplicate["concurrency"][0]["id"] = "A1"
        self.write(duplicate)
        with self.assertRaisesRegex(BuilderError, "distinct ids"):
            self.runner.review()

    def test_section_shapes_are_checked(self):
        data = self.full()
        bad = {
            "problem": lambda d: d["problem"].update(non_goals=[]),
            "assumptions": lambda d: d["assumptions"][0].pop("when"),
            "stack": lambda d: d.update(stack="whatever we like"),
            "threat_model": lambda d: d["threat_model"].pop("in_scope"),
            "options": lambda d: d["options"]["approaches"].pop(),
            "options ": lambda d: d["options"].update(recommendation="Something else"),
            "options  ": lambda d: d["options"].update(recommendation=["Version column"]),
            "risks": lambda d: d["risks"][0].update(check=["G"]),
            "estimate": lambda d: d["estimate"].update(jobs="1"),
            "components": lambda d: d["components"].pop("cdn"),
            "components ": lambda d: d["components"].update(queue={"decision": "later"}),
            "phases": lambda d: d.update(phases=[]),
        }
        for section, change in bad.items():
            with self.subTest(section=section):
                broken = json.loads(json.dumps(data))
                change(broken)
                self.write(broken)
                with self.assertRaisesRegex(BuilderError, section.strip()):
                    self.runner.review()
        data["stack"] = {"choice": "Python and SQLite", "reason": "The repository already uses them"}
        data["components"]["queue"] = {"decision": "later", "trigger": "More than one writer process"}
        self.write(data)
        self.runner.review()

    def test_estimate_matches_the_contract_and_can_be_made_before_it_is_recorded(self):
        data = narrow(self.root)
        data["estimate"]["jobs"] = 2
        self.write(data)
        with self.assertRaisesRegex(BuilderError, "estimate.*1 job"):
            self.runner.review()
        data.pop("estimate")
        self.write(data)
        with self.assertRaisesRegex(BuilderError, "skip depth.*: estimate"):
            self.runner.review()
        self.assertEqual(self.runner.estimate()["jobs"], 1)  # `vesper estimate` works on the draft

    def test_proposed_risks_are_every_accepted_list_item(self):
        from builder.planning import proposed_risks
        risks = proposed_risks(self.focused())
        self.assertEqual([(item["id"], item["accept"]) for item in risks],
                         [("A2", "One owner, no login (D3)"), ("C2", "One server per file")])
        self.assertEqual(proposed_risks(narrow(self.root, version=1)), [])

    def test_preflight_failure_does_not_spend_critique_attempts(self):
        from builder.planning import review_plan
        self.full()
        for _ in range(3):
            with self.assertRaisesRegex(BuilderError, "trust-host"):
                review_plan(self.runner, brain=Brain("codex", ADAPTERS["codex"]))
        review_plan(self.runner, report=self.report(), external_attested=True)
        self.runner.prove_checks()  # P3-T3: focused and full depth prove the checks
        self.runner.approve(self.runner.review()["digest"])
