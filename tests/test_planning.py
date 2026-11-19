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


def narrow(root):
    data = {"version": 1, "impact": dict.fromkeys(
        ("new_system", "data", "security", "integrations", "deployment", "cross_layer"), False),
        "rationale": "Restore existing behavior in one established pattern.",
        "authors": ["planner-session"], "existing_design": "architecture.md"}
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

    def full(self):
        data = narrow(self.root)
        data["impact"]["security"] = True
        data["architecture"] = {"owner": "technical-lead", "author": "architect-session",
            "revision": profile("technical-lead")["revision"], "artifact": "architecture.md",
            "inputs": ["product.md", "decisions.md"], "consumers": ["backend", "qa"]}
        data["authors"].append("architect-session")
        data["handoff"] = {"canonical_contract": "architecture.md", "acknowledged_by": ["backend", "qa"]}
        self.write(data)
        return data

    def write(self, data):
        (self.root / "plan/planning.json").write_text(json.dumps(data))

    def report(self, verdict="approve"):
        packet = self.runner.review()["packet_digest"]
        return {"phase": "plan", "packet_digest": packet, "reviewer": "critic-session",
                "verdict": verdict, "summary": "Checked version and retry semantics.",
                "evidence": {"requirements": "product.md requires stale-write rejection.",
                             "architecture": "architecture.md keeps SQLite as state owner.",
                             "checks": "gate.py covers the approved invariant."},
                "findings": [] if verdict == "approve" else [{"severity": "blocking",
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
        self.runner.approve(self.runner.review()["digest"])
        self.assertIn("current version envelope", Path(self.runner.prepare()["brief"]).read_text())

    def test_preflight_failure_does_not_spend_critique_attempts(self):
        from builder.planning import review_plan
        self.full()
        for _ in range(3):
            with self.assertRaisesRegex(BuilderError, "trust-host"):
                review_plan(self.runner, brain=Brain("codex", ADAPTERS["codex"]))
        review_plan(self.runner, report=self.report(), external_attested=True)
        self.runner.approve(self.runner.review()["digest"])
