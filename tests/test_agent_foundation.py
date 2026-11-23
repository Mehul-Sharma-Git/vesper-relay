"""Shared agent foundation (P3-T1, P3-T1b): the critical-thinking skill in every role, a worker
hand-off of labelled claims, and only those claims shown to the reviewer.

P3-T1b (owner, 23 Nov 2026): workers write no reasoning note. At P3-G Claude's
reasoning_extraction safeguard refused a brief that asked for one (appendix B, finding 65). The
design rationale lives in the plan (`options`, the architecture handoff). A note-shaped section
a worker writes anyway still never reaches the reviewer (00-context, "One AI is enough")."""
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
from builder.providers import CLAIMS_LIMIT, REASONING_FIELDS, handoff_claims, worker_prompt
from builder.review_gate import prompt as review_prompt
from builder.team import PROFILES, SHARED_SKILLS, catalog, freeze_team, profile, render
import test_planning
import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)

# A note-shaped section, as P3-T1's workers wrote it. Workers are no longer asked for one; if a
# worker writes one anyway, none of it may reach the reviewer.
NOTE = """## Reasoning note
Understanding: Restore the stale-write version check.
Assumptions: Only the check regressed [verified: the gate fails on the seed].
Options considered: a version column (no waiting) or a row lock (blocks the second device).
Choice and why: The version column, because it detects stale writes without waiting.
Pre-mortem: A guard comparing counts instead of versions; the gate writes with an old version.
How I'd know I'm wrong: A write with an old version is accepted.
"""
SUMMARY = "Restored the check [verified: ran the gate]."
# What a model must not be asked for (finding 65): a note by either name, or its fields.
NOTE_WORDS = ("reasoning note", "decision record", *(field.lower() + ":" for field in REASONING_FIELDS))

# A stand-in `claude` CLI. As a worker it edits server.py and prints its summary; a `note` file
# next to it adds a note-shaped section first, a `no-claims` file drops the labels. As a reviewer
# it approves.
STAND_IN = """
import json, sys
from pathlib import Path
HERE = Path(sys.argv[0]).parent
prompt = sys.stdin.read()
if not Path('review.json').is_file():
    (HERE / 'brief.md').write_text(prompt)
    Path('server.py').write_text('VERSION_CHECK = True\\n')
    said = 'Restored the check.' if (HERE / 'no-claims').exists() else %r
    if (HERE / 'note').exists():
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
""" % (SUMMARY, NOTE)


def names_no_note(test, text):
    lowered = text.lower()
    for word in NOTE_WORDS:
        test.assertNotIn(word, lowered)


class HandoffClaimsTests(unittest.TestCase):
    def test_the_reviewer_gets_the_hand_offs_labelled_claims_never_a_note(self):
        text = (NOTE + "\n## Summary\nRestored the check [verified: ran the gate].\nA plain line.\n"
                "- Old clients still work [Inferred from the unchanged route]\n- Fast enough [assumed]\n")
        self.assertEqual(handoff_claims(text), ["Restored the check [verified: ran the gate].",
                                                "- Old clients still work [Inferred from the unchanged route]",
                                                "- Fast enough [assumed]"])
        self.assertEqual(handoff_claims(NOTE), [])  # the note's own labels stay private
        self.assertEqual(handoff_claims("Done. Should work."), [])
        many = handoff_claims("\n".join(f"claim {n} [verified]" + "x" * 900 for n in range(200)))
        self.assertEqual(len(many), CLAIMS_LIMIT)
        self.assertTrue(all(len(line) <= 500 for line in many))

    def test_a_summary_without_a_heading_ends_the_note_at_its_last_field(self):
        # Review round 2 on PR #56: plain summary lines after the note.
        text = NOTE + "\nSummary: Restored the check [verified: ran checks/stale.py, exit 0].\n" \
                      "- Old clients still work [inferred from unchanged route]\n"
        self.assertEqual(handoff_claims(text), ["Summary: Restored the check [verified: ran checks/stale.py, exit 0].",
                                                "- Old clients still work [inferred from unchanged route]"])

    def test_a_note_in_another_form_never_reaches_the_reviewer(self):
        # Review round 2 on PR #56: a bold, #-level or "Reasoning note:" marker, or bare field lines.
        body = NOTE.split("\n", 1)[1]
        for marker in ("**Reasoning note**", "# Reasoning note", "Reasoning note:", "#### Reasoning Note", ""):
            with self.subTest(marker=marker):
                text = marker + "\n" + body + "\nDone [verified: ran tests].\n"
                self.assertEqual(handoff_claims(text), ["Done [verified: ran tests]."])
        stray = "Assumptions: the gate covers it [verified: read checks/a.py]\n  - and more [assumed]\n"
        self.assertEqual(handoff_claims(stray), [])  # an unfinished note runs to the end: nothing leaks

    def test_a_claude_code_log_with_stderr_lines_still_yields_the_claims(self):
        # The worker log holds stderr too (builder/process.py); review blocker on PR #56.
        from builder.brains import ADAPTERS
        result = json.dumps({"type": "result", "result": "## Summary\n" + SUMMARY})
        for log in (result, "(node:12) Warning: something\n" + result + "\n",
                    result + "\nnpm notice: update available\n"):
            with self.subTest(log=log[:20]):
                self.assertEqual(handoff_claims(ADAPTERS["claude-code"].summary(log)), [SUMMARY])
        self.assertEqual(ADAPTERS["claude-code"].summary("Error: not logged in"), "Error: not logged in")


class SharedSkillTests(unittest.TestCase):
    def test_critical_thinking_is_in_every_role_and_every_frozen_role(self):
        self.assertEqual(SHARED_SKILLS, ("critical-thinking",))
        for role in PROFILES:
            with self.subTest(role=role):
                skills = profile(role)["skills"]
                self.assertEqual(list(skills)[0], "critical-thinking")
                self.assertIn("[verified]", skills["critical-thinking"])
                self.assertIn("## Self-critique", skills["critical-thinking"])
                self.assertIn("critical-thinking", catalog()[role]["core_skills"])
                self.assertIn("## Skill: critical-thinking", render(profile(role)))
        writers = [role for role, (access, *_) in PROFILES.items() if access == "write"]
        contract = {"team": 1, "jobs": [{"id": role, "role": role} for role in writers]}
        frozen = freeze_team(contract)
        for key, data in [*frozen["jobs"].items(), ("reviewer", frozen["reviewer"]),
                          ("security_reviewer", frozen["security_reviewer"])]:
            with self.subTest(frozen=key):
                self.assertIn("critical-thinking", data["skills"])

    def test_the_skill_asks_for_no_note(self):
        # P3-T1b: the skill every role loads names no note, by either name, and none of its fields.
        names_no_note(self, profile("backend")["skills"]["critical-thinking"])

    def test_the_shared_skill_cannot_be_selected_twice(self):
        with self.assertRaisesRegex(Exception, "unavailable"):
            profile("frontend", ["critical-thinking"])

    def test_the_brief_asks_for_labelled_claims_and_no_note(self):
        contract = {"title": "T", "delivery": "patch", "checks": [], "jobs": [],
                    "requirements": [{"id": "R", "description": "d", "checks": ["G"]}]}
        job = {"id": "J", "role": "backend", "goal": "Fix", "paths": ["a.py"], "checks": ["G"]}
        with mock.patch("builder.providers.reviewed_text", return_value=""):
            brief = worker_prompt(contract, job, None, {}, None)
            with_skill = worker_prompt(contract, job, None, {}, None, specialist=profile("backend"))
        self.assertIn("[verified], [inferred] or [assumed]", brief)
        names_no_note(self, brief)
        names_no_note(self, with_skill)  # the worker brief as launched, with its role's skills

    def test_the_reviewer_checks_verified_claims(self):
        packet = {"attempt_id": "a", "base_digest": "b", "candidate_digest": "c", "checks": [],
                  "claims": ["Restored the check [verified: ran the gate]."]}
        text = review_prompt(profile("reviewer"), packet)
        self.assertIn("[verified]", text)
        self.assertIn("advisory finding with category other", text)
        self.assertIn("review.json lists claims", text)
        self.assertNotIn("Restored the check", text)  # the claims are data in review.json
        none = review_prompt(profile("reviewer"), {**packet, "claims": []})
        self.assertIn("labelled no claims", none)
        manual = review_prompt(profile("reviewer"), {key: packet[key] for key in packet if key != "claims"})
        self.assertNotIn("review.json lists claims", manual)  # a manual attempt has no hand-off to read
        self.assertNotIn("labelled no claims", manual)


class HandoffRunTests(unittest.TestCase):
    """Launched workers at each depth, on a stand-in Claude Code CLI."""
    setUp = test_planning.PlanningTests.setUp
    full = test_planning.PlanningTests.full
    focused = test_planning.PlanningTests.focused
    write = test_planning.PlanningTests.write
    report = test_planning.PlanningTests.report

    def stand_in(self, note=False, claims=True):
        bin_dir = Path(self.temp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        exe = bin_dir / "claude"
        exe.write_text(f"#!{sys.executable}\n" + STAND_IN)
        exe.chmod(0o700)
        if note:
            (bin_dir / "note").write_text("")
        if not claims:
            (bin_dir / "no-claims").write_text("")
        patcher = mock.patch.dict(os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        patcher.start()
        self.addCleanup(patcher.stop)
        return bin_dir

    def approve_full(self):
        self.full()
        review_plan(self.runner, report=self.report(), external_attested=True)
        self.runner.prove_checks()  # P3-T3: focused and full depth prove the checks
        self.runner.approve(self.runner.review()["digest"])

    def approve_skip(self):
        test_planning.narrow(self.root)
        self.runner.approve(self.runner.review()["digest"])

    def run_once(self):
        return self.runner.run(Selection(worker="claude-code", settings={}), trust_host=True, reserve=0)

    def test_full_depth_accepts_labelled_claims_without_a_note(self):
        bin_dir = self.stand_in()
        self.approve_full()
        self.assertEqual(self.run_once()["status"], "complete")
        attempts = self.runner.state()["attempts"]
        self.assertEqual(len(attempts), 1)  # no process rejection first
        attempt = attempts[0]
        self.assertEqual(attempt["outcome"], "accepted")
        self.assertNotIn("reasoning_note", attempt)
        self.assertNotIn("warnings", attempt)
        self.assertFalse((self.runner.attempt_dir(attempt) / "reasoning.md").exists())
        self.assertEqual(json.loads((bin_dir / "review.json").read_text())["claims"], [SUMMARY])
        self.assertIn("[verified]", (bin_dir / "review.md").read_text())
        names_no_note(self, (bin_dir / "brief.md").read_text())

    def test_a_note_shaped_section_stays_out_of_the_review(self):
        bin_dir = self.stand_in(note=True)
        self.approve_full()
        self.assertEqual(self.run_once()["status"], "complete")
        attempt = self.runner.state()["attempts"][-1]
        self.assertEqual(attempt["outcome"], "accepted")
        self.assertNotIn("reasoning_note", attempt)
        self.assertEqual(json.loads((bin_dir / "review.json").read_text())["claims"], [SUMMARY])
        for name in ("review.json", "review.md"):
            seen = (bin_dir / name).read_text()
            self.assertNotIn("blocks the second device", seen)
            self.assertNotIn("the gate fails on the seed", seen)

    def test_a_hand_off_without_labelled_claims_warns_at_full_depth(self):
        bin_dir = self.stand_in(claims=False)
        self.approve_full()
        self.assertEqual(self.run_once()["status"], "complete")
        attempt = self.runner.state()["attempts"][-1]
        self.assertEqual(attempt["outcome"], "accepted")
        self.assertEqual(len(attempt["warnings"]), 1)
        self.assertIn("labelled no claims", attempt["warnings"][0])
        self.assertEqual(json.loads((bin_dir / "review.json").read_text())["claims"], [])
        self.assertIn("labelled no claims", (bin_dir / "review.md").read_text())

    def test_a_hand_off_without_labelled_claims_warns_at_focused_depth(self):
        self.stand_in(claims=False)
        self.focused()
        review_plan(self.runner, report=self.report(), external_attested=True)
        self.runner.prove_checks()
        self.runner.approve(self.runner.review()["digest"])
        self.assertEqual(self.runner.review()["files"]["planning"]["depth"], "focused")
        self.assertEqual(self.run_once()["status"], "complete")
        self.assertIn("labelled no claims", self.runner.state()["attempts"][-1]["warnings"][0])

    def test_state_from_a_run_with_a_note_still_loads(self):
        # P3-T1b, Change 5: an attempt saved with reasoning_note and reasoning.md is read, not migrated.
        self.stand_in()
        self.approve_full()
        self.run_once()
        state_file = self.root / ".builder" / "state.json"
        state = json.loads(state_file.read_text())
        attempt = state["attempts"][-1]
        note = self.runner.attempt_dir(attempt) / "reasoning.md"
        note.write_text(NOTE)
        attempt["reasoning_note"] = str(note.relative_to(self.root))
        state_file.write_text(json.dumps(state))
        self.assertEqual(self.runner.status()["status"], "complete")
        self.assertEqual(self.runner.state()["attempts"][-1]["reasoning_note"], attempt["reasoning_note"])
        self.assertEqual(note.read_text(), NOTE)


if __name__ == "__main__":
    unittest.main()
