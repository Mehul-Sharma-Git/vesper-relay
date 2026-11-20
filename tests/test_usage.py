"""P2-T3: usage ledger and plan-limit estimates, in % of the owner's limits and wall time."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import stand_in  # noqa: F401
import test_vesper

from builder import usage
from builder.brains import ADAPTERS, Brain

START = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)
BASE = 0.5  # session % per 1k tokens in the synthetic data; the week moves a tenth as fast


def at(minutes):
    return (START + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def synthetic(runs, account="claude", model="sonnet", factors=(1.0, 0.92, 1.08, 0.97, 1.05, 1.0)):
    """Readings around each run and the run's calls in between, with a little noise in the rate."""
    entries, session, week, clock = [], 10.0, 30.0, 0
    for index in range(runs):
        tokens = [4000 + 1000 * index, 2500]
        rate = BASE * factors[index % len(factors)]
        entries.append({"kind": "reading", "account": account, "session": round(session, 2),
                        "week": round(week, 2), "at": at(clock)})
        for number, count in enumerate(tokens):
            entries.append({"kind": "call", "run": f"run-{index}", "job": "J1",
                            "role": "worker" if number == 0 else "reviewer", "brain": "strong",
                            "adapter": "claude-code", "account": account, "model": model, "effort": None,
                            "start": at(clock + 1 + 5 * number), "end": at(clock + 4 + 5 * number),
                            "tokens": count})
        session += rate * sum(tokens) / 1000
        week += rate / 10 * sum(tokens) / 1000
        clock += 20
        entries.append({"kind": "reading", "account": account, "session": round(session, 2),
                        "week": round(week, 2), "at": at(clock)})
        clock += 30
    return entries


class CalibrationTests(unittest.TestCase):
    def test_band_contains_the_observed_value_in_a_held_out_run(self):
        entries = synthetic(6)  # each run: a reading, two calls, a reading
        calibration = usage.calibrate(entries[:-4])
        self.assertEqual(len(calibration[("claude", "sonnet")]), 5)
        before, *calls, after = entries[-4:]
        tokens = sum(call["tokens"] for call in calls)
        for kind in ("session", "week"):
            low, high = usage.percent_band(calibration, "claude", "sonnet", tokens, kind)
            observed = after[kind] - before[kind]
            self.assertLessEqual(low, observed, kind)
            self.assertGreaterEqual(high, observed, kind)
            self.assertLess(low, high)

    def test_a_reset_between_readings_is_not_a_sample(self):
        entries = synthetic(2)
        entries[-1]["session"] = 1.0  # the 5-hour session window reset during the run
        calibration = usage.calibrate(entries)
        self.assertEqual([sample.get("session") is None for sample in calibration[("claude", "sonnet")]],
                         [False, True])

    def test_mixed_models_calibrate_the_account_only(self):
        entries = synthetic(1)
        entries[2]["model"] = "opus"
        calibration = usage.calibrate(entries)
        self.assertIn(("claude", None), calibration)
        self.assertNotIn(("claude", "sonnet"), calibration)
        self.assertIsNotNone(usage.percent_band(calibration, "claude", "sonnet", 1000, "session"))

    def test_confidence_is_low_below_five_calibrated_runs(self):
        self.assertEqual(usage.confidence(usage.calibrate(synthetic(4))[("claude", "sonnet")]), "low")
        self.assertNotEqual(usage.confidence(usage.calibrate(synthetic(5))[("claude", "sonnet")]), "low")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patch = mock.patch.dict(os.environ, {"VESPER_STATE_DIR": temp.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.ledger = Path(temp.name) / "usage.jsonl"

    def test_a_launch_that_never_starts_is_not_a_call(self):
        from builder.brains import launch
        from builder.contracts import BuilderError
        with tempfile.TemporaryDirectory() as work, self.assertRaises(BuilderError):
            launch(Brain("strong", ADAPTERS["claude-code"], "sonnet"), "worker", None, False, work=Path(work),
                   input_text="", log=Path(work) / "log", timeout=5, ledger={"run": "r", "job": "J", "role": "x"})
        self.assertEqual(usage.entries(), [])

    def test_readings_name_a_known_account(self):
        from builder.contracts import BuilderError
        usage.record_reading(" Claude ", 10, 20)
        self.assertEqual(usage.entries()[-1]["account"], "claude")
        with self.assertRaisesRegex(BuilderError, "claude, chatgpt or gemini"):
            usage.record_reading("cluade", 10, 20)

    def test_malformed_rows_are_skipped(self):
        rows = synthetic(5)
        self.ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n"
                               + json.dumps({"kind": "reading", "account": "claude"}) + "\n"
                               + json.dumps({"kind": "call", "account": "claude", "tokens": 5}) + "\n{torn")
        self.assertEqual(len(usage.entries()), len(rows))
        self.assertEqual(len(usage.calibrate(usage.entries())[("claude", "sonnet")]), 5)


class EstimateTests(unittest.TestCase):
    contract = {"title": "Pocket Todo", "delivery": "app", "requirements": [],
                "checks": [{"id": "G1", "script": "g.py"}],
                "jobs": [{"id": "J_API", "role": "backend", "paths": ["server.py"], "depends_on": [],
                          "checks": ["G1"], "max_attempts": 2},
                         {"id": "J_UI", "role": "frontend", "paths": ["app.js"], "depends_on": ["J_API"],
                          "checks": ["G1"]}]}
    bundle = {"team": {}, "planning": {"depth": "skip"}}
    claude = Brain("strong", ADAPTERS["claude-code"], "sonnet")

    def estimate(self, entries):
        return usage.estimate(self.contract, self.bundle, entries, brains=lambda role: self.claude, reserve=25)

    def test_without_calibration_the_estimate_says_uncalibrated_and_shows_tokens_and_time(self):
        calls = [item for item in synthetic(3) if item["kind"] == "call"]
        result = self.estimate(calls)
        self.assertEqual((result["jobs"], result["calls"]), (2, [4, 8]))
        account = result["accounts"]["claude"]
        self.assertFalse(account["calibrated"])
        self.assertNotIn("session", account)
        self.assertGreater(account["tokens"][1], account["tokens"][0])
        text = usage.render(result)
        self.assertIn("uncalibrated", text)
        self.assertIn("tokens", text)
        self.assertIn("wall time", text)
        self.assertNotIn("%", text)
        self.assertIn("unknown", usage.render(self.estimate([])))

    def test_calibrated_estimate_shows_percent_bands_and_sessions_needed(self):
        result = self.estimate(synthetic(6))
        account = result["accounts"]["claude"]
        self.assertTrue(account["calibrated"])
        low, high = account["session"]
        self.assertLess(0, low)
        self.assertLess(low, high)
        self.assertEqual(account["confidence"], "medium")
        self.assertGreaterEqual(account["sessions_needed"], 1)
        text = usage.render(result)
        self.assertRegex(text, r"session \d+(\.\d)?–\d+(\.\d)?%")
        self.assertIn("weekly", text)
        self.assertNotIn("$", text)


class CommandTests(unittest.TestCase):
    setUp = test_vesper.VesperTests.setUp
    cli = test_vesper.VesperTests.cli
    git = test_vesper.VesperTests.git

    def ledger(self):
        path = Path(self.env["VESPER_STATE_DIR"]) / "usage.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_usage_record_logs_an_observed_reading(self):
        self.cli("usage", "record", "--account", "claude", "--session", "42", "--week", "13")
        reading = self.ledger()[-1]
        self.assertEqual((reading["kind"], reading["account"], reading["session"], reading["week"]),
                         ("reading", "claude", 42, 13))
        self.assertTrue(reading["at"])
        self.assertEqual(os.stat(Path(self.env["VESPER_STATE_DIR"]) / "usage.jsonl").st_mode & 0o777, 0o600)
        self.assertIn("between 0 and 100", self.cli("usage", "record", "--account", "claude", "--session", "142",
                                                    "--week", "13", code=2))

    def test_estimate_command_and_review_sheet_show_the_estimate(self):
        project = self.plan_only()
        text = subprocess.run([sys.executable, "-B", str(test_vesper.ROOT / "vesper.py"), "--project", str(project),
                               "estimate"], cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("Estimate", text.stdout)
        data = self.cli("--project", project, "estimate", "--json")
        self.assertEqual(data["jobs"], 1)
        sheet = subprocess.run([sys.executable, "-B", str(test_vesper.ROOT / "vesper.py"), "--project",
                                str(project), "review"], cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertIn("Estimate", sheet.stdout)

    def plan_only(self):
        from test_planning import narrow
        project = Path(self.cli("start", "--mode", "bug", "--idea", "Spinner never stops")["project"])
        for name in ("product", "design", "architecture", "decisions"):
            (project / "plan" / f"{name}.md").write_text("Spinner stops on failure.\n")
        narrow(project)
        contract = {"team": 1, "title": "Fix spinner", "delivery": "Git patch",
                    "requirements": [{"id": "R1", "description": "Spinner stops on failure", "checks": ["G1"]}],
                    "checks": [{"id": "G1", "script": "gate.py"}],
                    "jobs": [{"id": "J1", "role": "frontend", "goal": "Fix the spinner",
                              "paths": ["app.js"], "depends_on": [], "checks": ["G1"]}]}
        (project / "plan" / "contract.json").write_text(json.dumps(contract))
        (project / "checks" / "gate.py").write_text("assert True\n")
        return project


class TestIsolationTests(unittest.TestCase):
    def test_tests_never_write_the_owners_state(self):
        # P2-G: test runs had filled the owner's real usage ledger with stand-in calls.
        from builder.learning import state_home
        from builder.usage import ledger_path
        real = (Path.home() / ".local" / "state" / "vesper-relay").resolve()
        self.assertNotEqual(state_home(), real)
        self.assertNotIn(real, ledger_path().parents)


if __name__ == "__main__":
    unittest.main()
