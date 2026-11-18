import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.contracts import BuilderError
from builder.brains import ADAPTERS, Brain, LEGACY, command as brain_command
from builder.review_gate import decode_provider_report, prompt, report_schema

REPLIES = ROOT / "docs/plan/fixtures/pocket-todo/reviewer-replies"
STRICT_ENDING = "Return only the JSON object. No text before or after it."
TYPES = {"object": dict, "array": list, "string": str}


def schema_errors(schema, data, where="$"):
    """The JSON Schema subset the report schemas use (no third-party validator here)."""
    errors = []
    if "type" in schema and not isinstance(data, TYPES[schema["type"]]):
        return [f"{where}: expected {schema['type']}"]
    if "const" in schema and data != schema["const"]:
        errors.append(f"{where}: expected {schema['const']!r}")
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{where}: not one of {schema['enum']}")
    if isinstance(data, str) and len(data) < schema.get("minLength", 0):
        errors.append(f"{where}: too short")
    if isinstance(data, dict):
        errors += [f"{where}.{key}: missing" for key in schema.get("required", ()) if key not in data]
        for key, sub in schema.get("properties", {}).items():
            if key in data:
                errors += schema_errors(sub, data[key], f"{where}.{key}")
    if isinstance(data, list):
        if len(data) > schema.get("maxItems", len(data)):
            errors.append(f"{where}: too many items")
        for index, item in enumerate(data):
            errors += schema_errors(schema.get("items", {}), item, f"{where}[{index}]")
    return errors


def approved_report():
    return json.loads((REPLIES / "approved-report.json").read_text(encoding="utf-8"))


def packet_for(report, **extra):
    return {**{key: report[key] for key in ("attempt_id", "base_digest", "candidate_digest")}, **extra}


class ReportSchemaTests(unittest.TestCase):
    def test_accepts_the_real_approved_report(self):
        report = approved_report()
        self.assertIn("design", report["evidence"])
        self.assertEqual(schema_errors(report_schema(packet_for(report, design_review=True)), report), [])

    def test_rejects_a_missing_evidence_area(self):
        report = approved_report()
        del report["evidence"]["security"]
        errors = schema_errors(report_schema(packet_for(report, design_review=True)), report)
        self.assertEqual(errors, ["$.evidence.security: missing"])

    def test_design_area_required_only_for_design_review(self):
        report = approved_report()
        del report["evidence"]["design"]
        self.assertEqual(schema_errors(report_schema(packet_for(report)), report), [])
        self.assertTrue(schema_errors(report_schema(packet_for(report, design_review=True)), report))

    def test_binding_fields_verdict_and_findings_are_enforced(self):
        report = approved_report()
        schema = report_schema(packet_for(report, design_review=True))
        for change in ({"attempt_id": "other"}, {"candidate_digest": "0" * 64}, {"verdict": "maybe"},
                       {"summary": ""}, {"findings": [{"severity": "nit", "path": "a", "evidence": "e",
                                                        "recommendation": "r"}]},
                       {"findings": [{"severity": "advisory", "path": "a", "evidence": "e"}]}):
            with self.subTest(change=change):
                self.assertTrue(schema_errors(schema, {**report, **change}))

    def test_schema_is_plain_json(self):
        schema = report_schema(packet_for(approved_report()))
        self.assertEqual(json.loads(json.dumps(schema)), schema)


class PlanReportSchemaTests(unittest.TestCase):
    def critique(self, **change):
        return {"phase": "plan", "packet_digest": "d" * 64, "reviewer": "reviewer-abc",
                "verdict": "request_changes", "summary": "Checked retry semantics.",
                "evidence": {"requirements": "product.md", "architecture": "architecture.md",
                             "checks": "gate.py"},
                "findings": [{"severity": "blocking", "path": "plan/architecture.md:1",
                              "scenario": "Retry after lost response", "consequence": "Duplicate write",
                              "evidence": "No retry identity", "recommendation": "Add a request id."}],
                **change}

    def test_accepts_valid_and_rejects_missing_checks_evidence(self):
        from builder.planning import plan_report_schema
        schema = plan_report_schema("d" * 64, "reviewer-abc")
        self.assertEqual(schema_errors(schema, self.critique()), [])
        missing = self.critique(evidence={"requirements": "product.md", "architecture": "architecture.md"})
        self.assertEqual(schema_errors(schema, missing), ["$.evidence.checks: missing"])

    def test_binding_and_finding_fields_are_enforced(self):
        from builder.planning import plan_report_schema
        schema = plan_report_schema("d" * 64, "reviewer-abc")
        finding = self.critique()["findings"][0]
        for change in ({"phase": "build"}, {"packet_digest": "e" * 64}, {"reviewer": "planner-session"},
                       {"findings": [{key: value for key, value in finding.items() if key != "scenario"}]}):
            with self.subTest(change=change):
                self.assertTrue(schema_errors(schema, self.critique(**change)))


class ReviewerCommandTests(unittest.TestCase):
    schema = {"type": "object", "required": ["verdict"]}

    def command(self, name, operation="reviewer", schema=None, launcher=None):
        adapter = LEGACY[name]
        with mock.patch("builder.brains.base.shutil.which", return_value="/usr/local/bin/" + name):
            return brain_command(Brain(adapter, ADAPTERS[adapter]), operation, launcher, True,
                                 response=Path("r.json"), schema=schema)

    def test_claude_reviewer_command_carries_the_schema(self):
        command = self.command("claude", schema=self.schema)
        index = command.index("--json-schema")
        self.assertEqual(json.loads(command[index + 1]), self.schema)
        self.assertIn("--output-format", command)

    def test_schema_flag_only_for_a_native_claude_reviewer(self):
        self.assertNotIn("--json-schema", self.command("claude"))
        self.assertNotIn("--json-schema", self.command("claude", operation="worker", schema=self.schema))
        self.assertNotIn("--json-schema", " ".join(self.command("codex", schema=self.schema)))

    def test_launcher_command_is_unchanged(self):
        launcher = ROOT / "tests" / "stand-in-launcher"
        with mock.patch("builder.providers.check_launcher", return_value=str(launcher)):
            command = self.command("claude", schema=self.schema, launcher=str(launcher))
        self.assertEqual(command, [str(launcher), "reviewer", "claude"])

    def test_prompt_ends_with_strict_instruction(self):
        packet = {"attempt_id": "a", "base_digest": "b", "candidate_digest": "c"}
        with mock.patch("builder.team.render", return_value="Reviewer role"):
            self.assertTrue(prompt({}, packet).endswith(STRICT_ENDING))


class StructuredOutputDecodeTests(unittest.TestCase):
    def wrapper(self, **fields):
        return json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "", **fields})

    def test_structured_output_is_the_report(self):
        report = approved_report()
        self.assertEqual(decode_provider_report(self.wrapper(structured_output=report)), report)

    def test_structured_output_wins_over_result_text(self):
        report = approved_report()
        text = self.wrapper(result=json.dumps({"verdict": "request_changes"}), structured_output=report)
        self.assertEqual(decode_provider_report(text), report)

    def test_failed_schema_retries_raise(self):
        text = self.wrapper(subtype="error_max_structured_output_retries", is_error=True, structured_output=None)
        with self.assertRaisesRegex(BuilderError, "provider returned an error"):
            decode_provider_report(text)

    def test_non_object_structured_output_falls_back_to_result(self):
        report = approved_report()
        self.assertEqual(decode_provider_report(self.wrapper(result=json.dumps(report),
                                                             structured_output=[report])), report)
        with self.assertRaisesRegex(BuilderError, "valid JSON report"):
            decode_provider_report(self.wrapper(structured_output=[report]))


class PlanCritiqueStrictOutputTests(unittest.TestCase):
    def test_review_plan_passes_schema_and_reads_structured_output(self):
        from builder.planning import review_plan
        from tests.test_planning import PlanningTests

        case = PlanningTests("test_canonical_contract_reaches_worker")
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.full()
        template = case.report()
        seen = {}

        def fake_run(command, *, cwd, input_text, env, log, timeout, **_):
            identity = re.search(r'"reviewer": "(reviewer-[0-9a-f]+)"', input_text).group(1)
            schema = json.loads(command[command.index("--json-schema") + 1])
            seen.update(schema=schema, identity=identity, prompt=input_text,
                        file=json.loads((cwd / "review.schema.json").read_text()))
            report = {**template, "reviewer": identity}
            self.assertEqual(schema_errors(schema, report), [])
            log.write_text(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                       "result": "", "structured_output": report}))
            return 0

        with mock.patch("builder.brains.base.shutil.which", return_value="/usr/local/bin/claude"), \
                mock.patch("builder.process.run_process", fake_run):
            result = review_plan(case.runner, brain=Brain("claude-code", ADAPTERS["claude-code"]), trust_host=True)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(seen["schema"], seen["file"])
        self.assertEqual(seen["schema"]["properties"]["reviewer"]["const"], seen["identity"])
        self.assertEqual(seen["schema"]["properties"]["packet_digest"]["const"], template["packet_digest"])
        self.assertTrue(seen["prompt"].endswith(STRICT_ENDING))


if __name__ == "__main__":
    unittest.main()
