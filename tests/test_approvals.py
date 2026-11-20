"""P2-T2: human-only approvals and a plain-language approval sheet, in every door."""
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import stand_in  # noqa: F401  (sets VESPER_TEST_CONFIRMER for this process)
import test_vesper
import test_planning

from builder import approvals
from builder.contracts import BuilderError
from builder.runner import Runner

FIXTURE = test_vesper.ROOT / "docs" / "plan" / "fixtures" / "pocket-todo"
LONG_HEX = re.compile(r"\b[0-9a-f]{16,}\b")


def sheets(folder, action):
    return [path.read_text() for path in sorted(Path(folder).glob(f"*-{action}.txt"))]


class ConfirmerTests(unittest.TestCase):
    """Unit tests of the confirmers themselves."""

    def sheet(self):
        return approvals.Sheet(full="FULL SHEET\nWhat changed: first approval\nDigest: abcdef123456\n",
                               short="SHORT\nWhat changed: first approval\nDigest: abcdef123456\n", files=[])

    def test_tty_refuses_non_interactive_stdin(self):
        with self.assertRaisesRegex(BuilderError, "terminal"):
            approvals.tty_confirm("approve-plan", self.sheet(), stdin=io.StringIO("ANY\n"), stderr=io.StringIO())

    def test_tty_needs_the_shown_code(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        shown = io.StringIO()
        with mock.patch.object(approvals, "new_code", return_value="KXQ7"):
            with self.assertRaisesRegex(BuilderError, "not confirmed"):
                approvals.tty_confirm("approve-plan", self.sheet(), stdin=Terminal("NOPE\n"), stderr=shown)
            approvals.tty_confirm("approve-plan", self.sheet(), stdin=Terminal("KXQ7\n"), stderr=shown)
        self.assertIn("FULL SHEET", shown.getvalue())
        self.assertIn("KXQ7", shown.getvalue())

    def test_macos_dialog_shows_the_short_form_and_can_show_the_full_sheet(self):
        calls, answers = [], iter(["Show full sheet", "Approve"])

        def run(argv, opened=None):
            calls.append(argv)
            return next(answers) if argv[0] == "osascript" else ""
        approvals.dialog_confirm("approve-plan", self.sheet(), run=run, platform="darwin")
        dialogs = [argv for argv in calls if argv[0] == "osascript"]
        self.assertEqual(len(dialogs), 2)
        text = dialogs[0][-1]
        self.assertIn("What changed: first approval", text)
        self.assertIn("abcdef123456", text)
        self.assertNotIn("FULL SHEET", text)
        self.assertTrue(any(argv[0] == "open" for argv in calls))
        with self.assertRaisesRegex(BuilderError, "not confirmed"):
            approvals.dialog_confirm("approve-plan", self.sheet(), run=lambda argv, opened=None: "Cancel",
                                     platform="darwin")
        with self.assertRaisesRegex(BuilderError, "macOS"):
            approvals.dialog_confirm("approve-plan", self.sheet(), run=run, platform="linux")

    def test_without_a_test_confirmer_the_configured_one_decides(self):
        environ = {key: value for key, value in os.environ.items() if key != approvals.TEST_CONFIRMER}
        with self.assertRaisesRegex(BuilderError, "terminal"):
            approvals.confirm("approve-plan", "run", "d" * 64, self.sheet(), environ=environ,
                              confirmer="tty", stdin=io.StringIO(""))
        with self.assertRaisesRegex(BuilderError, "not available yet"):
            approvals.confirm("approve-plan", "run", "d" * 64, self.sheet(), environ=environ,
                              confirmer="dashboard")

    def test_short_form_always_keeps_what_changed_and_the_short_digest(self):
        changed = {"added": ["checks/new.py"], "removed": [], "edited": [
            {"path": "checks/api.py", "lines_before": 10, "lines_after": 12}]}
        text = approvals.what_changed_text(changed)
        self.assertIn("checks/api.py", text)
        self.assertIn("10 → 12 lines", text)
        self.assertEqual(approvals.what_changed_text(None, first="first approval"), "What changed: first approval")


class ConfigAndDoctorTests(unittest.TestCase):
    def test_confirmer_is_a_personal_setting_with_tty_default(self):
        from builder.config import DEFAULTS, LEVELS, validate
        self.assertEqual((DEFAULTS["approvals.confirmer"], LEVELS["approvals"]), ("tty", "personal"))
        for value, message in (("dashboard", "not available yet"), ("yes", "must be one of")):
            with self.assertRaisesRegex(BuilderError, message):
                validate({**DEFAULTS, "approvals.confirmer": value})

    def test_doctor_warns_while_the_test_confirmer_is_set(self):
        from builder.doctor import Probe, doctor
        with tempfile.TemporaryDirectory() as home:
            base = {"HOME": home, "PATH": os.defpath}
            checks = lambda environ: {item["check"]: item for item in doctor(
                call=False, probe=Probe(environ), project=home)["checks"]}
            warned = checks({**base, approvals.TEST_CONFIRMER: "/tmp/stand-in"})["approvals"]
            self.assertEqual(warned["status"], "warn")
            self.assertIn("test stand-in", warned["detail"])
            self.assertEqual(checks(base)["approvals"]["status"], "ok")


class PlanApprovalTests(unittest.TestCase):
    """Runner-level: plan approval and attesting a plan critique."""
    Base = test_planning.PlanningTests
    setUp, full, write, report = Base.setUp, Base.full, Base.write, Base.report

    def test_approval_is_refused_without_a_confirmer_result(self):
        test_planning.narrow(self.root)
        digest = self.runner.review()["digest"]
        with mock.patch.dict(os.environ, {"VESPER_TEST_CONFIRM_ANSWER": "no"}):
            with self.assertRaisesRegex(BuilderError, "not confirmed"):
                self.runner.approve(digest)
        self.assertFalse(self.runner.state_file.exists())
        with mock.patch.dict(os.environ, {approvals.TEST_CONFIRMER: ""}), \
                mock.patch.object(approvals, "configured_confirmer", return_value="tty"), \
                mock.patch.object(sys, "stdin", io.StringIO("")):
            with self.assertRaisesRegex(BuilderError, "terminal"):
                self.runner.approve(digest)
        self.assertFalse(self.runner.state_file.exists())

    def test_recorded_confirmation_binds_the_digest(self):
        test_planning.narrow(self.root)
        digest = self.runner.review()["digest"]
        self.runner.approve(digest)
        state = self.runner.state()
        self.assertEqual(state["confirmation"]["digest"], digest)
        self.assertEqual(state["confirmation"]["confirmer"], "test-stand-in")
        record = json.loads((self.root / ".builder" / "confirmations.json").read_text())[-1]
        self.assertEqual((record["action"], record["digest"]), ("approve-plan", digest))
        self.assertTrue(record["at"])
        entry = next(item for item in record["files"] if item["path"] == "checks/gate.py")
        self.assertEqual(set(entry), {"path", "sha256", "size", "lines"})
        self.assertEqual((entry["size"], entry["lines"]), (len("assert True"), 1))

    def test_attesting_a_plan_critique_needs_a_confirmation(self):
        from builder.planning import review_plan
        self.full()
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.dict(os.environ, {"VESPER_TEST_CONFIRM_ANSWER": "no"}):
                with self.assertRaisesRegex(BuilderError, "not confirmed"):
                    review_plan(self.runner, report=self.report(), external_attested=True)
            self.assertFalse((self.root / ".builder" / "plan-critique.json").exists())
            with mock.patch.dict(os.environ, {"VESPER_TEST_SHEETS": folder}):
                review_plan(self.runner, report=self.report(), external_attested=True)
            sheet = sheets(folder, "attest-independence")[-1]
        for field in ("critic-session", "approve", "0 blockers",
                      "this report came from a separate reviewer session, not the author"):
            self.assertIn(field, sheet)
        self.assertRegex(sheet, r"Report: [0-9a-f]{12}\b")


class PocketTodoSheetTests(unittest.TestCase):
    """CLI-level: the plan sheet for the Pocket Todo fixture."""
    setUp = test_vesper.VesperTests.setUp
    cli = test_vesper.VesperTests.cli
    git = test_vesper.VesperTests.git

    def run_with_fixture(self):
        project = Path(self.cli("start", "--mode", "build", "--idea", "Pocket Todo")["project"])
        for name in ("plan", "checks"):
            shutil.copytree(FIXTURE / name, project / name, dirs_exist_ok=True)
        return project

    def text(self, project, *args):
        p = subprocess.run([sys.executable, "-B", str(test_vesper.ROOT / "vesper.py"), "--project", str(project),
                            *args], cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def critique(self, project):
        packet = self.cli("--project", project, "review", "--json")["packet_digest"]
        report = {"phase": "plan", "packet_digest": packet, "reviewer": "critic-session", "verdict": "approve",
                  "summary": "Swept reachability, concurrency, failure paths and gates.",
                  "evidence": {"requirements": "Every requirement has a gate.",
                               "architecture": "Reachability and concurrency lists are complete.",
                               "checks": "api.py, ui.py and browser.py assert the matrix."},
                  "findings": [{"severity": "advisory", "path": "plan/architecture.md", "scenario": "Wi-Fi peer",
                                "consequence": "Anyone on the Wi-Fi can edit todos",
                                "evidence": "D3 accepts no login", "recommendation":
                                "Accepted risk: owner must confirm that devices on the home Wi-Fi can use the app"}]}
        path = self.root / "critique.json"
        path.write_text(json.dumps(report))
        self.cli("--project", project, "review-plan", "--report", path, "--attest-independent")

    def test_plan_sheet_speaks_plainly_and_json_is_unchanged(self):
        project = self.run_with_fixture()
        self.assertEqual(self.cli("--project", project, "review", "--json"), Runner(project).review())
        self.critique(project)
        sheet = self.text(project, "review")
        contract = json.loads((FIXTURE / "plan" / "contract.json").read_text())
        self.assertIn(contract["title"], sheet)
        for requirement in contract["requirements"]:
            self.assertIn(requirement["id"], sheet)
            self.assertIn(", ".join(requirement["checks"]), sheet)
        for job in contract["jobs"]:
            self.assertIn(job["id"], sheet)
            for path in job["paths"]:
                self.assertIn(path, sheet)
        self.assertIn("Critique: approve, 0 blockers", sheet)
        self.assertIn("Accepted risk: owner must confirm that devices on the home Wi-Fi can use the app", sheet)
        self.assertIn("What changed: first approval", sheet)
        digest = self.cli("--project", project, "review", "--json")["digest"]
        self.assertIn(digest[:12], sheet)
        self.assertEqual(LONG_HEX.findall(sheet), [], "only the short digest may appear")

    def test_what_changed_compares_with_the_last_human_confirmation(self):
        project = self.run_with_fixture()
        self.critique(project)
        folder = self.root / "sheets"
        self.env["VESPER_TEST_SHEETS"] = str(folder)
        self.cli("--project", project, "approve", "--digest", self.cli("--project", project, "review", "--json")["digest"])
        approved = sheets(folder, "approve-plan")[-1]
        self.assertIn("What changed: first approval", approved)
        for field in ("Requirements", "Jobs", "Critique: approve, 0 blockers", "Digest:"):
            self.assertIn(field, approved)
        api = project / "checks" / "api.py"
        before = len(api.read_text().splitlines())
        api.write_text(api.read_text() + "# one more line\n")
        self.text(project, "review")  # printing a sheet never moves the baseline
        sheet = self.text(project, "review")
        self.assertIn("checks/api.py", sheet)
        self.assertIn(f"{before} → {before + 1} lines", sheet)
        self.assertNotIn("first approval", sheet)


if __name__ == "__main__":
    unittest.main()
