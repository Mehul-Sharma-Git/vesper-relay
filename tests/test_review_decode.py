import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.contracts import BuilderError
from builder.brains import ADAPTERS, Brain
from builder.review_gate import decode_provider_report
import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)

REPLIES = ROOT / "docs/plan/fixtures/pocket-todo/reviewer-replies"
REPORT = {"attempt_id": "a1", "base_digest": "b2", "candidate_digest": "c3", "verdict": "approve",
          "summary": "Looked at everything.", "evidence": {"requirements": "product.md"}, "findings": []}


def fence(data, tag="json"):
    return f"```{tag}\n{json.dumps(data, indent=2)}\n```"


def wrapper(result, **fields):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": result, **fields})


class DecodeProviderReportTests(unittest.TestCase):
    def test_bare_object(self):
        self.assertEqual(decode_provider_report("  " + json.dumps(REPORT) + "\n"), REPORT)

    def test_fence_only(self):
        self.assertEqual(decode_provider_report(fence(REPORT)), REPORT)
        self.assertEqual(decode_provider_report(fence(REPORT, tag="")), REPORT)

    def test_prose_then_fence_from_live_run(self):
        reply = json.loads((REPLIES / "preamble-fence.json").read_text(encoding="utf-8"))
        self.assertTrue(reply["result"].startswith("I've read the whole diff"))
        report = decode_provider_report(reply["result"])
        self.assertEqual(report["verdict"], "approve")
        self.assertEqual(report["attempt_id"], "78bf719d2f6f4f3f9f2894447fdeff8a")

    def test_claude_wrapper_with_prose_and_fence(self):
        for name in ("preamble-fence.json", "preamble-fence-2.json"):
            with self.subTest(name):
                report = decode_provider_report((REPLIES / name).read_text(encoding="utf-8"))
                self.assertEqual(report["verdict"], "approve")
                self.assertIn("evidence", report)

    def test_two_fences_last_valid_wins(self):
        first = {**REPORT, "summary": "Draft."}
        text = f"Draft:\n\n{fence(first)}\n\nFinal answer:\n\n{fence(REPORT)}\n"
        self.assertEqual(decode_provider_report(text), REPORT)

    def test_invalid_fence_then_valid_fence(self):
        text = "Here:\n```json\n{\"verdict\": \"approve\",\n```\nCorrected:\n" + fence(REPORT)
        self.assertEqual(decode_provider_report(text), REPORT)

    def test_valid_fence_then_invalid_fence_uses_valid(self):
        text = fence(REPORT) + "\nAlso:\n```json\n{not json}\n```"
        self.assertEqual(decode_provider_report(text), REPORT)

    def test_fenced_array_is_not_a_report(self):
        text = "Result:\n```json\n[1, 2]\n```\n" + fence(REPORT)
        self.assertEqual(decode_provider_report(text), REPORT)

    def test_prose_with_no_json_raises(self):
        for text in ("I reviewed the diff and it looks fine.", "", "Use {braces} like this", "```json\nnope\n```"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(BuilderError, "valid JSON report"):
                    decode_provider_report(text)

    def test_wrapper_with_error_raises(self):
        failed = wrapper(fence(REPORT), is_error=True)
        out_of_turns = wrapper("x", subtype="error_max_turns")
        for text in (failed, out_of_turns):
            with self.subTest(text=text[:60]):
                with self.assertRaisesRegex(BuilderError, "provider returned an error"):
                    decode_provider_report(text)

    def test_top_level_array_is_rejected(self):
        with self.assertRaisesRegex(BuilderError, "valid JSON report"):
            decode_provider_report(json.dumps([REPORT]))

    def test_prose_then_bare_object_returns_top_level_object(self):
        text = "Verdict follows. " + json.dumps(REPORT) + " Thanks."
        self.assertEqual(decode_provider_report(text), REPORT)

    def test_stray_brace_in_prose_is_skipped(self):
        text = 'The key {"verdict" is below. ' + json.dumps(REPORT)
        self.assertEqual(decode_provider_report(text), REPORT)

    def test_hostile_replies_raise_builder_error(self):
        for text in ("x" + '{"a":' * 50_000, "x" + '{"' * 128_000, "[" * 256_000):
            with self.subTest(size=len(text)):
                with self.assertRaisesRegex(BuilderError, "valid JSON report"):
                    decode_provider_report(text)

    def test_progress_line_before_one_line_wrapper(self):
        text = "launcher: starting reviewer\n" + wrapper("Done.\n\n" + fence(REPORT))
        self.assertEqual(decode_provider_report(text), REPORT)


class PlanCritiqueDecodeTests(unittest.TestCase):
    def test_review_plan_accepts_prose_and_fence_critique(self):
        from builder.planning import review_plan
        from tests.test_planning import PlanningTests

        case = PlanningTests("test_canonical_contract_reaches_worker")
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.full()
        launcher = case.root.parent / "launcher"
        launcher.write_text(f"#!{sys.executable}\nraise SystemExit(1)\n")
        launcher.chmod(0o700)
        template = case.report()

        def fake_run(command, *, cwd, input_text, env, log, timeout, **_):
            self.assertEqual(command[1:], ["reviewer", "claude"])
            identity = re.search(r'"reviewer": "(reviewer-[0-9a-f]+)"', input_text).group(1)
            report = {**template, "reviewer": identity}
            log.write_text(wrapper("I checked the plan, checks and seed.\n\n" + fence(report)))
            return 0

        with mock.patch("builder.process.run_process", fake_run):
            result = review_plan(case.runner, brain=Brain("claude-code", ADAPTERS["claude-code"]), launcher=str(launcher))
        self.assertEqual(result["status"], "reviewed")
        self.assertTrue(result["report"]["reviewer"].startswith("reviewer-"))
        self.assertTrue((case.runner.control / "plan-critique.json").is_file())


if __name__ == "__main__":
    unittest.main()
