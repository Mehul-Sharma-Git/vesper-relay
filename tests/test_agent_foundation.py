"""Shared agent foundation (P3-T1): the critical-thinking skill in every role, the worker's
reasoning note kept with its attempt and shown to the reviewer, and the depth rule."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from builder.brains import Selection
from builder.planning import review_plan
from builder.providers import REASONING_FIELDS, reasoning_note, worker_prompt
from builder.review_gate import prompt as review_prompt
from builder.team import PROFILES, SHARED_SKILLS, catalog, freeze_team, profile, render
import test_planning
import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)

NOTE = """## Reasoning note
Understanding: Restore the stale-write version check.
Assumptions: Only the check regressed [verified: the gate fails on the seed].
Options considered: a version column (no waiting) or a row lock (blocks the second device).
Choice and why: The version column, because it detects stale writes without waiting.
Pre-mortem: A guard comparing counts instead of versions; the gate writes with an old version.
How I'd know I'm wrong: A write with an old version is accepted.
"""

# A stand-in `claude` CLI. As a worker it edits server.py and prints its final message, with
# the reasoning note unless a no-note marker sits next to it; as a reviewer it approves.
STAND_IN = """
import json, sys
from pathlib import Path
HERE = Path(sys.argv[0]).parent
prompt = sys.stdin.read()
if not Path('review.json').is_file():
    (HERE / 'brief.md').write_text(prompt)
    Path('server.py').write_text('VERSION_CHECK = True\\n')
    said = 'Restored the check [verified: ran the gate].'
    if not (HERE / 'no-note').exists():
        said = %r + '\\n## Summary\\n' + said
    print(json.dumps({'type': 'result', 'result': said}))
    raise SystemExit(0)
packet = json.loads(Path('review.json').read_text())
(HERE / 'review.json').write_text(json.dumps(packet))
(HERE / 'review.md').write_text(prompt)
report = {key: packet[key] for key in ('attempt_id', 'base_digest', 'candidate_digest')}
report.update(verdict='approve', summary='Checked.', findings=[],
              evidence={key: 'Read the diff.' for key in ('requirements', 'correctness', 'scope', 'tests',
                                                          'maintainability', 'security')})
print(json.dumps({'type': 'result', 'result': json.dumps(report)}))
""" % NOTE


class ReasoningNoteTests(unittest.TestCase):
    def test_a_complete_note_is_extracted_up_to_the_next_heading(self):
        note, problem = reasoning_note("Done.\n\n" + NOTE + "\n## Summary\nChanged server.py.")
        self.assertIsNone(problem)
        self.assertTrue(note.startswith("## Reasoning note\nUnderstanding:"))
        self.assertIn("How I'd know I'm wrong: A write", note)
        self.assertNotIn("Summary", note)

    def test_no_note_or_an_empty_field_is_missing_and_says_why(self):
        self.assertEqual(reasoning_note("Fixed it. Should work."), (None, "no '## Reasoning note' section"))
        for field in REASONING_FIELDS:
            with self.subTest(field=field):
                text = "\n".join(line if not line.startswith(field + ":") else field + ":"
                                 for line in NOTE.splitlines())
                note, problem = reasoning_note(text)
                self.assertIsNone(note)
                self.assertIn(field, problem)

    def test_bold_labels_lists_and_multiline_fields_count(self):
        text = ("### Reasoning note\n**Understanding:** fix it\n- **Assumptions:**\n  - one [assumed]\n"
                "Options considered: A or B\nChoice and why: A\nPre-mortem: race; locked it\n"
                "How I’d know I’m wrong: the gate fails\n")
        note, problem = reasoning_note(text)
        self.assertIsNone(problem)
        self.assertIn("one [assumed]", note)

    def test_a_claude_code_log_with_stderr_lines_still_yields_the_note(self):
        # The worker log holds stderr too (builder/process.py); review blocker on PR #56.
        from builder.brains import ADAPTERS
        result = json.dumps({"type": "result", "result": NOTE + "\n## Summary\nDone."})
        for log in (result, "(node:12) Warning: something\n" + result + "\n",
                    result + "\nnpm notice: update available\n"):
            with self.subTest(log=log[:20]):
                note, problem = reasoning_note(ADAPTERS["claude-code"].summary(log))
                self.assertIsNone(problem)
                self.assertEqual(note, NOTE.strip())
        self.assertEqual(ADAPTERS["claude-code"].summary("Error: not logged in"), "Error: not logged in")

    def test_the_last_note_wins_and_a_long_note_is_cut(self):
        first = NOTE.replace("Restore the stale-write version check.", "First draft.")
        note, _ = reasoning_note(first + "\n" + NOTE)
        self.assertNotIn("First draft.", note)
        note, problem = reasoning_note(NOTE + "x" * 20_000)
        self.assertIsNone(problem)
        self.assertLess(len(note), 9000)
        self.assertTrue(note.endswith("[note cut]"))


class SharedSkillTests(unittest.TestCase):
    def test_critical_thinking_is_in_every_role_and_every_frozen_role(self):
        self.assertEqual(SHARED_SKILLS, ("critical-thinking",))
        for role in PROFILES:
            with self.subTest(role=role):
                skills = profile(role)["skills"]
                self.assertEqual(list(skills)[0], "critical-thinking")
                self.assertIn("## Reasoning note", skills["critical-thinking"])
                self.assertIn("[verified]", skills["critical-thinking"])
                self.assertIn("critical-thinking", catalog()[role]["core_skills"])
                self.assertIn("## Skill: critical-thinking", render(profile(role)))
        writers = [role for role, (access, *_) in PROFILES.items() if access == "write"]
        contract = {"team": 1, "jobs": [{"id": role, "role": role} for role in writers]}
        frozen = freeze_team(contract)
        for key, data in [*frozen["jobs"].items(), ("reviewer", frozen["reviewer"]),
                          ("security_reviewer", frozen["security_reviewer"])]:
            with self.subTest(frozen=key):
                self.assertIn("critical-thinking", data["skills"])

    def test_the_shared_skill_cannot_be_selected_twice(self):
        with self.assertRaisesRegex(Exception, "unavailable"):
            profile("frontend", ["critical-thinking"])

    def test_the_brief_asks_for_the_note_and_the_reviewer_checks_verified_claims(self):
        contract = {"title": "T", "delivery": "patch", "checks": [], "jobs": [],
                    "requirements": [{"id": "R", "description": "d", "checks": ["G"]}]}
        job = {"id": "J", "role": "backend", "goal": "Fix", "paths": ["a.py"], "checks": ["G"]}
        with mock.patch("builder.providers.reviewed_text", return_value=""):
            brief = worker_prompt(contract, job, None, {}, None)
        self.assertIn("## Reasoning note", brief)
        packet = {"attempt_id": "a", "base_digest": "b", "candidate_digest": "c", "checks": [],
                  "reasoning_note": NOTE}
        text = review_prompt(profile("reviewer"), packet)
        self.assertIn("[verified]", text)
        self.assertIn("advisory finding with category other", text)
        self.assertIn("reasoning_note", text)
        missing = review_prompt(profile("reviewer"), {**packet, "reasoning_note": None})
        self.assertIn("gave no reasoning note", missing)


class DepthRuleTests(unittest.TestCase):
    """Launched workers at each depth, on a stand-in Claude Code CLI."""
    setUp = test_planning.PlanningTests.setUp
    full = test_planning.PlanningTests.full
    focused = test_planning.PlanningTests.focused
    write = test_planning.PlanningTests.write
    report = test_planning.PlanningTests.report

    def stand_in(self, note=True):
        bin_dir = Path(self.temp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        exe = bin_dir / "claude"
        exe.write_text(f"#!{sys.executable}\n" + STAND_IN)
        exe.chmod(0o700)
        if not note:
            (bin_dir / "no-note").write_text("")
        patcher = mock.patch.dict(os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        patcher.start()
        self.addCleanup(patcher.stop)
        return bin_dir

    def approve_full(self):
        self.full()
        review_plan(self.runner, report=self.report(), external_attested=True)
        self.runner.approve(self.runner.review()["digest"])

    def approve_skip(self):
        narrow = test_planning.narrow
        narrow(self.root)
        self.runner.approve(self.runner.review()["digest"])

    def run_once(self):
        return self.runner.run(Selection(worker="claude-code", settings={}), trust_host=True, reserve=0)

    def test_full_depth_keeps_the_note_and_the_reviewer_sees_it(self):
        bin_dir = self.stand_in()
        self.approve_full()
        result = self.run_once()
        self.assertEqual(result["status"], "complete")
        attempt = self.runner.state()["attempts"][-1]
        self.assertEqual(attempt["outcome"], "accepted")
        saved = self.root / attempt["reasoning_note"]
        self.assertEqual(saved, self.runner.attempt_dir(attempt) / "reasoning.md")
        self.assertEqual(saved.read_text(), NOTE.strip() + "\n")
        self.assertEqual(json.loads((bin_dir / "review.json").read_text())["reasoning_note"], NOTE.strip())
        self.assertIn("[verified]", (bin_dir / "review.md").read_text())
        self.assertIn("critical-thinking", (bin_dir / "brief.md").read_text())

    def test_full_depth_rejects_a_missing_note_as_a_process_failure(self):
        bin_dir = self.stand_in(note=False)
        self.approve_full()
        self.run_once()
        state = self.runner.state()
        first = state["attempts"][0]
        self.assertEqual((first["outcome"], first["failure_kind"]), ("rejected", "process"))
        self.assertIn("reasoning note", first["reason"])
        self.assertEqual(first["checks"], [])  # rejected before any gate ran
        self.assertNotIn("review", first)
        # The retry's brief carries the reason, labelled as a process failure.
        self.assertIn("skipped a required step", (bin_dir / "brief.md").read_text())

    def test_skip_depth_warns_and_continues_without_a_note(self):
        bin_dir = self.stand_in(note=False)
        self.approve_skip()
        self.assertEqual(self.run_once()["status"], "complete")
        attempt = self.runner.state()["attempts"][-1]
        self.assertEqual(attempt["outcome"], "accepted")
        self.assertNotIn("reasoning_note", attempt)
        self.assertEqual(len(attempt["warnings"]), 1)
        self.assertIn("no '## Reasoning note' section", attempt["warnings"][0])
        self.assertIsNone(json.loads((bin_dir / "review.json").read_text())["reasoning_note"])

    def test_focused_depth_warns_and_continues_without_a_note(self):
        self.stand_in(note=False)
        self.focused()
        review_plan(self.runner, report=self.report(), external_attested=True)
        self.runner.approve(self.runner.review()["digest"])
        self.assertEqual(self.runner.review()["files"]["planning"]["depth"], "focused")
        self.assertEqual(self.run_once()["status"], "complete")
        self.assertIn("warnings", self.runner.state()["attempts"][-1])


if __name__ == "__main__":
    unittest.main()
