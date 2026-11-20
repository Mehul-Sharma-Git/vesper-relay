"""P2-T6: additive checks after approval (amendments chained to the approval digest)."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)
import test_builder
import test_rc1

from builder.contracts import BuilderError
from builder.runner import Runner

THIRD = ("from pathlib import Path\nimport sys\n"
         "print('G3 ran')\n"
         "assert (Path(sys.argv[1]) / 'first.txt').read_text() == {expected!r}\n")


class AddCheckTests(unittest.TestCase):
    Base = test_builder.BuilderTests
    setUp, write_plan, args, command = Base.setUp, Base.write_plan, Base.args, Base.command
    approve, candidate = Base.approve, Base.candidate

    def script(self, name="third.py", expected="one"):
        path = self.project.parent / name
        path.write_text(THIRD.format(expected=expected))
        return path

    def add(self, *extra, code=0, env=None):
        return self.command("add-check", *extra, code=code, env=env)

    def add_third(self, jobs="J1", **options):
        return self.add("--id", "G3", "--script", str(self.script(**options)), "--jobs", jobs,
                        "--reason", "QA: first.txt must hold exactly one")

    def submit(self, job, files, code=0):
        attempt, workspace = self.candidate(job)
        for name, text in files.items():
            (workspace / name).write_text(text)
        return attempt, workspace, self.command("submit", attempt["id"], code=code)

    def amendments(self):
        folder = self.project / ".builder" / "amendments"
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []

    def test_added_check_runs_on_the_next_verification(self):
        self.approve()
        self.add_third()
        attempt, workspace = self.candidate("J1")
        # The worker sees the new gate too, read-only, and its brief says how to run it.
        self.assertTrue((workspace / ".vesper-gates" / "third.py").is_file())
        self.assertIn("G3", Path(attempt["brief"]).read_text())
        (workspace / "first.txt").write_text("one")
        result = self.command("submit", attempt["id"])
        self.assertEqual(result["outcome"], "accepted")
        self.assertEqual([item["id"] for item in result["checks"]], ["G1", "G3"])
        log = next(item["log"] for item in result["checks"] if item["id"] == "G3")
        self.assertIn("G3 ran", (self.project / log).read_text())
        # The final job runs every gate, the added one included.
        _, _, final = self.submit("J2", {"second.txt": "two"})
        self.assertEqual([item["id"] for item in final["checks"]], ["G1", "G2", "G3"])
        self.assertEqual(self.command("status")["status"], "complete")

    def test_added_check_can_reject_a_candidate(self):
        self.approve()
        self.add_third(expected="uno")
        _, _, result = self.submit("J1", {"first.txt": "one"}, code=1)
        self.assertEqual(result["outcome"], "rejected")
        self.assertIn("Check G3 exited", result["reason"])

    def test_editing_an_approved_check_file_is_still_detected(self):
        self.approve()
        self.add_third(jobs="J2")
        approved = next((self.project / ".builder" / "approvals").iterdir()) / "checks" / "first.py"
        amended = self.project / ".builder" / "amendments" / self.amendments()[0]
        for path, message in ((approved, "Frozen approval files have changed"),
                              (amended / "checks" / "first.py", "Amendment 1 .*changed"),
                              (amended / "checks" / "third.py", "Amendment 1 .*changed"),
                              (amended / "amendment.json", "Amendment 1 .*changed")):
            original = path.read_bytes()
            path.write_bytes(original.replace(b"one", b"ONE").replace(b"QA", b"qa"))
            self.assertRegex(self.command("status", code=2), message)
            self.command("prepare", code=2)
            path.write_bytes(original)
        self.assertEqual(self.command("status")["status"], "ready")

    def test_amendment_cannot_touch_an_accepted_job_or_an_existing_check(self):
        self.approve()
        self.submit("J1", {"first.txt": "one"})
        script = str(self.script())
        refusals = [
            (["--id", "G3", "--script", script, "--jobs", "J1"], "J1 is already accepted"),
            (["--id", "G3", "--script", script, "--jobs", "J2,J1"], "J1 is already accepted"),
            (["--id", "G1", "--script", script, "--jobs", "J2"], "G1 already exists"),
            (["--id", "G2", "--command", "python3 -c pass", "--jobs", "J2"], "G2 already exists"),
            (["--id", "G3", "--script", str(self.script("first.py")), "--jobs", "J2"],
             "first.py is already in the approved checks"),
            (["--id", "G3", "--script", script, "--jobs", "J9"], "Unknown job J9"),
            (["--id", "G3", "--command", "/bin/sh -c true", "--jobs", "J2"], "bare program name"),
            (["--id", "G3", "--script", str(self.project.parent / "missing.py"), "--jobs", "J2"],
             "Check script not found"),
        ]
        for extra, message in refusals:
            with self.subTest(extra=extra):
                self.assertIn(message, self.add(*extra, "--reason", "why", code=2))
        self.assertEqual(self.amendments(), [])
        self.assertEqual(self.command("status")["amendments"], [])

    def test_amendment_cannot_touch_a_job_whose_candidate_awaits_review(self):
        self.approve()
        self.candidate("J1")
        runner = Runner(self.project.resolve())
        state = runner.state()
        state["active"]["review"] = {"candidate_digest": "0" * 64}
        runner.save(state)
        with runner.lock(), self.assertRaisesRegex(BuilderError, "awaits independent review"):
            runner.add_check("G3", script=self.script(), jobs=["J1"], reason="why")
        self.assertEqual(self.amendments(), [])

    def test_add_check_needs_jobs_and_a_reason(self):
        self.approve()
        script = str(self.script())
        self.assertIn("--jobs", self.add("--id", "G3", "--script", script, "--reason", "why", code=2))
        self.assertIn("--reason", self.add("--id", "G3", "--script", script, "--jobs", "J1", code=2))
        self.assertIn("reason", self.add("--id", "G3", "--script", script, "--jobs", "J1",
                                         "--reason", "   ", code=2))
        self.assertIn("--jobs", self.add("--id", "G3", "--script", script, "--jobs", ",",
                                         "--reason", "why", code=2))
        self.assertEqual(self.amendments(), [])

    def test_add_check_is_refused_before_approval(self):
        self.assertIn("Approve", self.add("--id", "G3", "--script", str(self.script()), "--jobs", "J1",
                                          "--reason", "why", code=2))

    def test_confirmer_receives_the_add_check_sheet(self):
        self.approve()
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, "VESPER_TEST_SHEETS": folder}
            refused = {**env, "VESPER_TEST_CONFIRM_ANSWER": "no"}
            self.assertIn("not confirmed", self.add("--id", "G3", "--script", str(self.script()),
                                                    "--jobs", "J1,J2", "--reason", "QA: exact text", code=2,
                                                    env=refused))
            self.assertEqual(self.amendments(), [])
            first = self.add("--id", "G3", "--script", str(self.script()), "--jobs", "J1,J2",
                             "--reason", "QA: exact text", env=env)
            self.add("--id", "G4", "--command", "python3 -c 'print(4)'", "--jobs", "J2",
                     "--reason", "QA: smoke the CLI", env=env)
            sheets = [path.read_text() for path in sorted(Path(folder).glob("*-add-check.txt"))]
        self.assertEqual(len(sheets), 3)
        script_sheet, command_sheet = sheets[1], sheets[2]
        for field in ("G3", "third.py", "J1, J2", "QA: exact text", "What changed: first confirmation",
                      "Digest: " + first["amendment"]["digest"][:12]):
            self.assertIn(field, script_sheet)
        for field in ("G4", "python3 -c 'print(4)'", "J2", "QA: smoke the CLI",
                      "added   amendments/002-G4/amendment.json"):
            self.assertIn(field, command_sheet)
        self.assertNotRegex(script_sheet + command_sheet, r"\b[0-9a-f]{16,}\b")

    def test_status_lists_amendments_chained_to_the_approval(self):
        self.approve()
        approval = self.command("status")["digest"]
        first = self.add_third(jobs="J2")["amendment"]
        second = self.add("--id", "G4", "--command", "python3 -c pass", "--jobs", "J1,J2",
                          "--reason", "QA: smoke")["amendment"]
        listed = self.command("status")["amendments"]
        self.assertEqual([(item["sequence"], item["check"]["id"], item["jobs"]) for item in listed],
                         [(1, "G3", ["J2"]), (2, "G4", ["J1", "J2"])])
        self.assertEqual([item["reason"] for item in listed], ["QA: first.txt must hold exactly one", "QA: smoke"])
        self.assertEqual(listed[1]["check"]["command"], ["python3", "-c", "pass"])
        self.assertEqual((listed[0]["digest"], listed[1]["digest"]), (first["digest"], second["digest"]))
        self.assertEqual((listed[0]["previous"], listed[1]["previous"]), (approval, first["digest"]))
        self.assertEqual([item["confirmer"] for item in listed], ["test-stand-in"] * 2)
        records = json.loads((self.project / ".builder" / "confirmations.json").read_text())
        self.assertEqual([item["digest"] for item in records if item["action"] == "add-check"],
                         [first["digest"], second["digest"]])
        # Reordering the chain is detected.
        state_file = self.project / ".builder" / "state.json"
        state = json.loads(state_file.read_text())
        state["amendments"].reverse()
        state_file.write_text(json.dumps(state))
        self.assertRegex(self.command("status", code=2), "Amendment 1 .*changed")

    def test_amendment_digest_binds_the_check_jobs_and_reason(self):
        self.approve()
        amendment = self.add_third(jobs="J2")["amendment"]
        folder = self.project / ".builder" / "amendments" / self.amendments()[0]
        record = json.loads((folder / "amendment.json").read_text())
        self.assertEqual(record["check"], {"id": "G3", "script": "third.py"})
        self.assertEqual((record["jobs"], record["reason"]), (["J2"], "QA: first.txt must hold exactly one"))
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", amendment["digest"]))
        self.assertEqual(record["previous"], self.command("status")["digest"])


class ReviewedRunTests(unittest.TestCase):
    """Through the `vesper` door, on a run with independent review."""
    Base = test_rc1.TeamTests
    setUp, cli, git, plan, approve, submit, write_report = (Base.setUp, Base.cli, Base.git, Base.plan,
                                                            Base.approve, Base.submit, Base.write_report)

    def test_reviewer_copy_holds_the_added_check_and_its_log(self):
        project, command = self.plan()
        self.approve(command)
        script = self.root / "extra.py"
        script.write_text("print('EXTRA RAN')\n")
        command("add-check", "--id", "G_EXTRA", "--script", str(script), "--jobs", "J1", "--reason", "QA: extra")
        _, preview = self.submit(command)
        self.assertEqual([item["id"] for item in preview["checks"]], ["G1", "G_EXTRA"])
        review = Path(preview["review"]["workspace"])
        self.assertTrue((review / "checks" / "gate.py").is_file())
        self.assertEqual((review / "checks" / "extra.py").read_text(), script.read_text())
        self.assertIn("EXTRA RAN", (review / "logs" / "G_EXTRA.log").read_text())
        command("review-candidate", "--report", self.write_report(test_rc1.verdict(preview)), "--attest-independent")
        status = command("status")
        self.assertEqual(status["status"], "complete")
        self.assertEqual([item["check"]["id"] for item in status["amendments"]], ["G_EXTRA"])


if __name__ == "__main__":
    unittest.main()
