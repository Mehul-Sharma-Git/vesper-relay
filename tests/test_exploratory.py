"""P3-T5: the exploratory QA session.

After a frontend job's candidate passes its gates (focused and full depth), QA explores a
throwaway copy of it: empty input, very long text, emoji, double clicks, the back button, a slow
network, two tabs and keyboard only (with Playwright inside the sandbox). QA writes
exploratory.md with each bug's repro steps; its findings enter the backlog (P2-T7) with category
and severity, under P2-T7's rule (a blocker, or a security or data finding, waits for the owner once
the candidate's review finishes); a bug that matters comes with a proposed check the owner adds with
add-check (P2-T6), never automatically. `run --explore` counts the session against the reserve."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from builder import decisions, exploratory, review_gate, usage
from builder.brains import Selection
from builder.contracts import BuilderError, fingerprint, inventory
from builder.planning import review_plan
import test_agent_foundation
import test_planning
import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)

FIXTURE = ROOT / "docs" / "plan" / "fixtures" / "pocket-todo"
SOLUTION = ("server.py", "index.html", "app.js", "styles.css")


def probes(text="Tried it; nothing wrong."):
    return dict.fromkeys(exploratory.PROBES, text)


def finding(**changes):
    item = {"severity": "advisory", "category": "correctness", "probe": "emoji", "path": "Add todo form",
            "scenario": "A todo titled with a family emoji", "consequence": "The title is cut in the list",
            "evidence": "The list shows a broken glyph after reload",
            "recommendation": "Count user-perceived characters, not code points",
            "repro": "1. Open the app. 2. Type the family emoji as a todo title. 3. Press Enter. 4. Reload."}
    item.update(changes)
    return item


def spec(findings=(), proposed=None, markdown="# Exploratory session\n\n## F1\nRepro: 1. Open the app.\n",
         touch_app=False, bad_bytes=False, **report):
    data = {"summary": "Explored the add-todo journey.", "probes": probes(), "findings": list(findings)}
    data.update(report)
    return {"report": data, "markdown": markdown, "proposed": proposed or {}, "touch_app": touch_app,
            "bad_bytes": bad_bytes}


# A stand-in `claude` CLI that plays the three roles it is launched as: the worker ships
# server.py with a note-shaped section (kept from the reviewer, P3-T1b); QA (its folder has report/) writes the report spec.json asks
# for; the reviewer approves. It logs each role it played.
STAND_IN = r'''
import json, sys
from pathlib import Path
HERE = Path(sys.argv[0]).parent
prompt = sys.stdin.read()
role = 'reviewer' if Path('review.json').is_file() else 'qa' if Path('report').is_dir() else 'worker'
with open(HERE / 'roles.txt', 'a') as seen:
    seen.write(role + '\n')
if role == 'worker':
    Path('server.py').write_text('VERSION = 2\n')
    print(json.dumps({'type': 'result', 'result': %(note)r + '\n## Summary\nShipped [verified: wrote it].'}))
elif role == 'qa':
    spec = json.loads((HERE / 'spec.json').read_text())
    (HERE / 'brief.md').write_text(prompt)
    (HERE / 'layout.txt').write_text(' '.join(sorted(path.name for path in Path('.').iterdir())))
    Path('report/exploratory.md').write_text(spec['markdown'])
    Path('report/exploratory.json').write_text(json.dumps(spec['report']))
    for name, text in spec['proposed'].items():
        Path('report/proposed-checks').mkdir(exist_ok=True)
        Path('report/proposed-checks', name).write_text(text)
    if spec.get('bad_bytes'):
        Path('report/exploratory.md').write_bytes(b'# Report\n\xff\n')
    if spec['touch_app']:
        Path('app/server.py').write_text('changed by QA')
    print(json.dumps({'type': 'result', 'result': 'Explored [verified: ran the journeys].'}))
else:
    packet = json.loads(Path('review.json').read_text())
    report = {key: packet[key] for key in ('attempt_id', 'base_digest', 'candidate_digest')}
    report.update(verdict='approve', summary='Checked.', findings=[],
                  evidence=dict.fromkeys(%(areas)r, 'Read the diff.'))
    print(json.dumps({'type': 'result', 'result': json.dumps(report)}))
''' % {"note": test_agent_foundation.NOTE, "areas": review_gate.AREAS}


class Base(unittest.TestCase):
    setUp = test_planning.PlanningTests.setUp
    full = test_planning.PlanningTests.full
    focused = test_planning.PlanningTests.focused
    write = test_planning.PlanningTests.write
    report = test_planning.PlanningTests.report

    def stand_in(self, data, script=STAND_IN):
        bin_dir = Path(self.temp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        exe = bin_dir / "claude"
        exe.write_text(f"#!{sys.executable}\n" + script)
        exe.chmod(0o700)
        (bin_dir / "spec.json").write_text(json.dumps(data))
        patcher = mock.patch.dict(os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        patcher.start()
        self.addCleanup(patcher.stop)
        return bin_dir

    def approve(self, depth="focused", role="frontend", paths=("server.py",)):
        (self.root / "seed" / "server.py").write_text("VERSION = 1\n")
        contract = json.loads((self.root / "plan/contract.json").read_text())
        contract["jobs"][0].update(role=role, paths=list(paths))
        (self.root / "plan/contract.json").write_text(json.dumps(contract))
        if depth == "skip":
            test_planning.narrow(self.root)
        else:
            data = self.full() if depth == "full" else self.focused()
            data["architecture"]["consumers"] = [role, "qa"]
            data["handoff"]["acknowledged_by"] = [role, "qa"]
            self.write(data)
            review_plan(self.runner, report=self.report(), external_attested=True)
            self.runner.prove_checks()
        self.runner.approve(self.runner.review()["digest"])

    def submit(self, files=None):
        attempt = self.runner.prepare()
        for name, text in (files or {"server.py": "VERSION = 2\n"}).items():
            (Path(attempt["workspace"]) / name).write_text(text)
        result = self.runner.submit(attempt["id"])
        self.assertEqual(result["outcome"], "awaiting_review", result)
        return self.runner.state()["active"]

    def brain(self):
        return Selection(worker="claude-code", settings={}).worker("qa")

    def explore(self):
        with self.runner.lock():
            return exploratory.explore(self.runner, self.brain(), None, True, timeout=60)

    def review(self, findings=()):
        packet = self.runner.state()["active"]["review"]
        data = {**{key: packet[key] for key in review_gate.BINDING}, "summary": "Checked.",
                "verdict": "request_changes" if any(item["severity"] == "blocking" for item in findings) else "approve",
                "evidence": dict.fromkeys(review_gate.AREAS, "Read it."), "findings": list(findings)}
        with self.runner.lock():
            return self.runner.review_candidate(data, external_attested=True)

    def decide(self, finding_id, **choice):
        with self.runner.lock():
            return self.runner.decide(finding_id, **choice)

    def backlog(self):
        return [item for item in decisions.load(self.root)["items"] if item["source"] == "exploratory"]


class SessionTests(Base):
    def test_findings_land_in_the_backlog_with_category_and_severity(self):
        self.approve()
        attempt = self.submit()
        bin_dir = self.stand_in(spec([finding(), finding(severity="blocking", category="data", probe="two-tabs",
                                                         path="List rename")]))
        result = self.explore()
        items = self.backlog()
        self.assertEqual([(item["severity"], item["category"], item["probe"]) for item in items],
                         [("advisory", "correctness", "emoji"), ("blocking", "data", "two-tabs")])
        # P2-T7's rule: the advisory is noted; the data finding waits for the owner.
        self.assertEqual([item["status"] for item in items], ["noted", "awaiting_decision"])
        self.assertEqual(result["awaiting_decision"], [items[1]["id"]])
        for item in items:
            self.assertEqual((item["job"], item["attempt"]), ("J", attempt["id"]))
            self.assertIn("1. Open the app.", item["repro"])
        self.assertEqual([item["id"] for item in result["findings"]], [item["id"] for item in items])
        # The report is kept beside the attempt and recorded on it in the run's state.
        report = self.root / result["report"]
        self.assertTrue(report.is_file())
        self.assertIn("Repro", report.read_text())
        [session] = self.runner.state()["active"]["exploratory"]
        self.assertEqual(session["findings"], [item["id"] for item in items])
        self.assertEqual(session["awaiting"], [items[1]["id"]])
        self.assertEqual(session["report"], result["report"])
        self.assertEqual(set(session["probes"]), set(exploratory.PROBES))
        # The waiting finding joins the candidate's decisions only when its review finishes.
        status = self.runner.status()
        self.assertEqual((status["status"], status["awaiting_decision"]), ("awaiting_review", []))
        self.assertEqual(decisions.describe(items[0]), "the exploratory QA session on job J")
        # QA explored a copy of the candidate beside the approved plan, and was told what to try.
        self.assertEqual((bin_dir / "layout.txt").read_text(), "app plan report")
        brief = (bin_dir / "brief.md").read_text()
        for words in ("# QA engineer", "exploratory.md", "exploratory.json", "Playwright", *exploratory.PROBES):
            self.assertIn(words, brief)

    def test_a_security_finding_makes_an_approved_candidate_wait_for_the_owner(self):
        self.approve()
        self.submit()
        self.stand_in(spec([finding(severity="advisory", category="security", probe="long-text",
                                    path="Todo list")]))
        [found] = self.explore()["findings"]
        with self.assertRaisesRegex(BuilderError, "run review-candidate first"):
            self.decide(found["id"], accept=True, reason="Local app only")
        self.assertEqual(self.review()["outcome"], "awaiting_decision")
        status = self.runner.status()
        self.assertEqual((status["status"], status["awaiting_decision"]), ("awaiting_decision", [found["id"]]))
        with self.assertRaisesRegex(BuilderError, "awaits the owner's decision"):
            self.review()
        self.decide(found["id"], accept=True, reason="Only the owner uses this app")
        state = self.runner.state()
        self.assertEqual((state["completed"], state["attempts"][-1]["outcome"]), (["J"], "accepted"))
        self.assertEqual(self.backlog()[0]["status"], "accepted")

    def test_the_owner_can_send_an_exploratory_blocker_back_and_it_never_goes_back_alone(self):
        self.approve()
        self.submit()
        self.stand_in(spec([finding(severity="blocking", probe="double-click", path="Add todo form",
                                    recommendation="Ignore a second submit while the first is pending")]))
        [found] = self.explore()["findings"]
        # The reviewer approves; QA's blocker still waits for the owner instead of returning the job.
        self.assertEqual(self.review()["outcome"], "awaiting_decision")
        self.decide(found["id"], fix=True)
        attempt = self.runner.state()["attempts"][-1]
        self.assertEqual(attempt["outcome"], "rejected")
        self.assertIn("Ignore a second submit while the first is pending", attempt["reason"])
        self.assertEqual(self.backlog()[0]["status"], "fix")

    def test_a_rejected_candidate_keeps_its_exploratory_decisions(self):
        self.approve()
        self.submit()
        self.stand_in(spec([finding(category="data", probe="two-tabs")]))
        [found] = self.explore()["findings"]
        blocker = {"severity": "blocking", "category": "correctness", "path": "server.py", "scenario": "Save",
                   "consequence": "Lost", "evidence": "Read it", "recommendation": "Keep the version",
                   "repro": "POST twice -> 200"}
        result = self.review([blocker])
        self.assertEqual(result["outcome"], "rejected")
        self.assertIn(found["id"], result["awaiting_decision"])
        self.assertEqual(self.runner.status()["status"], "awaiting_decision")
        self.decide(found["id"], dismiss=True, reason="Two tabs are not a supported use")
        self.assertEqual(self.backlog()[0]["status"], "dismissed")

    def test_a_candidate_whose_findings_wait_cannot_be_abandoned_before_its_review(self):
        self.approve()
        attempt = self.submit()
        self.stand_in(spec([finding(category="security", probe="long-text")]))
        [found] = self.explore()["findings"]
        with self.runner.lock(), self.assertRaisesRegex(BuilderError, f"{found['id']} wait for the owner"):
            self.runner.abandon(attempt["id"])
        self.assertEqual(self.review()["outcome"], "awaiting_decision")
        self.decide(found["id"], fix=True)
        self.assertEqual(self.runner.status()["status"], "ready")
        self.assertEqual(self.backlog()[0]["status"], "fix")

    def test_a_candidate_with_only_noted_findings_can_be_abandoned(self):
        self.approve()
        attempt = self.submit()
        self.stand_in(spec([finding()]))
        self.explore()
        with self.runner.lock():
            self.assertEqual(self.runner.abandon(attempt["id"])["outcome"], "interrupted")

    def test_a_bug_that_matters_comes_with_a_proposed_check_the_owner_adds(self):
        self.approve()
        self.submit()
        script = "import sys\nraise SystemExit(0)\n"
        self.stand_in(spec([finding(severity="blocking", proposed_check="G_EMOJI")],
                           proposed={"G_EMOJI.py": script, "unused.py": "pass\n"}))
        result = self.explore()
        [item] = self.backlog()
        self.assertEqual(item["proposed_check"], "G_EMOJI")
        [proposal] = result["proposed_checks"]
        kept = self.root / proposal["script"]
        self.assertEqual(kept.read_text(), script)
        self.assertEqual(proposal["finding"], item["id"])
        self.assertIn(f"add-check --id G_EMOJI --script {kept}", proposal["command"])
        self.assertFalse((kept.parent / "unused.py").exists())
        # Proposed, never applied: the contract and its amendments are unchanged.
        state = self.runner.state()
        self.assertEqual(state.get("amendments", []), [])
        self.assertEqual([check["id"] for check in self.runner.frozen_contract(state)["checks"]], ["G"])

    def test_the_tested_candidate_is_untouched_and_review_still_runs(self):
        self.approve()
        attempt = self.submit()
        self.stand_in(spec(touch_app=True))
        self.explore()
        candidate, manifest = self.runner.reviewed_candidate(self.runner.state(), self.runner.state()["active"])
        self.assertEqual(fingerprint(manifest), attempt["review"]["candidate_digest"])
        self.assertEqual((candidate / "server.py").read_text(), "VERSION = 2\n")
        packet = self.runner.state()["active"]["review"]
        data = {**{key: packet[key] for key in review_gate.BINDING}, "summary": "Checked.", "verdict": "approve",
                "evidence": dict.fromkeys(review_gate.AREAS, "Read it."), "findings": []}
        with self.runner.lock():
            self.assertEqual(self.runner.review_candidate(data, external_attested=True)["outcome"], "accepted")

    def test_a_report_without_repro_steps_or_an_account_of_every_probe_is_refused(self):
        self.approve()
        self.submit()
        partial = probes()
        partial.pop("two-tabs")
        cases = {"repro": spec([finding(repro="")]),
                 "two-tabs": spec(probes=partial),
                 "category": spec([finding(category="ux")]),
                 "G_MISSING": spec([finding(proposed_check="G_MISSING")]),
                 "exploratory.md": spec(markdown=""),
                 "UTF-8": spec(bad_bytes=True)}
        for words, data in cases.items():
            with self.subTest(words):
                self.stand_in(data)
                with self.assertRaisesRegex(BuilderError, words):
                    self.explore()
                self.assertEqual(self.backlog(), [])
                self.assertNotIn("exploratory", self.runner.state()["active"])

    def test_the_session_is_refused_outside_its_scope(self):
        self.stand_in(spec())
        with self.subTest("before a tested candidate"):
            self.approve()
            with self.assertRaisesRegex(BuilderError, "passes its gates"):
                self.explore()
        with self.subTest("after the review"):
            self.submit()
            self.review()
            self.setUp()
            self.stand_in(spec())
            self.approve()
            self.submit()
            self.review([{"severity": "advisory", "category": "security", "path": "server.py", "scenario": "s",
                          "consequence": "c", "evidence": "e", "recommendation": "r"}])
            with self.assertRaisesRegex(BuilderError, "already reviewed"):
                self.explore()
        for depth, role, words in (("skip", "frontend", "focused and full depth"),
                                   ("focused", "backend", "frontend job")):
            with self.subTest(depth=depth, role=role):
                self.setUp()
                self.stand_in(spec())
                self.approve(depth, role)
                self.submit()
                with self.assertRaisesRegex(BuilderError, words):
                    self.explore()


class RunTests(Base):
    def run_at(self, explore, depth="focused", role="frontend"):
        bin_dir = self.stand_in(spec([finding()]))
        self.approve(depth, role)
        self.runner.run(Selection(worker="claude-code", settings={}), trust_host=True, reserve=0, explore=explore)
        return bin_dir, self.runner.state()["attempts"][-1]

    def test_run_explore_launches_qa_between_the_gates_and_the_review(self):
        bin_dir, attempt = self.run_at(True)
        self.assertEqual((bin_dir / "roles.txt").read_text().split(), ["worker", "qa", "reviewer"])
        self.assertEqual(attempt["outcome"], "accepted")
        self.assertEqual(len(attempt["exploratory"]), 1)
        self.assertEqual(len(self.backlog()), 1)

    def test_without_explore_or_outside_its_scope_run_does_not_explore(self):
        for explore, depth, role in ((False, "focused", "frontend"), (True, "skip", "frontend"),
                                     (True, "full", "backend")):
            with self.subTest(explore=explore, depth=depth, role=role):
                self.setUp()
                bin_dir, attempt = self.run_at(explore, depth, role)
                self.assertNotIn("qa", (bin_dir / "roles.txt").read_text().split())
                self.assertNotIn("exploratory", attempt)

    def test_a_failed_session_is_a_warning_and_the_review_goes_on(self):
        for name, data in (("no repro", spec([finding(repro="")])), ("not UTF-8", spec(bad_bytes=True))):
            with self.subTest(name):
                self.setUp()
                bin_dir = self.stand_in(data)
                self.approve()
                self.runner.run(Selection(worker="claude-code", settings={}), trust_host=True, reserve=0,
                                explore=True)
                attempt = self.runner.state()["attempts"][-1]
                self.assertEqual((bin_dir / "roles.txt").read_text().split(), ["worker", "qa", "reviewer"])
                self.assertEqual(attempt["outcome"], "accepted")
                self.assertTrue(any("exploratory session" in warning for warning in attempt["warnings"]))
                self.assertEqual(self.backlog(), [])

    def test_a_security_finding_holds_the_run_for_the_owner(self):
        self.stand_in(spec([finding(category="security")]))
        self.approve()
        result = self.runner.run(Selection(worker="claude-code", settings={}), trust_host=True, reserve=0,
                                 explore=True)
        [item] = self.backlog()
        self.assertEqual((result["status"], result["awaiting_decision"]), ("awaiting_decision", [item["id"]]))


class EstimateTests(unittest.TestCase):
    def test_run_explore_counts_a_qa_call_per_attempt_against_the_reserve(self):
        def calls(role, depth, explore):
            contract = {"jobs": [{"id": "J", "role": role, "max_attempts": 2}]}
            bundle = {"team": 1, "planning": {"depth": depth}, "plan_critique": True}
            return usage.estimate(contract, bundle, [], brains=lambda name: None, explore=explore)["calls"]
        self.assertEqual(calls("frontend", "focused", False), [2, 4])
        self.assertEqual(calls("frontend", "focused", True), [3, 6])
        self.assertEqual(calls("frontend", "skip", True), [2, 4])
        self.assertEqual(calls("backend", "focused", True), [2, 4])


# A stand-in QA on the Pocket Todo solution: it starts the candidate's server.py and runs the
# probes it can run over HTTP (no browser in a stand-in), and reports what it saw.
POCKET_TODO_QA = r'''
import json, subprocess, sys, tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
HERE = Path(sys.argv[0]).parent
sys.stdin.read()
if not Path('report').is_dir():
    raise SystemExit('this stand-in only explores')

def call(base, method, path, body=None):
    request = Request(base + path, data=None if body is None else json.dumps(body).encode(), method=method,
                      headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=10) as reply:
            return reply.status, json.loads(reply.read() or b'null')
    except HTTPError as error:
        return error.code, None

with tempfile.TemporaryDirectory() as temp:
    boot = ('import socket, runpy, sys; socket.getfqdn = lambda name="": name; '
            'sys.argv = ["server.py", "--port", "0", "--db", sys.argv[1]]; '
            'runpy.run_path("app/server.py", run_name="__main__")')
    server = subprocess.Popen([sys.executable, '-B', '-c', boot, temp + '/db.sqlite3'], stdout=subprocess.PIPE, text=True)
    try:
        base = server.stdout.readline().split()[1]
        lists = call(base, 'GET', '/api/lists')[1]
        inbox = lists[0]['id'] if isinstance(lists, list) else lists['lists'][0]['id']
        seen = {
            'empty-input': call(base, 'POST', '/api/todos', {'listId': inbox, 'title': '   '})[0],
            'long-text': call(base, 'POST', '/api/todos', {'listId': inbox, 'title': 'x' * 201})[0],
            'emoji': call(base, 'POST', '/api/todos', {'listId': inbox, 'title': 'Buy \U0001F34E'})[0],
        }
        twice = [call(base, 'POST', '/api/todos', {'listId': inbox, 'title': 'Pay rent'})[0] for _ in range(2)]
    finally:
        server.terminate()
        server.wait()

findings = []
if twice == [201, 201]:
    findings.append({'severity': 'advisory', 'category': 'correctness', 'probe': 'double-click', 'path': 'server.py',
                     'scenario': 'The same new todo is sent twice in a row (a double click past the UI guard, a retry, two tabs)',
                     'consequence': 'Two identical todos appear',
                     'evidence': f'POST /api/todos twice with the same title -> {twice[0]} then {twice[1]}',
                     'recommendation': 'Accept an idempotency key on create, or say in the plan that duplicates are allowed',
                     'repro': '1. Start the app. 2. POST /api/todos {"listId": INBOX, "title": "Pay rent"}. '
                              '3. Send the same request again at once. 4. GET /api/todos: two "Pay rent" todos.'})
account = {name: f'Over HTTP: {status}' for name, status in seen.items()}
account['double-click'] = f'Over HTTP, the same create twice: {twice}'
for name in ('back-button', 'slow-network', 'two-tabs', 'keyboard-only'):
    account[name] = 'Not run: this stand-in has no browser'
lines = ['# Exploratory session: Pocket Todo', '']
for number, item in enumerate(findings, 1):
    lines += [f'## {number}. {item["scenario"]}', '', f'Repro: {item["repro"]}', '']
lines += ['## Probes', ''] + [f'- {name}: {text}' for name, text in account.items()]
Path('report/exploratory.md').write_text('\n'.join(lines) + '\n')
Path('report/exploratory.json').write_text(json.dumps({'summary': 'Explored adding todos.', 'probes': account,
                                                       'findings': findings}))
print(json.dumps({'type': 'result', 'result': 'Explored Pocket Todo [verified: ran the server].'}))
'''


class PocketTodoTests(Base):
    def test_on_the_pocket_todo_fixture_the_session_produces_a_report(self):
        self.approve(paths=SOLUTION)
        self.submit({name: (FIXTURE / "solution" / name).read_text() for name in SOLUTION})
        self.stand_in(spec(), script=POCKET_TODO_QA)
        result = self.explore()
        text = (self.root / result["report"]).read_text()
        self.assertIn("# Exploratory session: Pocket Todo", text)
        self.assertIn("empty-input: Over HTTP: 400", text)
        self.assertIn("long-text: Over HTTP: 400", text)
        self.assertIn("emoji: Over HTTP: 201", text)
        [item] = self.backlog()
        self.assertEqual((item["probe"], item["category"], item["severity"]), ("double-click", "correctness", "advisory"))
        self.assertIn("201 then 201", item["evidence"])
        self.assertIn("Repro: 1. Start the app.", text)


class CommandTests(unittest.TestCase):
    def test_the_commands_offer_the_session(self):
        helped = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "explore", "--help"],
                                capture_output=True, text=True, check=True).stdout
        for words in ("--brain", "--sandbox", "--timeout"):
            self.assertIn(words, helped)
        helped = subprocess.run([sys.executable, "-B", str(ROOT / "build_local.py"), "--project", "x", "run",
                                 "--help"], capture_output=True, text=True, check=True).stdout
        self.assertIn("--explore", helped)
        usage = (ROOT / "docs" / "USAGE.md").read_text()
        self.assertIn("explore --brain", usage)
        self.assertIn("run --explore", usage)

    def test_the_qa_role_runs_the_exploratory_session(self):
        text = (ROOT / "team" / "roles" / "qa.md").read_text()
        for words in ("Exploratory session", "exploratory.md", "keyboard only", "two tabs", "add-check"):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
