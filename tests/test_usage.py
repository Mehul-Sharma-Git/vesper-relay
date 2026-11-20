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
import test_scheduling
import test_vesper

from builder import usage
from builder.brains import ADAPTERS, Brain

START = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)
BASE = 0.5  # session % per 1k tokens in the synthetic data; the week moves a tenth as fast


def at(minutes):
    return (START + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def synthetic(runs, account="claude", model="sonnet", factors=(1.0, 0.92, 1.08, 0.97, 1.05, 1.0), marked=True):
    """Readings around each run and the run's calls in between, with a little noise in the rate.
    Readings are marked as bracketing the run (P2-T9) unless ``marked`` is false."""
    entries, session, week, clock = [], 10.0, 30.0, 0
    for index in range(runs):
        tokens = [4000 + 1000 * index, 2500]
        rate = BASE * factors[index % len(factors)]
        mark = (lambda side: {"mark": side, "run": f"run-{index}"}) if marked else (lambda side: {})
        entries.append({"kind": "reading", "account": account, "session": round(session, 2),
                        "week": round(week, 2), "at": at(clock), **mark("before")})
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
                        "week": round(week, 2), "at": at(clock), **mark("after")})
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


class MarkedReadingTests(unittest.TestCase):
    """P2-T9: only readings marked as bracketing Vesper's own work calibrate."""

    def test_a_marked_pair_calibrates_and_unmarked_pairs_never_do(self):
        self.assertEqual(len(usage.calibrate(synthetic(3))[("claude", "sonnet")]), 3)
        unmarked = synthetic(6, marked=False)  # can include the host assistant's own use
        self.assertEqual(usage.calibrate(unmarked), {})
        result = EstimateTests().estimate(unmarked)
        self.assertFalse(result["accounts"]["claude"]["calibrated"])
        self.assertIn("uncalibrated", usage.render(result))

    def test_a_pair_needs_the_same_run_and_no_reading_between(self):
        rows = synthetic(1)
        rows[-1]["run"] = "run-other"
        self.assertEqual(usage.calibrate(rows), {})
        rows = synthetic(1)
        rows.insert(3, {"kind": "reading", "account": "claude", "session": 11, "week": 30.1, "at": at(9)})
        self.assertEqual(usage.calibrate(rows), {})


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

    def test_marked_readings_name_a_run_folder(self):
        from builder.contracts import BuilderError
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder) / "run"
            (run / "plan").mkdir(parents=True)
            usage.record_reading("claude", 10, 20, before=run / "plan" / "..")
            usage.record_reading("claude", 12, 21, after=run)
            first, second = usage.entries()
            self.assertEqual((first["mark"], first["run"]), ("before", str(run.resolve())))
            self.assertEqual((second["mark"], second["run"]), ("after", str(run.resolve())))
            with self.assertRaisesRegex(BuilderError, "not a Vesper run"):
                usage.record_reading("claude", 10, 20, before=Path(folder))
            with self.assertRaisesRegex(BuilderError, "before or after"):
                usage.record_reading("claude", 10, 20, before=run, after=run)

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


APPROVED = at(100)
RUN = "/runs/pocket-todo"


def kept(session=(5.0, 8.0), week=(0.5, 0.8)):
    """An approval's kept estimate (P2-T9) for one Claude account."""
    entry = {"calls": [2, 4], "tokens": [10000, 16000], "calibrated": True, "confidence": "low",
             "calibrated_runs": 2, "session": list(session), "week": list(week)}
    return {"approved_at": APPROVED, "estimate": {"jobs": 1, "calls": [2, 4], "accounts": {"claude": entry}}}


def part(start, session, rise, week=10, week_rise=0.6, run=RUN, calls=1):
    """A marked pair around one stretch of the run's work, `start` minutes after START."""
    rows = [{"kind": "reading", "account": "claude", "session": session, "week": week, "at": at(start),
             "mark": "before", "run": run}]
    for number in range(calls):
        rows.append({"kind": "call", "run": run, "job": "J1", "role": "backend", "brain": "strong",
                     "adapter": "claude-code", "account": "claude", "model": "sonnet", "effort": None,
                     "start": at(start + 1 + 2 * number), "end": at(start + 2 + 2 * number), "tokens": 3000})
    rows.append({"kind": "reading", "account": "claude", "session": session + rise, "week": week + week_rise,
                 "at": at(start + 2 + 2 * calls), "mark": "after", "run": run})
    return rows


class UsageCheckTests(unittest.TestCase):
    """`usage check`: a run's observed rise after approval against the estimate approve kept."""

    def check(self, rows, state=None):
        return usage.check_run(RUN, state or kept(), rows)

    def results(self, report, limit="session"):
        return report["accounts"]["claude"][limit]["result"]

    def test_a_paused_runs_two_marked_parts_are_summed(self):
        rows = part(110, 20, 3) + part(400, 23, 3)  # paused for limits between the two
        report = self.check(rows)
        session = report["accounts"]["claude"]["session"]
        self.assertEqual((session["observed"], session["parts"], session["result"]), (6, 2, "inside"))
        self.assertEqual(report["accounts"]["claude"]["week"]["observed"], 1.2)
        self.assertEqual(report["result"], "inside")

    def test_a_pair_around_review_plan_calibrates_but_is_left_out_of_the_check(self):
        critique = part(10, 10, 9, run=RUN)  # before approval: the critique's own usage
        self.assertEqual(len(usage.calibrate(critique)[("claude", "sonnet")]), 1)
        report = self.check(critique + part(110, 20, 6))
        self.assertEqual(report["accounts"]["claude"]["session"]["observed"], 6)
        self.assertEqual(report["accounts"]["claude"]["session"]["parts"], 1)

    def test_one_reading_step_outside_the_band_counts_as_inside(self):
        self.assertEqual(self.results(self.check(part(110, 20, 4))), "inside")  # band 5–8: one step below
        self.assertEqual(self.results(self.check(part(110, 20, 3))), "below")  # two steps below
        self.assertEqual(self.results(self.check(part(110, 20, 9))), "inside")
        self.assertEqual(self.results(self.check(part(110, 20, 10))), "above")
        self.assertEqual(self.check(part(110, 20, 10))["result"], "outside")

    def test_a_part_without_marked_readings_is_unchecked(self):
        rows = part(110, 20, 3)
        stray = dict(rows[1], start=at(300), end=at(301))  # a second part nobody bracketed
        report = self.check(rows + [stray])
        self.assertEqual(self.results(report), "unchecked")
        self.assertIn("not bracketed", report["accounts"]["claude"]["session"]["reason"])
        self.assertEqual(report["result"], "unchecked")
        opened = part(110, 20, 3)[:-1]  # a before reading with no after yet
        self.assertEqual(self.results(self.check(opened)), "unchecked")
        self.assertEqual(self.results(self.check([])), "unchecked")

    def test_a_run_approved_without_a_band_is_unchecked(self):
        state = kept()
        entry = state["estimate"]["accounts"]["claude"]
        for key in ("session", "week", "confidence", "calibrated_runs"):
            entry.pop(key)
        entry["calibrated"] = False
        report = self.check(part(110, 20, 6), state)
        self.assertEqual((self.results(report), self.results(report, "week")), ("unchecked", "unchecked"))
        self.assertIn("no band", report["accounts"]["claude"]["session"]["reason"])
        report = self.check(part(110, 20, 6), {"approved_at": APPROVED})  # approved before P2-T9
        self.assertEqual(report["result"], "unchecked")

    def test_a_reset_inside_a_part_leaves_that_limit_unchecked(self):
        report = self.check(part(110, 90, -85))
        self.assertEqual(self.results(report), "unchecked")
        self.assertEqual(self.results(report, "week"), "inside")


class ApprovalKeepsEstimateTests(unittest.TestCase):
    # Looked up when called: test_scheduling imports this module too.
    def setUp(self):
        test_scheduling.SchedulingTests.setUp(self)

    def control(self, *args, **kwargs):
        return test_scheduling.SchedulingTests.control(self, *args, **kwargs)

    def run_jobs(self, **options):
        return test_scheduling.SchedulingTests.run_jobs(self, **options)

    def test_the_approval_keeps_the_estimate_and_status_shows_the_check(self):
        from builder.contracts import review_bundle
        state = self.runner.state()
        contract, bundle = review_bundle(self.project)
        self.assertEqual(state["estimate"], usage.for_project(contract, bundle))
        self.assertTrue(state["estimate"]["accounts"]["claude"]["calibrated"])
        self.assertIn("session", state["estimate"]["accounts"]["claude"])
        self.assertNotIn("usage_check", self.runner.status())
        run = str(self.project.resolve())  # however the run folder is spelled
        usage.record_reading("claude", 10, 40, before=self.project)
        self.assertEqual(self.run_jobs()["status"], "complete")
        usage.record_reading("claude", 11, 40, after=self.project)
        status = self.runner.status()
        self.assertEqual(status["status"], "complete")
        self.assertEqual(status["usage_check"]["run"], run)
        self.assertIn(status["usage_check"]["result"], ("inside", "outside"))


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

    def test_usage_check_command_reports_the_run(self):
        project = self.plan_only()
        self.cli("usage", "record", "--account", "claude", "--session", "40", "--week", "13",
                 "--before", str(project))
        reading = self.ledger()[-1]
        self.assertEqual((reading["mark"], reading["run"]), ("before", str(project.resolve())))
        report = self.cli("--project", project, "usage", "check")
        self.assertEqual(report["result"], "unchecked")  # not approved yet
        self.assertIn("--before", self.cli("usage", "record", "--account", "claude", "--session", "1",
                                           "--week", "1", "--before", str(project), "--after", str(project),
                                           code=2))

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
