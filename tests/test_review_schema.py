import json
from pathlib import Path
import re
import subprocess
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
PLANNING_NOTE = ("plan/planning.json is Vesper's routing manifest: its architecture.revision is the "
                 "technical-lead role revision, not a digest of architecture.md")


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
    if isinstance(data, str) and "pattern" in schema and not re.search(schema["pattern"], data):
        errors.append(f"{where}: does not match {schema['pattern']}")
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

    def test_a_finding_cites_one_supplied_file_never_a_folder(self):
        # Codex (P1-G run 3) cited "plan/" and Claude (run 1) "seed/": each lost the whole critique.
        from builder.planning import plan_report_schema
        schema = plan_report_schema("d" * 64, "reviewer-abc")
        finding = self.critique()["findings"][0]
        for path in ("plan/architecture.md", "plan/architecture.md:12-30", "checks/api.py", "seed/app/main.go:4",
                     "seed/.env.example", "seed/..notes"):
            with self.subTest(path=path):
                self.assertEqual(schema_errors(schema, self.critique(findings=[{**finding, "path": path}])), [])
        # "plan/." is what Claude produced when asked for the folder under this schema.
        for path in ("plan/", "seed/", "checks/", "plan", "seed", "/etc/passwd", "plan//a.md", "docs/a.md",
                     "architecture.md", "plan/.", "plan/..", "plan/./a.md", "seed/a/../b.go"):
            with self.subTest(path=path):
                self.assertTrue(schema_errors(schema, self.critique(findings=[{**finding, "path": path}])))


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
        self.assertIn("never a folder", seen["prompt"])
        # P1-G: Codex twice blocked a plan because it read the role revision as an architecture digest.
        self.assertIn(PLANNING_NOTE, seen["prompt"])
        # P1-G: each critique round found new items of the same kinds, and Claude and Codex
        # disagreed on what blocks; the critic now sweeps each kind and blocks by a stated rule.
        for kind in ("who and what can reach the system", "concurrent changes to the same record",
                     "failure paths of each requirement", "gate adequacy"):
            self.assertIn(kind, seen["prompt"])
        self.assertIn("report every instance in this one review", seen["prompt"])
        self.assertIn("Blocking means:", seen["prompt"])
        # Only the owner accepts a risk, by approving the plan (00-context.md, Human-only approvals):
        # the critique never downgrades one on the plan's word; it reports each for the approval.
        self.assertIn("Accepted risk: owner must confirm", seen["prompt"])
        self.assertIn("the plan's own record of an acceptance is not the owner's confirmation", seen["prompt"])
        self.assertNotIn("confirmed by the owner in the decision log", seen["prompt"])
        # P1-G round 4: an unbounded gate-adequacy rule let Codex raise 22 blockers by inventing builds
        # made to slip past the gates. Gaps block only for plausible mistakes; security within the
        # owner's threat model, and a threat placed outside it still reaches the owner.
        self.assertIn("a plausible mistake by a competent engineer following the plan", seen["prompt"])
        self.assertIn("the candidate reviewer, who reads the code", seen["prompt"])
        self.assertIn("inside the owner's threat model", seen["prompt"])
        self.assertIn("every threat outside that model, whether or not the plan names it, is reported the same "
                      "way", " ".join(seen["prompt"].split()))
        # Data loss is not bounded by the security threat model (two of the owner's devices are not a threat).
        self.assertIn("a reachable data-loss exposure in the deployment the owner chose", seen["prompt"])
        self.assertNotIn("can be broken by an implementation that passes every gate", seen["prompt"])

        listed = re.search(r"Files you may cite: ([^\n]+)", seen["prompt"]).group(1).split(", ")
        self.assertIn("plan/architecture.md", listed)
        self.assertNotIn("plan", listed)

    def test_plan_roles_sweep_each_kind_and_name_what_a_gate_catches(self):
        def role(name):  # wrapped prose: compare with whitespace collapsed
            return " ".join((ROOT / "team/roles" / f"{name}.md").read_text().split())

        lead = role("technical-lead")
        for marker in ("Reachability,", "Concurrent changes,", "mitigate it in the contract with the gate",
                       "Only the owner accepts it, by approving the plan"):
            self.assertIn(marker, lead)
        qa = role("qa")
        self.assertIn("failure-path matrix", qa)
        self.assertIn("the wrong implementation that assertion catches", qa)
        planner = role("planner")
        self.assertIn("reachability and concurrent-change lists", planner)
        self.assertIn("a decision-log entry is not the owner's confirmation", planner)
        self.assertIn("threat model", planner)
        self.assertIn("Reachability, inside the owner's threat model", lead)
        self.assertIn("Concurrent changes, whatever the threat model", lead)
        self.assertIn("Aim the matrix at plausible mistakes", qa)

    def test_the_plan_critique_gets_ten_minutes_and_says_when_it_ran_out(self):
        # P1-G: a full sweep took Codex about 3 minutes; the 180 s reviewer default killed it,
        # and the error did not say why.
        from builder.planning import PLAN_REVIEW_TIMEOUT, review_plan
        from tests.test_planning import PlanningTests

        self.assertEqual(PLAN_REVIEW_TIMEOUT, 600)
        case = PlanningTests("test_canonical_contract_reaches_worker")
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.full()
        seen = []

        def fake_run(command, *, cwd, input_text, env, log, timeout, **_):
            seen.append(timeout)
            return 124

        with mock.patch("builder.brains.base.shutil.which", return_value="/usr/local/bin/claude"), \
                mock.patch("builder.process.run_process", fake_run), \
                self.assertRaisesRegex(BuilderError, "timed out after 600 s"):
            review_plan(case.runner, brain=Brain("claude-code", ADAPTERS["claude-code"]), trust_host=True)
        self.assertEqual(seen, [600])

    def test_review_plan_cli_defaults_to_ten_minutes(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "review-plan", "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("(default 600)", " ".join(result.stdout.split()))
        candidate = subprocess.run([sys.executable, "-B", str(ROOT / "build_local.py"), "review-candidate", "--help"],
                                   capture_output=True, text=True, check=True)
        self.assertIn("(default 180)", " ".join(candidate.stdout.split()))

    def test_a_rejected_critique_reply_is_kept_for_the_owner(self):
        from builder.planning import review_plan
        from tests.test_planning import PlanningTests

        case = PlanningTests("test_canonical_contract_reaches_worker")
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.full()
        template = case.report("request_changes")

        def fake_run(command, *, cwd, input_text, env, log, timeout, **_):
            identity = re.search(r'"reviewer": "(reviewer-[0-9a-f]+)"', input_text).group(1)
            finding = {**template["findings"][0], "path": "plan/"}
            report = {**template, "reviewer": identity, "findings": [finding]}
            log.write_text(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                       "result": "", "structured_output": report}))
            return 0

        with mock.patch("builder.brains.base.shutil.which", return_value="/usr/local/bin/claude"), \
                mock.patch("builder.process.run_process", fake_run), \
                self.assertRaisesRegex(BuilderError, r"Invalid relative path: 'plan/'.*kept in .*"
                                       r"plan-critique-rejected-1\.txt") as raised:
            review_plan(case.runner, brain=Brain("claude-code", ADAPTERS["claude-code"]), trust_host=True)
        kept = case.runner.control / "plan-critique-rejected-1.txt"
        self.assertIn(str(kept), str(raised.exception))
        self.assertIn('"path": "plan/"', kept.read_text(encoding="utf-8"))
        self.assertEqual(kept.stat().st_mode & 0o777, 0o600)
        self.assertFalse((case.runner.control / "plan-critique.json").exists())


if __name__ == "__main__":
    unittest.main()
