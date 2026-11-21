"""P3-T4: the reviewer's blockers come with evidence, full-depth reviews look through four lenses,
big diffs get a note, and each finding's outcome calibrates the reviewer.

- A blocking finding needs a `repro`; without one it becomes a `suspected` advisory that waits for
  the owner. Findings carry a `confidence` (high, medium, low).
- At full depth a launched reviewer runs four lens reviews (correctness, security, performance,
  readability) whose reports are merged deterministically; focused and skip get one review.
- A diff over 400 changed lines adds a note to the review packet and to `status`.
- `.builder/calibration.jsonl` records each finding as unknown, confirmed (the job came back and
  the fix changed that path) or dismissed (`decide --dismiss`); `vesper learn` reports precision
  per lens."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from builder import calibration, review_gate
from builder.brains import Selection
from builder.contracts import BuilderError
from builder.learning import summary
from builder.planning import review_plan
from builder.usage import estimate
import test_agent_foundation
import test_planning
import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)

FIXTURE = ROOT / "docs" / "plan" / "fixtures" / "pocket-todo"
PACKET = {"attempt_id": "a", "base_digest": "b", "candidate_digest": "c", "checks": []}
REPRO = "curl -X POST -H 'Origin: http://evil.example' /api/lists -> 201 (expected 403)"


def finding(severity="blocking", category="security", path="server.py", recommendation="Refuse foreign Origin.",
            **extra):
    return {"severity": severity, "category": category, "path": path, "evidence": "No Origin check on writes.",
            "recommendation": recommendation, "confidence": "high", **extra}


def report(findings=(), verdict=None, summary_text="Checked."):
    findings = list(findings)
    blocked = any(item["severity"] == "blocking" for item in findings)
    return {**{key: PACKET[key] for key in review_gate.BINDING},
            "verdict": verdict or ("request_changes" if blocked else "approve"), "summary": summary_text,
            "evidence": dict.fromkeys(review_gate.AREAS, "Read the diff."), "findings": findings}


class EvidenceTests(unittest.TestCase):
    def test_a_blocker_without_a_repro_becomes_a_suspected_advisory(self):
        raw = report([finding(), finding(category="correctness", path="app.js", repro=REPRO)])
        result, downgraded = review_gate.downgrade(raw)
        self.assertEqual(downgraded, 1)
        first, second = result["findings"]
        self.assertEqual((first["severity"], first["suspected"]), ("advisory", True))
        self.assertIn("no repro", first["evidence"].lower())
        self.assertEqual(second["severity"], "blocking")
        self.assertEqual(result["verdict"], "request_changes")
        alone, _ = review_gate.downgrade(report([finding()]))
        self.assertEqual(alone["verdict"], "approve")  # nothing proven blocks
        self.assertEqual(raw["findings"][0]["severity"], "blocking")  # the reviewer's report is kept as given

    def test_repro_and_confidence_are_in_the_schema_and_checked(self):
        schema = review_gate.report_schema(PACKET)["properties"]["findings"]["items"]
        self.assertEqual(schema["properties"]["confidence"]["enum"], ["high", "medium", "low"])
        self.assertIn("repro", schema["properties"])
        self.assertIn("repro", schema["required"])
        with self.assertRaisesRegex(BuilderError, "confidence"):
            review_gate.validate_report(report([finding(confidence="sure", repro=REPRO)]), PACKET)
        with self.assertRaisesRegex(BuilderError, "repro"):
            review_gate.validate_report(report([finding(repro=5)]), PACKET)

    def test_the_prompt_asks_for_a_repro_and_offers_the_sandbox_only_with_a_shell(self):
        from builder.team import profile
        text = review_gate.prompt(profile("reviewer"), PACKET)
        self.assertIn("repro", text)
        self.assertIn("suspected", text)
        self.assertNotIn(review_gate.PROVE_PROMPT, text)
        sandboxed = review_gate.prompt(profile("reviewer"), PACKET, shell=True)
        self.assertIn(review_gate.PROVE_PROMPT, sandboxed)
        self.assertIn("write any failing test or script under /tmp", sandboxed)


class MergeTests(unittest.TestCase):
    def lens_reports(self):
        return {
            "correctness": report([finding(category="correctness", path="app.js", recommendation="Keep the draft.",
                                           repro="type, delete list, Add: draft lost")]),
            "security": report([finding(repro=REPRO, confidence="medium"),
                                finding(severity="advisory", category="data", path="server.py",
                                        recommendation="Bound the body.")]),
            "performance": report([finding(severity="advisory", path="server.py",
                                           recommendation="refuse   foreign ORIGIN")]),
            "readability": report(),
        }

    def test_union_dedupe_and_verdict(self):
        merged = review_gate.merge(self.lens_reports(), PACKET)
        keys = [(item["path"], item["category"], item["severity"], item["lenses"]) for item in merged["findings"]]
        self.assertEqual(keys, [("app.js", "correctness", "blocking", ["correctness"]),
                                ("server.py", "security", "blocking", ["security", "performance"]),
                                ("server.py", "data", "advisory", ["security"])])
        self.assertEqual(merged["findings"][1]["repro"], REPRO)
        self.assertEqual(merged["verdict"], "request_changes")
        self.assertEqual(set(merged["evidence"]), set(review_gate.AREAS))
        for lens in review_gate.LENSES:
            self.assertIn(f"[{lens}]", merged["summary"])
        review_gate.validate_report(merged, PACKET)

    def test_the_merge_does_not_depend_on_arrival_order(self):
        reports = self.lens_reports()
        backwards = dict(reversed(list(reports.items())))
        self.assertEqual(review_gate.merge(reports, PACKET), review_gate.merge(backwards, PACKET))

    def test_a_proven_blocker_replaces_an_earlier_lens_suspected_copy_whole(self):
        # Review round 1 of PR 60: the suspected mark of the downgraded copy must not survive.
        suspected, _ = review_gate.downgrade(report([finding()]))
        proven = report([finding(repro=REPRO, confidence="medium")])
        merged = review_gate.merge({"correctness": suspected, "security": proven,
                                    "performance": report(), "readability": report()}, PACKET)
        [item] = merged["findings"]
        self.assertEqual((item["severity"], item["lenses"], item["repro"]), ("blocking", ["correctness", "security"],
                                                                            REPRO))
        self.assertNotIn("suspected", item)
        self.assertNotIn("Suspected blocker", item["evidence"])
        self.assertEqual(item["confidence"], "high")  # the strongest confidence of the two is kept

    def test_a_suspected_copy_outranks_a_plain_advisory_in_either_order(self):
        # Review round 2 of PR 60: a suspected blocker must still reach the owner.
        plain = report([finding(severity="advisory", category="correctness", path="app.js")])
        suspected, _ = review_gate.downgrade(report([finding(category="correctness", path="app.js")]))
        for first, second in ((plain, suspected), (suspected, plain)):
            merged = review_gate.merge({"correctness": first, "security": second,
                                        "performance": report(), "readability": report()}, PACKET)
            [item] = merged["findings"]
            self.assertEqual((item["severity"], item.get("suspected")), ("advisory", True))
            self.assertIn("Suspected blocker", item["evidence"])
            self.assertEqual(item["lenses"], ["correctness", "security"])
            self.assertEqual(merged["verdict"], "approve")

    def test_no_blockers_left_means_approve(self):
        merged = review_gate.merge({lens: report() for lens in review_gate.LENSES}, PACKET)
        self.assertEqual((merged["verdict"], merged["findings"]), ("approve", []))


class RunTests(unittest.TestCase):
    """Runner level, on the manual path: the size note, downgrades and calibration."""
    setUp = test_planning.PlanningTests.setUp

    def approve(self, seed="VERSION = 1\n"):
        (self.root / "seed" / "server.py").write_text(seed)
        test_planning.narrow(self.root)
        self.runner.approve(self.runner.review()["digest"])

    def submit(self, text):
        attempt = self.runner.prepare()
        (Path(attempt["workspace"]) / "server.py").write_text(text)
        result = self.runner.submit(attempt["id"])
        self.assertEqual(result["outcome"], "awaiting_review", result)
        return self.runner.state()["active"]

    def review(self, findings):
        packet = self.runner.state()["active"]["review"]
        data = {**{key: packet[key] for key in review_gate.BINDING}, "summary": "Checked.",
                "verdict": "request_changes" if any(item["severity"] == "blocking" for item in findings) else "approve",
                "evidence": dict.fromkeys(review_gate.AREAS, "Read it."), "findings": findings}
        with self.runner.lock():
            return self.runner.review_candidate(data, external_attested=True)

    def test_a_diff_over_400_changed_lines_gets_a_note_and_status_shows_it(self):
        self.approve()
        attempt = self.submit("".join(f"LINE_{number} = {number}\n" for number in range(400)))
        self.assertEqual(attempt["review"]["changed_lines"], 401)  # 400 added, 1 removed
        self.assertIn("401 changed lines", attempt["review"]["size_note"])
        self.assertIn("split", attempt["review"]["size_note"])
        status = self.runner.status()
        self.assertEqual(status["size_notes"], [{"job": "J", "attempt": attempt["id"],
                                                 "note": attempt["review"]["size_note"]}])
        self.review([])
        self.assertEqual(self.runner.status()["status"], "complete")  # a note, never a refusal

    def test_a_small_diff_has_no_note(self):
        self.approve()
        attempt = self.submit("VERSION = 2\n")
        self.assertEqual(attempt["review"]["changed_lines"], 2)
        self.assertNotIn("size_note", attempt["review"])
        self.assertNotIn("size_notes", self.runner.status())

    def test_a_blocker_without_a_repro_waits_for_the_owner_as_suspected(self):
        self.approve()
        self.submit("VERSION = 2\n")
        result = self.review([finding(category="correctness", confidence="low")])
        self.assertEqual(result["outcome"], "awaiting_decision")
        review = self.runner.state()["active"]["review"]
        self.assertEqual((review["verdict"], review["reported_verdict"], review["downgraded"]),
                         ("approve", "request_changes", 1))
        item = self.runner.status()["backlog"][0]
        self.assertEqual((item["severity"], item["status"], item["suspected"]), ("advisory", "awaiting_decision", True))

    def test_calibration_records_confirmed_dismissed_and_unknown(self):
        self.approve()
        self.submit("VERSION = 2\n")
        rejected = self.review([finding(category="correctness", repro="VERSION stays 2 on a stale write"),
                                finding(severity="advisory", category="performance", path="other.py",
                                        recommendation="Cache it.")])
        self.assertEqual(rejected["outcome"], "rejected")
        rows = calibration.rows(self.root)
        self.assertEqual([(row["finding"], row["outcome"], row["lens"]) for row in rows],
                         [("F1", "unknown", ["combined"]), ("F2", "unknown", ["combined"])])
        # The job came back and the fix changed server.py: F1 is confirmed; F2's path did not change.
        self.submit("VERSION = 3\n")
        latest = calibration.outcomes(calibration.rows(self.root))
        self.assertEqual({key: row["outcome"] for key, row in latest.items()}, {"F1": "confirmed", "F2": "unknown"})
        # A security advisory waits for the owner, who dismisses it as not a defect.
        self.review([finding(severity="advisory", recommendation="Check the Origin header.")])
        with self.runner.lock():
            self.runner.decide("F3", dismiss=True, reason="The app only listens on 127.0.0.1 (D3)")
        self.assertEqual(self.runner.status()["status"], "complete")
        latest = calibration.outcomes(calibration.rows(self.root))
        self.assertEqual(latest["F3"]["outcome"], "dismissed")
        self.assertEqual(self.runner.status()["backlog"][2]["status"], "dismissed")
        self.assertEqual(calibration.precision(calibration.rows(self.root)),
                         {"combined": {"confirmed": 1, "dismissed": 1, "unknown": 1, "precision": 0.5}})

    def test_dismissing_needs_a_reason_and_a_human_confirmation(self):
        self.approve()
        self.submit("VERSION = 2\n")
        self.review([finding(severity="advisory", recommendation="Check the Origin header.")])
        with self.runner.lock(), self.assertRaisesRegex(BuilderError, "reason"):
            self.runner.decide("F1", dismiss=True)
        with mock.patch.dict(os.environ, {"VESPER_TEST_CONFIRM_ANSWER": "no"}), self.runner.lock():
            with self.assertRaisesRegex(BuilderError, "not confirmed"):
                self.runner.decide("F1", dismiss=True, reason="Not reachable")
        self.assertEqual(self.runner.status()["status"], "awaiting_decision")
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.dict(os.environ, {"VESPER_TEST_SHEETS": folder}), self.runner.lock():
                self.runner.decide("F1", dismiss=True, reason="Not reachable")
            [sheet] = [path.read_text() for path in Path(folder).glob("*-accept-risk.txt")]
        for words in ("Vesper Relay: dismiss a finding", "You dismiss this finding as not a defect",
                      "Your reason: Not reachable"):
            self.assertIn(words, sheet)

    def test_learn_reports_reviewer_precision_per_lens(self):
        home = Path(self.temp.name) / "state"
        lines = [{"finding": "F1", "lens": ["security"], "outcome": "unknown"},
                 {"finding": "F1", "lens": ["security"], "outcome": "confirmed"},
                 {"finding": "F2", "lens": ["security", "performance"], "outcome": "dismissed"}]
        for name in ("run-a", "run-b"):  # F1 in one run is not F1 in another
            folder = home / "runs" / name / ".builder"
            folder.mkdir(parents=True)
            (folder / "calibration.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
        with mock.patch.dict(os.environ, {"VESPER_STATE_DIR": str(home)}):
            precision = summary({"runs": {}, "active": []})["reviewer_precision"]
        self.assertEqual(precision["security"], {"confirmed": 2, "dismissed": 2, "unknown": 0, "precision": 0.5})
        self.assertEqual(precision["performance"], {"confirmed": 0, "dismissed": 2, "unknown": 0, "precision": 0.0})


class EstimateTests(unittest.TestCase):
    def test_full_depth_counts_a_review_per_lens(self):
        contract = {"jobs": [{"id": "J", "role": "backend", "max_attempts": 2}]}
        calls = lambda depth: estimate(contract, {"team": {}, "planning": {"depth": depth}, "plan_critique": True},
                                       [], brains=lambda role: None)["calls"]
        self.assertEqual(calls("focused"), [2, 4])  # worker and one review per attempt
        self.assertEqual(calls("full"), [5, 10])  # worker and four lens reviews per attempt


# A stand-in `claude` CLI. As a worker it ships the Pocket Todo solution's server.py (which has no
# Origin check) with a reasoning note. As a reviewer it reads its lens from the prompt; the security
# lens proves the CSRF hole by starting the candidate and sending a cross-origin write, and quotes
# the result in its repro.
LENS_STAND_IN = r'''
import json, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
HERE = Path(sys.argv[0]).parent
prompt = sys.stdin.read()
if not Path('review.json').is_file():
    Path('server.py').write_text(Path(%(solution)r).read_text())
    print(json.dumps({'type': 'result', 'result': %(note)r + '\n## Summary\nShipped server.py [verified: copied it].'}))
    raise SystemExit(0)
lens = next((name for name in ('correctness', 'security', 'performance', 'readability') if f'Lens: {name}' in prompt), 'combined')
with open(HERE / 'lenses.txt', 'a') as seen:
    seen.write(lens + '\n')
packet = json.loads(Path('review.json').read_text())
findings = []
if lens in ('security', 'combined'):
    with tempfile.TemporaryDirectory() as temp:
        boot = ('import socket, runpy, sys; socket.getfqdn = lambda name="": name; '
                'sys.argv = ["server.py", "--port", "0", "--db", sys.argv[1]]; '
                'runpy.run_path("candidate/server.py", run_name="__main__")')
        server = subprocess.Popen([sys.executable, '-B', '-c', boot, temp + '/db.sqlite3'],
                                  stdout=subprocess.PIPE, text=True)
        try:
            base = server.stdout.readline().split()[1]
            request = Request(base + '/api/lists', data=b'{"name": "Pwned"}', method='POST',
                              headers={'Content-Type': 'application/json', 'Origin': 'http://evil.example'})
            status = urlopen(request, timeout=10).status
        finally:
            server.terminate()
            server.wait()
    if status == 201:
        findings.append({'severity': 'blocking', 'category': 'security', 'path': 'server.py', 'confidence': 'high',
                         'evidence': 'Writes never check the Origin header, so another website can change data.',
                         'recommendation': 'Refuse writes whose Origin is not the app itself with 403.',
                         'repro': f'POST /api/lists with Origin: http://evil.example and a JSON body -> {status} '
                                  '(expected 403); the list was created'})
report = {key: packet[key] for key in ('attempt_id', 'base_digest', 'candidate_digest')}
report.update(verdict='request_changes' if findings else 'approve', summary=f'{lens} lens checked.', findings=findings,
              evidence={key: f'{lens}: read the diff.' for key in ('requirements', 'correctness', 'scope', 'tests',
                                                                     'maintainability', 'security')})
print(json.dumps({'type': 'result', 'result': json.dumps(report)}))
''' % {"solution": str(FIXTURE / "solution" / "server.py"), "note": test_agent_foundation.NOTE}


class PocketTodoLensReviewTests(unittest.TestCase):
    """A stand-in multi-lens review of the Pocket Todo solution (no CSRF/Origin check in server.py)."""
    setUp = test_planning.PlanningTests.setUp
    full = test_planning.PlanningTests.full
    focused = test_planning.PlanningTests.focused
    write = test_planning.PlanningTests.write
    report = test_planning.PlanningTests.report

    def stand_in(self):
        bin_dir = Path(self.temp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        exe = bin_dir / "claude"
        exe.write_text(f"#!{sys.executable}\n" + LENS_STAND_IN)
        exe.chmod(0o700)
        patcher = mock.patch.dict(os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        patcher.start()
        self.addCleanup(patcher.stop)
        return bin_dir

    def run_at(self, depth):
        bin_dir = self.stand_in()
        contract = json.loads((self.root / "plan/contract.json").read_text())
        contract["jobs"][0]["max_attempts"] = 1
        (self.root / "plan/contract.json").write_text(json.dumps(contract))
        depth()
        review_plan(self.runner, report=self.report(), external_attested=True)
        self.runner.prove_checks()
        self.runner.approve(self.runner.review()["digest"])
        self.runner.run(Selection(worker="claude-code", settings={}), trust_host=True, reserve=0)
        return bin_dir, self.runner.state()["attempts"][-1]

    def test_full_depth_runs_four_lenses_and_finds_the_csrf_hole_with_a_repro(self):
        bin_dir, attempt = self.run_at(self.full)
        self.assertEqual(sorted((bin_dir / "lenses.txt").read_text().split()), sorted(review_gate.LENSES))
        review = attempt["review"]
        self.assertEqual([item["lens"] for item in review["lenses"]], list(review_gate.LENSES))
        self.assertEqual(review["verdict"], "request_changes")
        [blocker] = [item for item in review["findings"] if item["severity"] == "blocking"]
        self.assertEqual((blocker["category"], blocker["path"], blocker["lenses"]), ("security", "server.py", ["security"]))
        self.assertIn("-> 201 (expected 403)", blocker["repro"])
        self.assertEqual(attempt["outcome"], "rejected")
        rows = calibration.rows(self.root)
        self.assertEqual([(row["lens"], row["outcome"]) for row in rows], [(["security"], "unknown")])

    def test_focused_depth_runs_one_combined_review(self):
        bin_dir, attempt = self.run_at(self.focused)
        self.assertEqual((bin_dir / "lenses.txt").read_text().split(), ["combined"])
        self.assertNotIn("lenses", attempt["review"])
        [blocker] = [item for item in attempt["review"]["findings"] if item["severity"] == "blocking"]
        self.assertIn("-> 201 (expected 403)", blocker["repro"])
        self.assertEqual([row["lens"] for row in calibration.rows(self.root)], [["combined"]])


if __name__ == "__main__":
    unittest.main()
