"""Configurable gate timeouts and reviewer limits (P1-T3)."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.contracts import BuilderError
from builder.providers import provider_command, review_limits
from builder.runner import Runner

import test_builder
import test_rc1
from test_rc1 import verdict

SLOW_GATE = ("import time\ntime.sleep(1.5)\n"
             "from pathlib import Path\nimport sys\n"
             "assert (Path(sys.argv[1]) / 'first.txt').read_text() == 'one'\n")


class CheckTimeoutTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    write_plan = test_builder.BuilderTests.write_plan
    args = test_builder.BuilderTests.args
    command = test_builder.BuilderTests.command
    approve = test_builder.BuilderTests.approve
    candidate = test_builder.BuilderTests.candidate

    def test_invalid_check_timeout_is_rejected_at_review(self):
        for value in (0, 1801, -5, "60", True, 1.5, None):
            with self.subTest(value=value):
                self.plan["checks"][0]["timeout"] = value
                self.write_plan()
                self.assertIn("Invalid timeout for check G1", self.command("review", code=2))
        for value in (1, 1800):
            with self.subTest(value=value):
                self.plan["checks"][0]["timeout"] = value
                self.write_plan()
                self.command("review")

    def test_check_timeout_is_part_of_the_digest(self):
        before = self.command("review")["digest"]
        self.plan["checks"][0]["timeout"] = 60
        self.write_plan()
        self.assertNotEqual(self.command("review")["digest"], before)

    def submit_slow_gate(self, timeout):
        (self.project / "checks" / "first.py").write_text(SLOW_GATE)
        self.plan["checks"][0]["timeout"] = timeout
        self.write_plan()
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        return attempt

    def test_slow_gate_fails_past_its_timeout(self):
        attempt = self.submit_slow_gate(1)
        result = self.command("submit", attempt["id"], code=1)
        self.assertEqual(result["checks"][0]["exit_code"], 124)
        self.assertEqual(self.command("status")["completed"], [])

    def test_slow_gate_passes_within_its_timeout(self):
        attempt = self.submit_slow_gate(5)
        self.command("submit", attempt["id"])
        self.assertEqual(self.command("status")["completed"], ["J1"])


class RunCheckDefaultTests(unittest.TestCase):
    def timeout_for(self, check):
        seen = []

        def fake_execute(*args, timeout):
            seen.append(timeout)
            args[5].write_text("")
            return 0, True

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "candidate").mkdir()
            (root / "attempt").mkdir()
            runner = mock.MagicMock(root=root)
            runner.approval.return_value = root / "approval"
            state = {"bundle": {"checks": {}}, "active": {"checks": []}}
            with mock.patch("builder.runner.execute_check", fake_execute):
                Runner.run_check(runner, state, check, root / "candidate", root / "attempt", None)
        return seen[0]

    def test_defaults_and_explicit_timeouts(self):
        self.assertEqual(self.timeout_for({"id": "G1", "script": "g.py"}), 45)
        self.assertEqual(self.timeout_for({"id": "VESPER_REGRESSION", "script": "vesper_regression.py"}), 300)
        self.assertEqual(self.timeout_for({"id": "G1", "script": "g.py", "timeout": 60}), 60)
        self.assertEqual(self.timeout_for({"id": "VESPER_REGRESSION", "script": "v.py", "timeout": 900}), 900)


class ReviewerLimitTests(unittest.TestCase):
    def command(self, name, **kwargs):
        with mock.patch("builder.providers.shutil.which", return_value="/usr/local/bin/" + name):
            return provider_command(name, None, True, operation="reviewer", **kwargs)

    def test_reviewer_command_carries_the_chosen_max_turns(self):
        command = self.command("claude", max_turns=7)
        self.assertEqual(command[command.index("--max-turns") + 1], "7")
        default = self.command("claude")
        self.assertEqual(default[default.index("--max-turns") + 1], "20")

    def test_review_limits_are_bounded(self):
        self.assertEqual(review_limits(), (180, 20))
        self.assertEqual(review_limits(1800, 100), (1800, 100))
        for timeout, turns in ((0, 20), (1801, 20), (180, 0), (180, 101), (True, 20), (180, 2.0)):
            with self.subTest(timeout=timeout, turns=turns):
                with self.assertRaises(BuilderError):
                    review_limits(timeout, turns)
        with self.assertRaises(BuilderError):
            self.command("claude", max_turns=101)


class ReviewCandidateLimitTests(unittest.TestCase):
    setUp = test_rc1.TeamTests.setUp
    cli = test_rc1.TeamTests.cli
    git = test_rc1.TeamTests.git
    plan = test_rc1.TeamTests.plan
    approve = test_rc1.TeamTests.approve
    submit = test_rc1.TeamTests.submit

    def fake_claude(self, report):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        exe = bin_dir / "claude"
        exe.write_text(f"#!{sys.executable}\n"
                       "import sys\nfrom pathlib import Path\n"
                       "sys.stdin.read()\n"
                       "turns = sys.argv[sys.argv.index('--max-turns') + 1]\n"
                       f"Path({str(self.root / 'turns.txt')!r}).write_text(turns)\n"
                       f"print(Path({str(report)!r}).read_text())\n")
        exe.chmod(0o700)
        self.env["PATH"] = str(bin_dir) + os.pathsep + self.env["PATH"]

    def test_review_candidate_cli_passes_max_turns_and_bounds_limits(self):
        _, command = self.plan()
        self.approve(command)
        _, preview = self.submit(command)
        report = self.root / "verdict.json"
        report.write_text(json.dumps(verdict(preview)))
        self.fake_claude(report)
        reviewer = ("review-candidate", "--provider", "claude", "--trust-host")
        self.assertIn("Review max turns", command(*reviewer, "--review-max-turns", "101", code=2))
        self.assertIn("Review timeout", command(*reviewer, "--review-timeout", "1801", code=2))
        self.assertEqual(command("status")["status"], "awaiting_review")
        command(*reviewer, "--review-timeout", "30", "--review-max-turns", "7")
        self.assertEqual((self.root / "turns.txt").read_text(), "7")
        self.assertEqual(command("status")["status"], "complete")

    def test_review_candidate_passes_the_timeout_to_the_reviewer_process(self):
        project, command = self.plan()
        self.approve(command)
        _, preview = self.submit(command)
        seen = {}

        def fake_run(command, *, cwd, input_text, env, log, timeout):
            seen.update(turns=command[command.index("--max-turns") + 1], timeout=timeout)
            log.write_text(json.dumps(verdict(preview)))
            return 0

        with mock.patch("builder.providers.shutil.which", return_value="/usr/local/bin/claude"), \
                mock.patch("builder.runner.run_process", fake_run), \
                mock.patch.dict(os.environ, {"VESPER_STATE_DIR": self.env["VESPER_STATE_DIR"]}):
            result = Runner(project).review_candidate(provider="claude", trust_host=True,
                                                      review_timeout=600, review_max_turns=7)
        self.assertEqual(seen, {"turns": "7", "timeout": 600})
        self.assertEqual(result["outcome"], "accepted")

    def test_run_rejects_out_of_range_limits_before_work(self):
        _, command = self.plan()
        self.approve(command)
        run = ("run", "--provider", "claude", "--trust-host")
        self.assertIn("Review max turns", command(*run, "--review-max-turns", "0", code=2))
        self.assertIn("Review timeout", command(*run, "--review-timeout", "0", code=2))
        self.assertEqual(command("status")["attempts"], [])


class ReviewPlanLimitTests(unittest.TestCase):
    def setUp(self):
        from tests.test_planning import PlanningTests
        self.case = PlanningTests("test_canonical_contract_reaches_worker")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.full()

    def test_review_plan_threads_timeout_and_max_turns(self):
        from builder.planning import review_plan
        template = self.case.report()
        seen = {}

        def fake_run(command, *, cwd, input_text, env, log, timeout):
            identity = re.search(r'"reviewer": "(reviewer-[0-9a-f]+)"', input_text).group(1)
            seen.update(turns=command[command.index("--max-turns") + 1], timeout=timeout)
            log.write_text(json.dumps({**template, "reviewer": identity}))
            return 0

        with mock.patch("builder.providers.shutil.which", return_value="/usr/local/bin/claude"), \
                mock.patch("builder.process.run_process", fake_run):
            review_plan(self.case.runner, provider="claude", trust_host=True,
                        review_timeout=600, review_max_turns=9)
        self.assertEqual(seen, {"turns": "9", "timeout": 600})

    def test_out_of_range_limits_do_not_spend_critique_attempts(self):
        from builder.planning import review_plan
        for _ in range(3):
            with self.assertRaisesRegex(BuilderError, "Review max turns"):
                review_plan(self.case.runner, provider="claude", trust_host=True, review_max_turns=101)
        review_plan(self.case.runner, report=self.case.report(), external_attested=True)

    def test_vesper_review_plan_cli_accepts_the_flags(self):
        import subprocess
        result = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "--project", str(self.case.root),
                                 "review-plan", "--provider", "claude", "--trust-host",
                                 "--review-timeout", "0"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Review timeout", result.stderr)


if __name__ == "__main__":
    unittest.main()
