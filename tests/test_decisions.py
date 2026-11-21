"""P2-T7: advisory backlog and decision gate (advisories and blockers end in the owner's decision)."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)
import test_planning
import test_rc1

from builder import approvals
from builder.contracts import BuilderError
from builder.planning import plan_report_schema, review_plan, validate_critique
from builder.review_gate import CATEGORIES, prompt, report_schema, validate_report


def finding(severity, category, path="app.js"):
    return {"severity": severity, "category": category, "path": path,
            "evidence": f"The {category} problem the reviewer saw in {path}.",
            "recommendation": f"Fix the {category} problem in {path}."}


def job_report(preview, *findings):
    data = test_rc1.verdict(preview)
    data["findings"] = list(findings)
    data["verdict"] = "request_changes" if any(item["severity"] == "blocking" for item in findings) else "approve"
    return data


def sheets(folder):
    return [path.read_text() for path in sorted(Path(folder).glob("*-accept-risk.txt"))]


class CategoryTests(unittest.TestCase):
    PACKET = {"attempt_id": "a", "base_digest": "b", "candidate_digest": "c"}

    def report(self, *findings):
        return {**self.PACKET, "verdict": "request_changes" if any(
            item["severity"] == "blocking" for item in findings) else "approve", "summary": "s",
            "evidence": dict.fromkeys(("requirements", "correctness", "scope", "tests", "maintainability",
                                       "security"), "e"), "findings": list(findings)}

    def test_every_finding_needs_a_known_category(self):
        self.assertEqual(CATEGORIES, ("correctness", "security", "data", "performance", "maintainability",
                                      "design", "other"))
        validate_report(self.report(finding("advisory", "data")), self.PACKET)
        missing = finding("advisory", "data")
        del missing["category"]
        for item in (missing, finding("advisory", "style")):
            with self.assertRaisesRegex(BuilderError, "category"):
                validate_report(self.report(item), self.PACKET)

    def test_both_schemas_and_prompts_carry_the_category(self):
        for schema in (report_schema(self.PACKET), plan_report_schema("d", "r")):
            items = schema["properties"]["findings"]["items"]
            self.assertIn("category", items["required"])
            self.assertEqual(items["properties"]["category"]["enum"], list(CATEGORIES))
        role = {"name": "reviewer", "revision": "r", "instructions": "Review.", "skills": []}
        with mock.patch("builder.team.render", return_value="Review."):
            self.assertIn("category", prompt(role, self.PACKET))

    def test_plan_findings_need_a_known_category(self):
        planning = test_planning.PlanningTests("run")
        planning.setUp()
        self.addCleanup(planning.temp.cleanup)
        planning.full()
        bundle = planning.runner.review()["files"]
        report = planning.report("request_changes")
        validate_critique(report, bundle, report["packet_digest"])
        report["findings"][0]["category"] = "vibes"
        with self.assertRaisesRegex(BuilderError, "category"):
            validate_critique(report, bundle, report["packet_digest"])


class JobDecisionTests(unittest.TestCase):
    """Job reviews, through the `vesper` door."""
    Base = test_rc1.TeamTests
    setUp, cli, git, plan, approve, submit, write_report = (Base.setUp, Base.cli, Base.git, Base.plan,
                                                            Base.approve, Base.submit, Base.write_report)

    def start(self, attempts=None):
        project, command = self.plan()
        if attempts:
            path = project / "plan" / "contract.json"
            contract = json.loads(path.read_text())
            contract["jobs"][0]["max_attempts"] = attempts
            path.write_text(json.dumps(contract))
        self.approve(command)
        _, preview = self.submit(command)
        return project, command, preview

    def review(self, command, preview, *findings, code=0):
        return command("review-candidate", "--report", self.write_report(job_report(preview, *findings)),
                       "--attest-independent", code=code)

    def backlog(self, project):
        return json.loads((project / ".builder" / "backlog.json").read_text())["items"]

    def test_advisories_are_kept_in_the_backlog_and_shown_in_status(self):
        project, command, preview = self.start()
        result = self.review(command, preview, finding("advisory", "maintainability"))
        self.assertEqual(result["outcome"], "accepted")
        status = command("status")
        self.assertEqual(status["status"], "complete")
        [item] = status["backlog"]
        self.assertEqual((item["id"], item["category"], item["severity"], item["status"], item["job"]),
                         ("F1", "maintainability", "advisory", "noted", "J1"))
        self.assertEqual(self.backlog(project)[0]["recommendation"], "Fix the maintainability problem in app.js.")

    def test_security_advisory_waits_for_the_owner_then_accept_risk_continues(self):
        project, command, preview = self.start()
        result = self.review(command, preview, finding("advisory", "security"), finding("advisory", "design"),
                             code=1)
        self.assertEqual(result["outcome"], "awaiting_decision")
        status = command("status", code=1)
        self.assertEqual((status["status"], status["completed"], status["awaiting_decision"]),
                         ("awaiting_decision", [], ["F1"]))
        # Nothing moves on until the owner decides; the run cannot reach complete.
        self.assertIn("decide", command("prepare", code=2))
        self.assertIn("decide", command("review-candidate", "--report", self.write_report(job_report(preview)),
                                        "--attest-independent", code=2))
        self.assertIn("reason", command("decide", "F1", "--accept-risk", code=2))
        self.assertIn("does not await", command("decide", "F2", "--accept-risk", "--reason", "x", code=2))
        # An AI cannot accept the risk itself: without a human confirmation it is refused.
        self.env["VESPER_TEST_CONFIRM_ANSWER"] = "no"
        self.assertIn("not confirmed", command("decide", "F1", "--accept-risk", "--reason", "Owner only", code=2))
        self.assertEqual(command("status", code=1)["status"], "awaiting_decision")
        del self.env["VESPER_TEST_CONFIRM_ANSWER"]
        with tempfile.TemporaryDirectory() as folder:
            self.env["VESPER_TEST_SHEETS"] = folder
            result = command("decide", "F1", "--accept-risk", "--reason", "Only the owner can reach it")
            [sheet] = sheets(folder)
        self.assertEqual(result["status"], "complete")
        for field in ("F1", "security advisory", "the independent review of job J1",
                      "The security problem the reviewer saw in app.js.", "Fix the security problem in app.js.",
                      "Job J1's candidate is accepted with this finding unfixed",
                      "Your reason: Only the owner can reach it", "Digest: "):
            self.assertIn(field, sheet)
        accepted = {item["id"]: item for item in command("status")["backlog"]}
        self.assertEqual((accepted["F1"]["status"], accepted["F1"]["decision"]["reason"]),
                         ("accepted", "Only the owner can reach it"))
        self.assertEqual(accepted["F2"]["status"], "noted")
        records = json.loads((project / ".builder" / "confirmations.json").read_text())
        self.assertEqual(records[-1]["action"], "accept-risk")

    def test_fix_returns_the_job_for_correction_as_a_retry(self):
        _, command, preview = self.start()
        self.review(command, preview, finding("advisory", "data"), code=1)
        result = command("decide", "F1", "--fix")
        self.assertEqual(result["status"], "ready")
        [attempt] = result["attempts"]
        self.assertEqual((attempt["outcome"], attempt["failure_kind"]), ("rejected", "review"))
        self.assertIn("F1", attempt["reason"])
        self.assertEqual(result["backlog"][0]["status"], "fix")
        brief = Path(command("prepare")["brief"]).read_text()
        self.assertIn("Fix the data problem in app.js.", brief)

    def test_job_out_of_attempts_with_open_blockers_awaits_the_owner(self):
        _, command, preview = self.start(attempts=1)
        self.review(command, preview, finding("blocking", "correctness"), code=1)
        status = command("status", code=1)
        self.assertEqual((status["status"], status["awaiting_decision"]), ("awaiting_decision", ["F1"]))
        result = command("decide", "F1", "--fix")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["retry_grants"]), 1)
        self.assertIn("F1", result["retry_grants"][0]["reason"])
        attempt = command("prepare")
        (Path(attempt["workspace"]) / "app.js").write_text("export const loading = false;\n")
        preview = command("submit", attempt["id"])
        self.review(command, preview, finding("blocking", "security"), code=1)
        self.assertEqual(command("status", code=1)["awaiting_decision"], ["F2"])
        self.env["VESPER_TEST_CONFIRM_ANSWER"] = "no"
        self.assertIn("not confirmed", command("decide", "F2", "--accept-risk", "--reason", "Known", code=2))
        del self.env["VESPER_TEST_CONFIRM_ANSWER"]
        with tempfile.TemporaryDirectory() as folder:
            self.env["VESPER_TEST_SHEETS"] = folder
            result = command("decide", "F2", "--accept-risk", "--reason", "Known and harmless here")
            [sheet] = sheets(folder)
        self.assertIn("security blocker", sheet)
        self.assertIn("Job J1's last candidate, which the reviewer rejected, is accepted with this blocker unfixed",
                      sheet)
        self.assertEqual(result["status"], "complete")
        last = result["attempts"][-1]
        self.assertEqual((last["outcome"], last["accepted_risks"]), ("accepted", ["F2"]))
        self.assertEqual(last["review"]["verdict"], "request_changes")
        self.assertEqual((Path(result["snapshot"]) / "app.js").read_text(), "export const loading = false;\n")

    def test_security_advisory_on_a_rejected_candidate_still_waits_for_the_owner(self):
        # Review round 1 of PR 43: it was sent back as "returned" and the run reached complete.
        project, command, preview = self.start(attempts=2)
        self.review(command, preview, finding("blocking", "correctness"), finding("advisory", "security"), code=1)
        status = command("status", code=1)
        self.assertEqual((status["status"], status["awaiting_decision"]), ("awaiting_decision", ["F2"]))
        self.assertEqual([item["status"] for item in status["backlog"]], ["returned", "awaiting_decision"])
        self.assertIn("decide", command("prepare", code=2))
        # The backlog is only a view: editing it changes neither the gate nor what the owner is shown.
        path = project / ".builder" / "backlog.json"
        data = json.loads(path.read_text())
        data["items"][1].update(status="noted", evidence="Nothing to see here.")
        path.write_text(json.dumps(data))
        self.assertEqual(command("status", code=1)["status"], "awaiting_decision")
        with tempfile.TemporaryDirectory() as folder:
            self.env["VESPER_TEST_SHEETS"] = folder
            result = command("decide", "F2", "--accept-risk", "--reason", "Single user")
            [sheet] = sheets(folder)
        self.assertIn("The security problem the reviewer saw in app.js.", sheet)
        self.assertIn("goes on to its next attempt with this finding accepted as a risk", sheet)
        self.assertEqual((result["status"], result["completed"]), ("ready", []))
        attempt = command("prepare")
        (Path(attempt["workspace"]) / "app.js").write_text("export const loading = false;\n")
        self.review(command, command("submit", attempt["id"]))
        self.assertEqual(command("status")["status"], "complete")

    def test_fixing_an_advisory_on_a_rejected_candidate_tells_the_worker(self):
        _, command, preview = self.start(attempts=2)
        self.review(command, preview, finding("blocking", "correctness"), finding("advisory", "data"), code=1)
        result = command("decide", "F2", "--fix")
        self.assertEqual(result["status"], "ready")
        brief = Path(command("prepare")["brief"]).read_text()
        self.assertIn("Fix the data problem in app.js.", brief)
        self.assertIn("Fix the correctness problem in app.js.", brief)

    def test_a_candidate_waiting_for_the_owner_cannot_be_abandoned(self):
        _, command, preview = self.start()
        self.review(command, preview, finding("advisory", "security"), code=1)
        self.assertIn("only the owner", command("abandon", preview["id"], code=2))


class PlanDecisionTests(unittest.TestCase):
    """Plan-critique blockers and advisories, at the runner."""
    Base = test_planning.PlanningTests
    setUp, full, write, report = Base.setUp, Base.full, Base.write, Base.report

    def critique(self, *findings):
        report = self.report("request_changes" if any(item["severity"] == "blocking" for item in findings)
                             else "approve")
        report["findings"] = [dict(item, scenario="A second device writes", consequence="A lost write")
                              for item in findings]
        review_plan(self.runner, report=report, external_attested=True)

    def test_a_plan_blocker_can_be_sent_back(self):
        self.full()
        self.critique(finding("blocking", "correctness", "plan/architecture.md"))
        status = self.runner.status()
        self.assertEqual(status["awaiting_decision"], ["F1"])
        digest = self.runner.review()["digest"]
        with self.assertRaisesRegex(BuilderError, "plan critique.*F1"):
            self.runner.approve(digest)
        with self.runner.lock():
            result = self.runner.decide("F1", fix=True)
        self.assertEqual(result["backlog"][0]["status"], "fix")
        with self.assertRaisesRegex(BuilderError, "F1.*sent back"):
            self.runner.approve(digest)

    def test_accepted_plan_blockers_allow_approval_and_the_sheet_lists_each(self):
        self.full()
        self.critique(finding("blocking", "correctness", "plan/architecture.md"),
                      finding("blocking", "data", "plan/product.md"))
        digest = self.runner.review()["digest"]
        with mock.patch.dict(os.environ, {"VESPER_TEST_CONFIRM_ANSWER": "no"}), self.runner.lock():
            with self.assertRaisesRegex(BuilderError, "not confirmed"):
                self.runner.decide("F1", accept=True, reason="The retry identity is a later phase")
        with mock.patch.dict(os.environ, {approvals.TEST_CONFIRMER: ""}), self.runner.lock(), \
                mock.patch.object(approvals, "configured_confirmer", return_value="tty"):
            with self.assertRaisesRegex(BuilderError, "terminal"):
                self.runner.decide("F1", accept=True, reason="The retry identity is a later phase")
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.dict(os.environ, {"VESPER_TEST_SHEETS": folder}), self.runner.lock():
                self.runner.decide("F1", accept=True, reason="The retry identity is a later phase")
            [sheet] = sheets(folder)
        for field in ("F1", "correctness blocker", "the independent plan critique", "plan/architecture.md",
                      "The plan can be approved with this blocker unfixed",
                      "Your reason: The retry identity is a later phase"):
            self.assertIn(field, sheet)
        with self.assertRaisesRegex(BuilderError, "F2"):
            self.runner.approve(digest)
        with self.runner.lock():
            self.runner.decide("F2", accept=True, reason="Data loss on two devices is accepted for now")
        plan_sheet = self.runner.review_sheet()
        for field in ("F1", "The retry identity is a later phase", "F2", "Data loss on two devices is accepted"):
            self.assertIn(field, plan_sheet)
        self.runner.prove_checks()  # P3-T3: focused and full depth prove the checks
        self.runner.approve(digest)
        state = self.runner.state()
        self.assertEqual([item["id"] for item in state["accepted_risks"]], ["F1", "F2"])

    def test_plan_security_advisory_is_accepted_by_the_plan_approval(self):
        self.full()
        self.critique(finding("advisory", "security", "plan/architecture.md"),
                      finding("advisory", "performance", "plan/architecture.md"))
        self.assertEqual(self.runner.status()["awaiting_decision"], ["F1"])
        sheet = self.runner.review_sheet()
        risks = sheet.split("Risks you accept by approving:")[1]
        self.assertIn("Fix the security problem in plan/architecture.md", risks)
        self.assertNotIn("performance", risks)
        self.runner.prove_checks()  # P3-T3: focused and full depth prove the checks
        self.runner.approve(self.runner.review()["digest"])
        items = {item["id"]: item for item in self.runner.status()["backlog"]}
        self.assertEqual((items["F1"]["status"], items["F1"]["decision"]["by"]), ("accepted", "plan approval"))
        self.assertEqual(items["F2"]["status"], "noted")
        self.assertEqual(self.runner.status()["status"], "ready")

    def test_a_plan_advisory_sent_back_also_holds_approval(self):
        self.full()
        self.critique(finding("advisory", "data", "plan/architecture.md"))
        with self.runner.lock():
            self.runner.decide("F1", fix=True)
        with self.assertRaisesRegex(BuilderError, "F1.*sent back"):
            self.runner.approve(self.runner.review()["digest"])

    def test_an_acceptance_written_into_the_backlog_by_hand_does_not_count(self):
        self.full()
        self.critique(finding("blocking", "security", "plan/architecture.md"))
        path = self.root / ".builder" / "backlog.json"
        data = json.loads(path.read_text())
        data["items"][0].update(status="accepted", decision={"kind": "accept-risk", "reason": "AI says fine",
                                                              "digest": "0" * 64})
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(BuilderError, "F1 awaits your decision"):
            self.runner.approve(self.runner.review()["digest"])

    def test_editing_a_blockers_severity_or_packet_in_the_backlog_does_not_lift_it(self):
        # Review round 1 of PR 43: the gate trusted these fields of the backlog.
        self.full()
        self.critique(finding("blocking", "security", "plan/architecture.md"))
        digest = self.runner.review()["digest"]
        path = self.root / ".builder" / "backlog.json"
        for change in ({"severity": "advisory"}, {"packet_digest": "0" * 64}):
            with self.subTest(change=change):
                data = json.loads(path.read_text())
                data["items"][0].update(change)
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(BuilderError, "F1 awaits your decision"):
                    self.runner.approve(digest)
        self.assertFalse(self.runner.state_file.exists())

    def test_a_revised_plan_supersedes_earlier_critique_findings(self):
        self.full()
        self.critique(finding("blocking", "correctness", "plan/architecture.md"))
        (self.root / "plan" / "architecture.md").write_text("Restore the version check with a request id.")
        with self.runner.lock(), self.assertRaisesRegex(BuilderError, "plan has changed"):
            self.runner.decide("F1", accept=True, reason="x")
        self.critique()
        items = self.runner.status()["backlog"]
        self.assertEqual([item["status"] for item in items], ["superseded"])
        self.runner.prove_checks()  # P3-T3: focused and full depth prove the checks
        self.runner.approve(self.runner.review()["digest"])


if __name__ == "__main__":
    unittest.main()
