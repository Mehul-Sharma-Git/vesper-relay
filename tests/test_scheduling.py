"""P2-T4: limit-aware scheduling. Pause before a job that would cross the reserve; never mid-job."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import stand_in  # noqa: F401
import test_usage

from build_local import initialize
from builder import usage
from builder.brains import ADAPTERS, Brain, Selection
from builder.runner import Runner

# A stand-in Claude worker: writes the job's file and reports the tokens the test chose.
WORKER = """
import json, sys
from pathlib import Path
prompt = sys.stdin.read()
home = Path(sys.argv[0]).resolve().parent.parent  # brains see a filtered environment: use files
control = json.loads((home / 'control.json').read_text())
state = home / 'calls.json'
calls = json.loads(state.read_text()) if state.exists() else []
job = 'J1' if 'Job J1' in prompt else 'J2'
calls.append(job)
state.write_text(json.dumps(calls))
fail_first = control.get('fail_first') == job and calls.count(job) == 1
if not fail_first:
    Path('first.txt' if job == 'J1' else 'second.txt').write_text('one' if job == 'J1' else 'two')
print(json.dumps({'type': 'result', 'result': 'done', 'usage': {'input_tokens': control['tokens'],
                                                                 'output_tokens': 0}}))
"""


class Clock:
    """A fake clock. Given a time it stands still there; given none it follows real time (as the
    ledger's call stamps do), and sleeping moves it forward."""
    def __init__(self, when=None):
        self.when = when
        self.offset = timedelta()

    def __call__(self):
        return (self.when or datetime.now(timezone.utc)) + self.offset

    def sleep(self, seconds):
        self.offset += timedelta(seconds=seconds)


def shifted(rows, days):
    """Synthetic history moved into the past, so it never overlaps the test's own calls."""
    keys = ("at", "start", "end")
    return [{**row, **{key: (datetime.fromisoformat(row[key]) + timedelta(days=days)).isoformat(timespec="seconds")
                       for key in keys if key in row}} for row in rows]


class ResetTests(unittest.TestCase):
    def test_next_reset_comes_from_the_last_recorded_reset(self):
        rows = [{"kind": "reading", "account": "claude", "session": 60, "week": 30, "at": test_usage.at(0)},
                {"kind": "reading", "account": "claude", "session": 4, "week": 31, "at": test_usage.at(90)}]
        now = test_usage.START + timedelta(minutes=100)
        self.assertEqual(usage.next_reset(rows, "claude", "session", now), test_usage.START + timedelta(minutes=90, hours=5))
        later = test_usage.START + timedelta(minutes=90, hours=11)
        self.assertEqual(usage.next_reset(rows, "claude", "session", later), test_usage.START + timedelta(minutes=90, hours=15))
        self.assertIsNone(usage.next_reset(rows, "claude", "week", now))

    def test_start_after_waits_for_the_next_such_time(self):
        clock = Clock(datetime(2026, 11, 20, 8, 0).astimezone())
        usage.wait_until("09:30", clock=clock, sleep=clock.sleep)
        self.assertEqual((clock().hour, clock().minute), (9, 30))
        usage.wait_until("09:00", clock=clock, sleep=clock.sleep)
        self.assertEqual((clock().day, clock().hour), (21, 9))
        with self.assertRaises(Exception):
            usage.wait_until("25:00", clock=clock, sleep=clock.sleep)


class CommandTests(unittest.TestCase):
    def test_run_refuses_a_bad_start_time(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "run"
            initialize(project, "Anything")
            done = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve().parents[1] / "build_local.py"),
                                   "--project", str(project), "run", "--start-after", "25:00"],
                                  capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("24-hour time", done.stderr)


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "claude").write_text(f"#!{sys.executable}\n" + WORKER)
        (bin_dir / "claude").chmod(0o700)
        config = self.root / "config.toml"
        config.write_text('[sandbox]\nbackend = "none"\n[limits]\nreserve_percent = 25\n')
        environ = mock.patch.dict(os.environ, {
            "VESPER_STATE_DIR": str(self.root / "state"), "VESPER_CONFIG": str(config),
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        environ.start()
        self.addCleanup(environ.stop)
        self.project = self.root / "project"
        initialize(self.project, "Write two files")
        for name in ("product", "design", "architecture", "decisions"):
            (self.project / "plan" / f"{name}.md").write_text("# Plan\n")
        (self.project / "checks" / "first.py").write_text(
            "from pathlib import Path\nimport sys\nassert (Path(sys.argv[1]) / 'first.txt').read_text() == 'one'\n")
        (self.project / "checks" / "last.py").write_text(
            "from pathlib import Path\nimport sys\nassert (Path(sys.argv[1]) / 'second.txt').read_text() == 'two'\n")
        (self.project / "plan" / "contract.json").write_text(json.dumps({
            "title": "Two files", "delivery": "local files",
            "requirements": [{"id": "R1", "description": "two files", "checks": ["G1", "G2"]}],
            "checks": [{"id": "G1", "script": "first.py"}, {"id": "G2", "script": "last.py"}],
            "jobs": [{"id": "J1", "role": "backend", "goal": "write first", "paths": ["first.txt"],
                      "depends_on": [], "checks": ["G1"], "max_attempts": 2},
                     {"id": "J2", "role": "frontend", "goal": "write second", "paths": ["second.txt"],
                      "depends_on": ["J1"], "checks": ["G2"], "max_attempts": 2}]}))
        self.runner = Runner(self.project)
        self.runner.approve(self.runner.review()["digest"])
        # Calibration: 0.5% of the session per 1k tokens, give or take; history has 4-9k-token calls.
        for row in shifted(test_usage.synthetic(6, model=None), days=-10):
            usage.append(row)
        self.clock = Clock()
        self.control(1000)

    def control(self, tokens, fail_first=None):
        (self.root / "control.json").write_text(json.dumps({"tokens": tokens, "fail_first": fail_first}))

    def reading(self, session, week=40, ago=None):
        when = self.clock() - (ago or timedelta())
        usage.append({"kind": "reading", "account": "claude", "session": session, "week": week,
                      "at": when.isoformat(timespec="seconds")})

    def run_jobs(self, **options):
        return self.runner.run(Selection(worker="claude-code", settings={}), trust_host=True, clock=self.clock,
                               sleep=self.clock.sleep, **options)

    def calls(self):
        path = self.root / "calls.json"
        return json.loads(path.read_text()) if path.exists() else []

    def test_pauses_before_the_job_that_would_cross_the_reserve_then_resumes_from_the_snapshot(self):
        self.reading(session=50)
        self.control(40000)  # J1 uses about 20% of the session
        result = self.run_jobs()
        self.assertEqual(result["status"], "paused_for_limits")
        self.assertEqual(result["completed"], ["J1"])
        pause = result["pause"]
        self.assertEqual((pause["job"], pause["account"], pause["limit"]), ("J2", "claude", "session"))
        self.assertGreater(pause["projected"], 75)
        self.assertGreater(pause["used_since"], 15)  # J1's own calls count against the window
        self.assertEqual(pause["threshold"], 75)
        self.assertIn("run again", pause["resume"])
        self.assertIn("resets_at", pause)
        self.assertEqual(self.calls(), ["J1"])
        self.assertEqual([item["job"] for item in self.runner.state()["attempts"]], ["J1"])
        # The window resets; run again picks up at J2 from the accepted snapshot.
        self.clock.sleep(60)
        self.reading(session=3)
        self.control(1000)
        result = self.run_jobs()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(self.calls(), ["J1", "J2"])
        self.assertEqual([item["job"] for item in self.runner.state()["attempts"]], ["J1", "J2"])

    def test_start_after_resumes_past_a_reset_without_a_new_reading(self):
        # A recorded reset 3 hours ago puts the next one 2 hours from now.
        self.reading(session=90, ago=timedelta(hours=4))
        self.reading(session=5, ago=timedelta(hours=3))
        self.reading(session=50, ago=timedelta(minutes=1))
        self.control(40000)
        pause = self.run_jobs()["pause"]
        self.assertEqual(pause["job"], "J2")
        reset = datetime.fromisoformat(pause["resets_at"])
        self.assertAlmostEqual((reset - self.clock()).total_seconds(), 2 * 3600, delta=120)
        local = reset.astimezone()
        self.assertEqual(pause["resets_at_local"], local.strftime("%Y-%m-%d %H:%M"))
        self.assertEqual(pause["start_after"], (local + timedelta(minutes=1)).strftime("%H:%M"))
        # Unattended: wait past the reset with --start-after, no new reading, and J2 runs.
        self.control(1000)
        result = self.run_jobs(start_after=pause["start_after"])
        self.assertEqual(result["status"], "complete")
        self.assertGreater(self.clock(), reset)

    def test_an_old_reset_never_hides_a_fresh_high_reading(self):
        # Review round 2: windows start at first use, so a reset recorded long ago, rolled forward
        # in 5-hour steps, says nothing about a reading taken after an idle gap.
        self.reading(session=90, ago=timedelta(hours=16))
        self.reading(session=5, ago=timedelta(hours=15, minutes=10))
        self.reading(session=70, ago=timedelta(minutes=30))
        result = self.run_jobs()
        self.assertEqual((result["status"], result["pause"]["job"]), ("paused_for_limits", "J1"))
        self.assertEqual(result["pause"]["last_reading"], 70)
        self.assertEqual(self.calls(), [])

    def test_calls_after_the_earliest_possible_reset_still_count(self):
        # Review round 3: the window holding the reading ended somewhere between P + 5 h and
        # R + 5 h. J1 ran after the earliest end, so it may be in the current window: a resume
        # past R + 5 h must still count it and pause before J2.
        self.reading(session=90, ago=timedelta(hours=9))
        self.reading(session=5, ago=timedelta(hours=4, minutes=1))
        self.control(60000)
        pause = self.run_jobs()["pause"]
        self.assertEqual(pause["job"], "J2")
        result = self.run_jobs(start_after=pause["start_after"])
        self.assertEqual((result["status"], result["pause"]["job"]), ("paused_for_limits", "J2"))
        self.assertEqual(result["pause"]["last_reading"], 0)
        self.assertGreater(result["pause"]["used_since"], 30)
        self.assertEqual(self.calls(), ["J1"])

    def test_never_interrupts_a_running_job(self):
        # J1's first attempt fails and pushes usage over the line; its retry still runs, and the
        # pause comes only before J2.
        self.reading(session=50)
        self.control(40000, fail_first="J1")
        result = self.run_jobs()
        self.assertEqual(self.calls(), ["J1", "J1"])
        self.assertEqual(result["completed"], ["J1"])
        self.assertEqual((result["status"], result["pause"]["job"]), ("paused_for_limits", "J2"))

    def test_the_first_job_pauses_when_the_last_reading_is_already_close(self):
        self.reading(session=70)
        result = self.run_jobs()
        self.assertEqual((result["status"], result["pause"]["job"]), ("paused_for_limits", "J1"))
        self.assertEqual(self.calls(), [])

    def test_without_a_reading_it_runs_and_says_why_it_could_not_check(self):
        ledger = usage.ledger_path()
        ledger.write_text("".join(json.dumps(row) + "\n" for row in usage.entries() if row["kind"] == "call"))
        self.control(40000)
        result = self.run_jobs()
        self.assertEqual(result["status"], "complete")
        self.assertIn("no plan reading", " ".join(result.get("limit_notes", [])))


if __name__ == "__main__":
    unittest.main()
