"""P3-T3: QA owns the checks and proves each one can fail.

`prove-checks` applies each check's broken variant (checks/_broken/<CHECK_ID>/) to a copy of the
seed, or of a known-good tree given with --against, and requires the check to fail there while it
passes on the unbroken copy. At focused and full depth `approve` needs that proof for the exact
packet and stores it in the approval. `draft-checks` runs QA as a writer over a copy of plan/ and
checks/; checks may be recorded only (`"blocking": false`, mutation scores)."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from builder import qa
from builder.brains import Selection
from builder.contracts import BuilderError, inventory, validate
from builder.planning import review_plan
from builder.runner import Runner
import test_planning
import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)

FIXTURE = ROOT / "docs" / "plan" / "fixtures" / "pocket-todo"
GATE = "from pathlib import Path\nimport sys\nassert 'VERSION_CHECK = True' in (Path(sys.argv[1]) / 'server.py').read_text()\n"
SEED = "VERSION_CHECK = True\n# keeps stale writes out\n"
BREAKS = """--- a/server.py
+++ b/server.py
@@ -1,2 +1,2 @@
-VERSION_CHECK = True
+VERSION_CHECK = False
 # keeps stale writes out
"""
COSMETIC = """--- a/server.py
+++ b/server.py
@@ -1,2 +1,2 @@
 VERSION_CHECK = True
-# keeps stale writes out
+# keeps stale writes away
"""


class PatchTests(unittest.TestCase):
    """The strict unified-diff applier broken variants use (standard library only)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tree = Path(temp.name)
        (self.tree / "a.txt").write_text("one\ntwo\nthree\n")
        (self.tree / "old.txt").write_text("bye\n")

    def test_edits_adds_and_deletes_files(self):
        qa.apply_patch(self.tree, """--- a/a.txt
+++ b/a.txt
@@ -1,3 +1,3 @@
 one
-two
+TWO
 three
--- /dev/null
+++ b/sub/new.txt
@@ -0,0 +1,1 @@
+hello
\\ No newline at end of file
--- a/old.txt
+++ /dev/null
@@ -1 +0,0 @@
-bye
""")
        self.assertEqual((self.tree / "a.txt").read_text(), "one\nTWO\nthree\n")
        self.assertEqual((self.tree / "sub/new.txt").read_text(), "hello")
        self.assertFalse((self.tree / "old.txt").exists())

    def test_a_hunk_that_does_not_match_is_refused_and_changes_nothing(self):
        with self.assertRaisesRegex(BuilderError, "does not apply"):
            qa.apply_patch(self.tree, "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n one\n-zwei\n+TWO\n")
        self.assertEqual((self.tree / "a.txt").read_text(), "one\ntwo\nthree\n")

    def test_unsafe_paths_and_empty_patches_are_refused(self):
        for text in ("--- a/../x\n+++ b/../x\n@@ -0,0 +1 @@\n+x\n", "not a patch\n"):
            with self.assertRaises(BuilderError):
                qa.apply_patch(self.tree, text)


class ProveChecksTests(unittest.TestCase):
    setUp = test_planning.PlanningTests.setUp
    full = test_planning.PlanningTests.full
    focused = test_planning.PlanningTests.focused
    write = test_planning.PlanningTests.write
    report = test_planning.PlanningTests.report

    def project(self, variants=None, seed=SEED, gates=None):
        """A full-depth run with a real gate; variants map check ID to {file: text}."""
        (self.root / "seed" / "server.py").write_text(seed)
        (self.root / "checks" / "gate.py").write_text(GATE)
        if gates:
            contract = json.loads((self.root / "plan/contract.json").read_text())
            contract["checks"] += gates
            contract["jobs"][0]["checks"] += [item["id"] for item in gates]
            (self.root / "plan/contract.json").write_text(json.dumps(contract))
        for check, files in (variants or {}).items():
            for name, text in files.items():
                path = self.root / "checks" / "_broken" / check / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
        self.full()

    def critique(self):
        review_plan(self.runner, report=self.report(), external_attested=True)

    def outcomes(self, proof):
        return {item["id"]: item["outcome"] for item in proof["checks"]}

    def test_approve_is_refused_when_a_check_passes_against_its_broken_variant(self):
        self.project({"G": {"change.patch": COSMETIC, "note.md": "Changes only a comment."}})
        proof = self.runner.prove_checks()
        self.assertEqual(self.outcomes(proof), {"G": "passes_broken"})
        self.assertFalse(proof["passed"])
        self.assertEqual(proof["checks"][0]["note"], "Changes only a comment.")
        self.critique()
        with self.assertRaisesRegex(BuilderError, "G passes against its broken variant"):
            self.runner.approve(self.runner.review()["digest"])
        self.assertFalse(self.runner.state_file.exists())

    def test_a_proven_check_lets_approval_through_and_the_proof_is_stored(self):
        self.project({"G": {"change.patch": BREAKS}})
        proof = self.runner.prove_checks()
        self.assertEqual(self.outcomes(proof), {"G": "proven"})
        item = proof["checks"][0]
        self.assertEqual((item["base_exit_code"], item["broken_exit_code"] != 0), (0, True))
        self.critique()
        self.runner.approve(self.runner.review()["digest"])
        stored = self.runner.state()["check_proof"]
        self.assertEqual(stored["packet_digest"], proof["packet_digest"])
        self.assertEqual(self.outcomes(stored), {"G": "proven"})

    def test_focused_and_full_depth_need_a_proof_and_skip_depth_does_not(self):
        self.project({"G": {"change.patch": BREAKS}})
        self.critique()
        with self.assertRaisesRegex(BuilderError, "prove-checks"):
            self.runner.approve(self.runner.review()["digest"])
        self.focused()
        review_plan(self.runner, report=self.report(), external_attested=True)
        with self.assertRaisesRegex(BuilderError, "prove-checks"):
            self.runner.approve(self.runner.review()["digest"])
        test_planning.narrow(self.root)
        self.runner.approve(self.runner.review()["digest"])
        self.assertNotIn("check_proof", self.runner.state())

    def test_a_missing_broken_entry_is_reported_per_check(self):
        self.project({"G": {"change.patch": BREAKS}},
                     gates=[{"id": "G2", "script": "gate.py"}, {"id": "G3", "script": "gate.py"}])
        proof = self.runner.prove_checks()
        self.assertEqual(self.outcomes(proof), {"G": "proven", "G2": "missing", "G3": "missing"})
        self.assertEqual(proof["missing"], ["G2", "G3"])
        self.assertTrue(proof["passed"])  # "each check may have" a variant: reported, not refused
        self.critique()
        self.runner.approve(self.runner.review()["digest"])

    def test_the_proof_binds_the_exact_packet(self):
        self.project({"G": {"change.patch": BREAKS}})
        self.runner.prove_checks()
        (self.root / "checks" / "gate.py").write_text(GATE + "# edited after the proof\n")
        self.critique()
        with self.assertRaisesRegex(BuilderError, "prove-checks"):
            self.runner.approve(self.runner.review()["digest"])

    def test_a_changed_proof_log_is_refused(self):
        self.project({"G": {"change.patch": BREAKS}})
        proof = self.runner.prove_checks()
        (self.root / proof["checks"][0]["logs"]["broken"]).write_text("edited\n")
        self.critique()
        with self.assertRaisesRegex(BuilderError, "Check proof evidence changed"):
            self.runner.approve(self.runner.review()["digest"])

    def test_a_variant_that_does_not_apply_is_unusable_and_blocks(self):
        self.project({"G": {"change.patch": BREAKS.replace("-VERSION_CHECK = True", "-VERSION_CHECK = 1")}})
        proof = self.runner.prove_checks()
        self.assertEqual(self.outcomes(proof), {"G": "unusable"})
        self.assertIn("does not apply", proof["checks"][0]["reason"])
        self.assertFalse(proof["passed"])

    def test_replacement_files_break_the_behaviour_too(self):
        self.project({"G": {"files/server.py": "VERSION_CHECK = None\n"}})
        self.assertEqual(self.outcomes(self.runner.prove_checks()), {"G": "proven"})

    def test_a_variant_for_an_unknown_check_or_with_stray_files_is_refused(self):
        self.project({"NOPE": {"change.patch": BREAKS}})
        with self.assertRaisesRegex(BuilderError, "NOPE matches no check"):
            self.runner.prove_checks()
        shutil.rmtree(self.root / "checks" / "_broken" / "NOPE")
        self.project({"G": {"change.patch": BREAKS, "extra.txt": "?"}})
        proof = self.runner.prove_checks()
        self.assertEqual(self.outcomes(proof), {"G": "unusable"})
        self.assertIn("extra.txt", proof["checks"][0]["reason"])

    def test_a_check_that_fails_on_the_unbroken_base_proves_little_and_is_reported(self):
        # A new build's seed is empty: the check fails before anything is broken.
        self.project({"G": {"files/server.py": "VERSION_CHECK = None\n"}}, seed="# nothing yet\n")
        proof = self.runner.prove_checks()
        self.assertEqual(self.outcomes(proof), {"G": "fails_on_base"})
        self.assertTrue(proof["passed"])
        self.assertEqual(proof["inconclusive"], ["G"])

    def test_against_a_known_good_tree(self):
        self.project({"G": {"change.patch": BREAKS}}, seed="# nothing yet\n")
        good = Path(self.temp.name) / "solution"
        good.mkdir()
        (good / "server.py").write_text(SEED)
        proof = self.runner.prove_checks(against=good)
        self.assertEqual(self.outcomes(proof), {"G": "proven"})
        self.assertEqual(proof["against"]["path"], str(good.resolve()))
        self.assertEqual(proof["against"]["digest"], qa.fingerprint(inventory(good)))

    def test_command_gates_are_proven_too(self):
        command = [Path(sys.executable).name, "-c",
                   "import pathlib; assert 'VERSION_CHECK = True' in pathlib.Path('server.py').read_text()"]
        path = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", os.defpath)
        with mock.patch.dict(os.environ, {"PATH": path}):
            self.project({"G_CMD": {"change.patch": BREAKS}}, gates=[{"id": "G_CMD", "command": command}])
            self.assertEqual(self.outcomes(self.runner.prove_checks())["G_CMD"], "proven")

    def test_prove_checks_is_refused_after_approval(self):
        self.project()
        test_planning.narrow(self.root)
        self.runner.approve(self.runner.review()["digest"])
        with self.assertRaisesRegex(BuilderError, "before approval"):
            self.runner.prove_checks()

    def test_the_command_line_exits_1_when_the_proof_does_not_pass(self):
        import subprocess
        self.project({"G": {"change.patch": COSMETIC}})
        command = [sys.executable, "-B", str(ROOT / "vesper.py"), "--project", str(self.root), "prove-checks",
                   "--sandbox", "none"]
        done = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(json.loads(done.stdout)["checks"][0]["outcome"], "passes_broken")
        (self.root / "checks" / "_broken" / "G" / "change.patch").write_text(BREAKS)
        done = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual((done.returncode, json.loads(done.stdout)["passed"]), (0, True), done.stderr)
        helped = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "draft-checks", "--help"],
                                capture_output=True, text=True)
        self.assertIn("--brain", helped.stdout)

    def test_the_plan_sheet_shows_the_proof(self):
        self.project({"G": {"change.patch": BREAKS}}, gates=[{"id": "G2", "script": "gate.py"}])
        self.assertIn("Checks proven to fail: not run yet", self.runner.review_sheet())
        self.runner.prove_checks()
        sheet = self.runner.review_sheet()
        self.assertIn("Checks proven to fail: 1 of 2", sheet)
        self.assertIn("G2: no broken variant", sheet)


class RecordOnlyCheckTests(unittest.TestCase):
    """Mutation scores at full depth are recorded, never blocking (P3-T3 item 4)."""
    setUp = test_planning.PlanningTests.setUp

    def contract(self, **change):
        data = json.loads((self.root / "plan/contract.json").read_text())
        data["checks"].append({"id": "G_MUT", "script": "mutation.py", "blocking": False, **change})
        data["jobs"][0]["checks"].append("G_MUT")
        (self.root / "checks" / "mutation.py").write_text("print('mutation score 40%')\nraise SystemExit(3)\n")
        return data

    def test_a_record_only_check_runs_and_never_rejects(self):
        (self.root / "plan/contract.json").write_text(json.dumps(self.contract()))
        test_planning.narrow(self.root)
        self.runner.approve(self.runner.review()["digest"])
        attempt = self.runner.prepare()
        (Path(attempt["workspace"]) / "server.py").write_text("ok\n")
        result = self.runner.submit(attempt["id"])
        self.assertEqual(result["outcome"], "awaiting_review")
        recorded = {item["id"]: item for item in self.runner.state()["active"]["checks"]}
        self.assertEqual((recorded["G_MUT"]["exit_code"], recorded["G_MUT"]["blocking"]), (3, False))
        self.assertIn("mutation score 40%", (self.root / recorded["G_MUT"]["log"]).read_text())

    def test_a_promise_cannot_rest_on_a_record_only_check(self):
        data = self.contract()
        data["requirements"][0]["checks"] = ["G_MUT"]
        checks = {"gate.py": ["0" * 64, 0o644], "mutation.py": ["0" * 64, 0o644]}
        with self.assertRaisesRegex(BuilderError, "names G_MUT, which records only"):
            validate(data, checks)
        with self.assertRaisesRegex(BuilderError, "blocking"):
            validate(self.contract(blocking="no"), checks)
        only_recorded = self.contract()
        only_recorded["checks"][0]["blocking"] = False  # J's gate.py now only records too
        only_recorded["checks"].append({"id": "G_OTHER", "script": "gate.py"})
        only_recorded["requirements"][0]["checks"] = ["G_OTHER"]
        only_recorded["jobs"].append({"id": "J2", "role": "backend", "goal": "Other", "paths": ["other.py"],
                                      "depends_on": [], "checks": ["G_OTHER"]})
        with self.assertRaisesRegex(BuilderError, "Job J needs a check that blocks"):
            validate(only_recorded, checks)


@unittest.skipUnless(os.name == "posix", "the fixture gates start a local server")
class PocketTodoFixtureTests(unittest.TestCase):
    """The fixture's three checks each fail against their broken variant (checks/_broken/), and
    pass on the known-good reference app. G_BROWSER needs Python Playwright: it runs here when
    Playwright is installed, and in the sandbox image otherwise (the PR's acceptance command)."""

    def test_each_fixture_check_fails_against_its_broken_variant(self):
        contract = json.loads((FIXTURE / "plan" / "contract.json").read_text())
        broken = FIXTURE / "checks" / "_broken"
        self.assertEqual(sorted(path.name for path in broken.iterdir()), ["G_API", "G_BROWSER", "G_UI"])
        only = ["G_API", "G_UI"]
        if importlib.util.find_spec("playwright"):
            only.append("G_BROWSER")
        with tempfile.TemporaryDirectory() as temp:
            results = qa.prove_tree(contract, FIXTURE / "checks", inventory(FIXTURE / "checks"),
                                    FIXTURE / "reference", Path(temp), launcher=None, only=only)
            # On a failure, show why: the end of each log of a check that was not proven.
            why = "\n".join(f"{item['id']} {key}: " + path.read_text(errors="replace")[-1500:]
                            for item in results if item["outcome"] != "proven"
                            for key, path in item.get("logs", {}).items())
        self.assertEqual({item["id"]: item["outcome"] for item in results}, dict.fromkeys(only, "proven"), why)


# A stand-in `claude` CLI acting as QA: it drafts a strategy and a broken variant, and edits the
# seed too when a marker file sits next to it.
QA_STAND_IN = """
import json, sys
from pathlib import Path
HERE = Path(sys.argv[0]).parent
(HERE / 'brief.md').write_text(sys.stdin.read())
Path('checks/test-strategy.md').write_text('| Risk | Level | Check |\\n| stale write | integration | G |\\n')
variant = Path('checks/_broken/G')
variant.mkdir(parents=True, exist_ok=True)
(variant / 'change.patch').write_text(%r)
if (HERE / 'touch-seed').exists():
    Path('seed/server.py').write_text('changed')
print(json.dumps({'type': 'result', 'result': 'Drafted G [verified: read checks/gate.py].'}))
""" % BREAKS


class DraftChecksTests(unittest.TestCase):
    setUp = test_planning.PlanningTests.setUp

    def stand_in(self, touch_seed=False):
        bin_dir = Path(self.temp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        exe = bin_dir / "claude"
        exe.write_text(f"#!{sys.executable}\n" + QA_STAND_IN)
        exe.chmod(0o700)
        if touch_seed:
            (bin_dir / "touch-seed").write_text("")
        patcher = mock.patch.dict(os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        patcher.start()
        self.addCleanup(patcher.stop)
        return bin_dir

    def brain(self):
        return Selection(worker="claude-code", settings={}).worker("qa")

    def test_qa_drafts_checks_into_the_plan_as_a_plan_change(self):
        (self.root / "seed" / "server.py").write_text(SEED)
        bin_dir = self.stand_in()
        result = qa.draft_checks(self.runner, self.brain(), None, True, timeout=60)
        self.assertEqual(result["changed"], ["checks/_broken/G/change.patch", "checks/test-strategy.md"])
        self.assertIn("Drafted G", result["report"])
        self.assertTrue((self.root / "checks" / "test-strategy.md").is_file())
        self.assertEqual((self.root / "checks" / "_broken" / "G" / "change.patch").read_text(), BREAKS)
        brief = (bin_dir / "brief.md").read_text()
        for words in ("checks/test-strategy.md", "checks/_broken/", "seed/ is read-only", "# QA engineer"):
            self.assertIn(words, brief)

    def test_a_draft_that_edits_the_seed_is_refused_and_changes_nothing(self):
        (self.root / "seed" / "server.py").write_text(SEED)
        self.stand_in(touch_seed=True)
        before = inventory(self.root / "checks")
        with self.assertRaisesRegex(BuilderError, "seed"):
            qa.draft_checks(self.runner, self.brain(), None, True, timeout=60)
        self.assertEqual(inventory(self.root / "checks"), before)
        self.assertEqual((self.root / "seed" / "server.py").read_text(), SEED)

    def test_draft_checks_is_refused_after_approval(self):
        test_planning.narrow(self.root)
        self.runner.approve(self.runner.review()["digest"])
        with self.assertRaisesRegex(BuilderError, "before approval"):
            qa.draft_checks(self.runner, self.brain(), None, True, timeout=60)


class QaRoleTests(unittest.TestCase):
    def test_the_qa_role_owns_the_checks_and_the_test_strategy(self):
        text = (ROOT / "team" / "roles" / "qa.md").read_text()
        for words in ("checks/test-strategy.md", "checks/_broken/", "prove-checks", "OpenAPI",
                      "Firefox and WebKit", "Gremlins", "StrykerJS", '"blocking": false'):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
