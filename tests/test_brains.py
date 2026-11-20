"""Brain adapters: any AI as Vesper's brain, one AI enough for every role (P1-T8)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.brains import ADAPTERS, Brain, Selection, command, parse_result, resolve, usage
from builder.contracts import BuilderError

import test_rc1
import stand_in  # noqa: F401  (test-only confirmer for protected actions, P2-T2)

CAPABILITIES = {"edit_files", "run_shell", "strict_output", "model_select", "effort_select",
                "usage_report", "sandbox_login"}
BINARIES = {"claude-code": "claude", "codex": "codex", "gemini-cli": "gemini"}
EVIDENCE = ("requirements", "correctness", "scope", "tests", "maintainability", "security")

# A `codex exec --json` log as the runner keeps it (P2-T10): stdout's JSONL events with the
# image's stderr lines mixed in (the log holds both). Field names are codex-cli 0.170.0's
# exec events. Two turns: 1200 + 1500 input tokens (800 and 1100 of them cached) and
# 90 + 60 output tokens (reasoning tokens are part of the output count).
CODEX_WARNING = ("WARNING: proceeding, even though we could not create PATH aliases: "
                 "Permission denied (os error 13)")
CODEX_EVENTS = "\n".join([
    CODEX_WARNING,
    '{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}',
    '{"type":"turn.started"}',
    '{"type":"item.completed","item":{"id":"item_0","type":"reasoning","text":"**Reading the packet**"}}',
    '{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"bash -lc ls",'
    '"aggregated_output":"review.json\\n","exit_code":0,"status":"completed"}}',
    "2026-11-21T09:14:03.120Z WARN codex_core::exec: shell snapshot unavailable",
    '{"type":"item.completed","item":{"id":"item_2","type":"agent_message","text":"Read the diff and the gate."}}',
    '{"type":"turn.completed","usage":{"input_tokens":1200,"cached_input_tokens":800,"output_tokens":90,'
    '"reasoning_output_tokens":40}}',
    '{"type":"turn.started"}',
    '{"type":"item.completed","item":{"id":"item_3","type":"agent_message","text":"All checks hold."}}',
    '{"type":"turn.completed","usage":{"input_tokens":1500,"cached_input_tokens":1100,'
    '"cache_write_input_tokens":0,"output_tokens":60,"reasoning_output_tokens":20}}',
]) + "\n"
CODEX_TOKENS = 1200 + 1500 + 90 + 60  # cached input is inside the input count

# One stand-in for every agent CLI. As a worker it fixes the spinner; as a reviewer (its
# working directory holds review.json) it approves in the adapter's own output format.
# Codex prints its event stream when given --json. Marker files next to calls.jsonl make the
# Codex worker fail (codex-worker-fails) or the Codex reviewer skip its reply file
# (codex-no-reply-file), printing the report into its log instead.
STAND_IN = """
import json, sys
from pathlib import Path
NAME = Path(sys.argv[0]).name
HERE = Path(sys.argv[0]).parent.parent
argv = sys.argv[1:]
prompt = sys.stdin.read()
with open(HERE / 'calls.jsonl', 'a') as calls:
    calls.write(json.dumps({'binary': NAME, 'argv': argv, 'review': Path('review.json').is_file()}) + '\\n')
if NAME == 'codex' and '--json' in argv:
    sys.stdout.write(%r)
if not Path('review.json').is_file():
    assert 'Fix spinner' in prompt
    Path('app.js').write_text('export const loading = false;\\n')
    if NAME == 'claude' and '--output-format' in argv:
        print(json.dumps({'type': 'result', 'result': 'Fixed the spinner.', 'usage': {'input_tokens': 20,
                                                                                      'output_tokens': 5}}))
    if NAME == 'codex' and (HERE / 'codex-worker-fails').exists():
        raise SystemExit(1)
    raise SystemExit(0)
packet = json.loads(Path('review.json').read_text())
report = {key: packet[key] for key in ('attempt_id', 'base_digest', 'candidate_digest')}
report.update(verdict='approve', summary='Independently verified the candidate.', findings=[],
              evidence={key: 'Read the diff and the gate result.' for key in %r})
text = json.dumps(report)
if NAME == 'claude':
    print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': text,
                      'usage': {'input_tokens': 11, 'output_tokens': 7}, 'total_cost_usd': 0.5}))
elif NAME == 'codex' and (HERE / 'codex-no-reply-file').exists():
    print(text)
elif NAME == 'codex':
    Path(argv[argv.index('--output-last-message') + 1]).write_text(text)
else:
    print(json.dumps({'response': 'Review done.\\n```json\\n' + text + '\\n```',
                      'stats': {'models': {'gemini-2.5-pro': {'tokens': {'prompt': 9, 'candidates': 4}}}}}))
""" % (CODEX_EVENTS, EVIDENCE)


class AdapterTests(unittest.TestCase):
    def build(self, adapter, operation, **kwargs):
        with mock.patch("builder.brains.base.shutil.which", return_value="/usr/local/bin/x"):
            return command(Brain(adapter, ADAPTERS[adapter], kwargs.pop("model", None), kwargs.pop("effort", None)),
                           operation, None, True, **kwargs)

    def test_three_v1_adapters_declare_every_capability(self):
        self.assertEqual(set(ADAPTERS), {"claude-code", "codex", "gemini-cli"})
        for name, adapter in ADAPTERS.items():
            with self.subTest(adapter=name):
                declared = adapter.capabilities
                self.assertEqual(set(declared._asdict()), CAPABILITIES)
                self.assertTrue(declared.edit_files)
                kind, value = declared.sandbox_login
                self.assertIn(kind, ("env", "file"))
                self.assertTrue(value)
                self.assertEqual(adapter.binary, BINARIES[name])
                for operation in ("worker", "reviewer", "consult"):
                    self.assertEqual(self.build(name, operation)[0], "/usr/local/bin/x")

    def test_launcher_receives_the_operation_and_the_cli_name(self):
        launcher = ROOT / "tests" / "test_brains.py"
        for name, binary in BINARIES.items():
            with mock.patch("builder.providers.check_launcher", return_value=str(launcher)):
                built = command(Brain(name, ADAPTERS[name]), "reviewer", str(launcher), False)
            self.assertEqual(built, [str(launcher), "reviewer", binary])

    def test_no_launcher_and_no_trust_is_refused(self):
        with self.assertRaisesRegex(BuilderError, "--launcher PATH or explicitly opt into --trust-host"):
            command(Brain("codex", ADAPTERS["codex"]), "worker", None, False)

    def test_schema_only_reaches_strict_output_brains(self):
        schema = {"type": "object"}
        for name, adapter in ADAPTERS.items():
            built = " ".join(self.build(name, "reviewer", schema=schema))
            with self.subTest(adapter=name):
                self.assertEqual("--json-schema" in built, adapter.capabilities.strict_output)
        self.assertNotIn("--json-schema", self.build("claude-code", "worker", schema=schema))

    def test_reviewers_and_consultants_are_read_only(self):
        for name, marker in (("claude-code", "Read,Glob,Grep"), ("codex", "read-only"), ("gemini-cli", "plan")):
            for operation in ("reviewer", "consult"):
                with self.subTest(adapter=name, operation=operation):
                    self.assertIn(marker, self.build(name, operation))
        self.assertIn("workspace-write", self.build("codex", "worker"))
        self.assertIn("auto_edit", self.build("gemini-cli", "worker"))

    def test_model_and_effort_follow_capabilities(self):
        claude = self.build("claude-code", "worker", model="opus", effort="high")
        self.assertEqual(claude[claude.index("--model") + 1], "opus")
        self.assertEqual(claude[claude.index("--effort") + 1], "high")
        codex = self.build("codex", "reviewer", model="gpt-x", effort="low")
        self.assertEqual(codex[codex.index("-m") + 1], "gpt-x")
        self.assertIn('model_reasoning_effort="low"', codex)
        self.assertEqual(codex[-1], "-")
        gemini = self.build("gemini-cli", "worker", model="flash")
        self.assertEqual(gemini[gemini.index("-m") + 1], "flash")
        settings = {"brains.quick.use": "gemini-cli", "brains.quick.effort": "high"}
        with self.assertRaisesRegex(BuilderError, "does not accept an effort"):
            resolve("quick", settings)
        with self.assertRaisesRegex(BuilderError, "brains.odd.model"):
            resolve("odd", {"brains.odd.use": "codex", "brains.odd.model": "x\" -c y"})

    def test_brain_names_resolve_through_config_then_adapters(self):
        settings = {"brains.strong.use": "claude-code", "brains.strong.model": "opus",
                    "brains.codex.use": "gemini-cli"}
        self.assertEqual(resolve("strong", settings), Brain("strong", ADAPTERS["claude-code"], "opus"))
        self.assertEqual(resolve("codex", settings).adapter, ADAPTERS["gemini-cli"])
        self.assertEqual(resolve("claude-code", {}).adapter, ADAPTERS["claude-code"])
        with self.assertRaisesRegex(BuilderError, "Unknown brain 'claude'"):
            resolve("claude", {})
        with self.assertRaisesRegex(BuilderError, "names adapter 'gpt'"):
            resolve("x", {"brains.x.use": "gpt"})

    def test_roles_map_to_brains_flag_then_config_then_fallback(self):
        settings = {"brains.strong.use": "codex", "brains.check.use": "gemini-cli",
                    "roles.frontend": "strong", "roles.reviewer": "check"}
        mapped = Selection(settings=settings)
        self.assertEqual(mapped.worker("frontend").name, "strong")
        self.assertEqual(mapped.reviewer(lambda: self.fail("fallback used")).name, "check")
        with self.assertRaisesRegex(BuilderError, "map role backend"):
            mapped.worker("backend")
        flagged = Selection(worker="claude-code", settings=settings)
        self.assertEqual(flagged.worker("frontend").name, "claude-code")
        self.assertEqual(flagged.reviewer(lambda: flagged.worker("frontend")).name, "check")
        alone = Selection(worker="claude-code", settings={})
        self.assertEqual(alone.reviewer(lambda: alone.worker("frontend")).name, "claude-code")
        self.assertEqual(Selection(reviewer="codex", settings=settings).reviewer().name, "codex")

    def test_results_decode_per_adapter_and_tolerantly(self):
        report = {"verdict": "approve"}
        text = json.dumps(report)
        claude = json.dumps({"type": "result", "result": "Done.\n```json\n" + text + "\n```",
                             "usage": {"input_tokens": 3, "output_tokens": 2}, "total_cost_usd": 1.0})
        gemini = json.dumps({"response": "Verdict below.\n" + text, "stats": {"models": {
            "gemini-2.5-pro": {"tokens": {"prompt": 5, "candidates": 1}}}}})
        cases = {"claude-code": claude, "codex": "Summary first.\n" + text, "gemini-cli": gemini}
        for name, output in cases.items():
            with self.subTest(adapter=name):
                self.assertEqual(parse_result(Brain(name, ADAPTERS[name]), output), report)
        with self.assertRaisesRegex(BuilderError, "returned an error"):
            parse_result(Brain("gemini-cli", ADAPTERS["gemini-cli"]),
                         json.dumps({"error": {"message": "quota"}}))
        self.assertEqual(usage(Brain("claude-code", ADAPTERS["claude-code"]), claude),
                         {"input_tokens": 3, "output_tokens": 2})
        self.assertEqual(usage(Brain("gemini-cli", ADAPTERS["gemini-cli"]), gemini),
                         {"gemini-2.5-pro": {"prompt": 5, "candidates": 1}})
        self.assertIsNone(usage(Brain("codex", ADAPTERS["codex"]), text))

    def test_codex_streams_events_and_keeps_its_reply_file(self):
        # P2-T10: --json puts the event stream (with token counts) on stdout; the reply still
        # arrives through --output-last-message, so decoding is unchanged.
        for operation in ("worker", "reviewer", "consult"):
            with self.subTest(operation=operation):
                argv = self.build("codex", operation, response=None if operation == "worker" else "/out/r.json")
                self.assertIn("--json", argv)
                self.assertEqual(argv[-1], "-")
                if operation != "worker":
                    self.assertEqual(argv[argv.index("--output-last-message") + 1], "/out/r.json")
        self.assertTrue(ADAPTERS["codex"].capabilities.usage_report)

    def test_codex_usage_sums_every_turn_of_its_event_log(self):
        from builder.usage import total_tokens
        codex = Brain("codex", ADAPTERS["codex"])
        counts = usage(codex, CODEX_EVENTS)
        self.assertEqual(counts, {"input_tokens": 2700, "output_tokens": 150})
        self.assertEqual(total_tokens(counts), CODEX_TOKENS)  # cached input counted once
        self.assertIsNone(usage(codex, "Plain text, no events.\n" + json.dumps({"verdict": "approve"})))
        no_usage = "\n".join(line for line in CODEX_EVENTS.splitlines() if "turn.completed" not in line)
        no_usage += '\n{"type":"turn.failed","error":{"message":"stream disconnected"}}\n'
        self.assertIsNone(usage(codex, no_usage))

    def test_codex_summary_keeps_messages_not_raw_events(self):
        said = ADAPTERS["codex"].summary(CODEX_EVENTS + '{"type":"error","message":"Reconnecting... 1/5"}\n')
        for text in ("Read the diff and the gate.", "All checks hold.", "Reconnecting... 1/5", CODEX_WARNING):
            self.assertIn(text, said)
        self.assertNotIn('"type"', said)
        self.assertNotIn("Reading the packet", said)  # reasoning is not a message
        # A tail read can start inside an event: the cut-off fragment is dropped too.
        self.assertNotIn("usage", ADAPTERS["codex"].summary(CODEX_EVENTS[CODEX_EVENTS.index("turn.completed") - 3:]))
        self.assertEqual(ADAPTERS["codex"].summary("Error: not logged in"), "Error: not logged in")

    def test_gemini_envelope_is_unwrapped_inside_a_noisy_log(self):
        # The reviewer log merges stdout and stderr, so lines may surround the envelope.
        report = {"verdict": "approve", "summary": "ok"}
        envelope = json.dumps({"response": "Done.\n```json\n" + json.dumps(report) + "\n```",
                               "stats": {"models": {"flash": {"tokens": {"prompt": 2}}}}})
        gemini = Brain("gemini-cli", ADAPTERS["gemini-cli"])
        for text in ("Loaded cached credentials.\n" + envelope, envelope + "\n[WARN] slow network",
                     "Loaded cached credentials.\n" + envelope + "\n[WARN] x"):
            with self.subTest(text=text[:30]):
                self.assertEqual(parse_result(gemini, text), report)
                self.assertEqual(usage(gemini, text), {"flash": {"prompt": 2}})
        with self.assertRaisesRegex(BuilderError, "returned an error"):
            parse_result(gemini, "Loaded cached credentials.\n" + json.dumps({"error": {"message": "quota"}}))

    def test_core_sentinel_names_are_reserved(self):
        for name in ("manual", "operator"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(BuilderError, "reserved"):
                    resolve(name, {f"brains.{name}.use": "codex"})
                with self.assertRaisesRegex(BuilderError, "reserved"):
                    Selection(settings={f"brains.{name}.use": "codex", "roles.frontend": name}).worker("frontend")

    def test_credentials_pass_only_to_their_own_brain_without_a_launcher(self):
        environ = {"PATH": "/bin", "HOME": "/h", "ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "o",
                   "GEMINI_API_KEY": "g", "PILOT_SECRET": "s"}
        for name, key in (("claude-code", "ANTHROPIC_API_KEY"), ("codex", "OPENAI_API_KEY"),
                          ("gemini-cli", "GEMINI_API_KEY")):
            with self.subTest(adapter=name):
                adapter = ADAPTERS[name]
                env = adapter.environment(None, environ)
                self.assertEqual(set(env), {"PATH", "HOME", key})
                self.assertEqual(set(adapter.environment("/launcher", environ)), {"PATH", "HOME"})

    def test_core_holds_no_vendor_names(self):
        for path in ("builder/runner.py", "builder/planning.py", "builder/contracts.py"):
            text = (ROOT / path).read_text(encoding="utf-8").lower()
            with self.subTest(path=path):
                self.assertNotIn("claude", text)
                self.assertNotIn("codex", text)
                self.assertNotIn("gemini", text)


class StandInRunTests(unittest.TestCase):
    """Full runs on stand-in CLIs: worker, gates and independent reviewer end to end."""
    setUp = test_rc1.TeamTests.setUp
    cli = test_rc1.TeamTests.cli
    git = test_rc1.TeamTests.git
    plan = test_rc1.TeamTests.plan
    approve = test_rc1.TeamTests.approve

    def stand_ins(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        for binary in BINARIES.values():
            exe = bin_dir / binary
            exe.write_text(f"#!{sys.executable}\n" + STAND_IN)
            exe.chmod(0o700)
        self.calls = self.root / "calls.jsonl"
        self.env["PATH"] = str(bin_dir) + os.pathsep + self.env["PATH"]

    def calls_made(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def config(self, text):
        path = Path(self.env["HOME"]) / ".config" / "vesper" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_one_brain_runs_every_role_to_complete(self):
        self.stand_ins()
        for name, binary in BINARIES.items():
            with self.subTest(adapter=name):
                self.calls.unlink(missing_ok=True)
                _, command = self.plan()
                self.approve(command)
                result = command("run", "--brain", name, "--trust-host")
                self.assertEqual(result["status"], "complete")
                attempt = result["attempts"][-1]
                self.assertEqual((attempt["provider"], attempt["adapter"]), (name, name))
                self.assertEqual((attempt["review"]["provider"], attempt["review"]["adapter"]), (name, name))
                self.assertEqual(attempt["review"]["verdict"], "approve")
                calls = self.calls_made()
                self.assertEqual([(call["binary"], call["review"]) for call in calls],
                                 [(binary, False), (binary, True)])
                self.assertEqual("usage" in attempt["review"], ADAPTERS[name].capabilities.usage_report)

    def test_every_ai_call_is_in_the_usage_ledger(self):
        # P2-T3: one line per AI call, with tokens when the adapter reports them.
        self.stand_ins()
        project, command = self.plan()
        self.approve(command)
        self.assertEqual(command("run", "--brain", "claude-code", "--reviewer-brain", "codex",
                                 "--trust-host")["status"], "complete")
        ledger = Path(self.env["VESPER_STATE_DIR"]) / "usage.jsonl"
        calls = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual([(call["kind"], call["role"], call["adapter"], call["account"], call["tokens"])
                          for call in calls],
                         [("call", "frontend", "claude-code", "claude", 25), ("call", "reviewer", "codex",
                                                                              "chatgpt", CODEX_TOKENS)])
        # P2-T10: Codex's tokens come from its event log; cached input is not added again.
        self.assertEqual(calls[1]["token_detail"], {"input_tokens": 2700, "output_tokens": 150})
        for call in calls:
            self.assertEqual((call["run"], call["job"]), (str(project.resolve()), "J1"))
            self.assertLessEqual(call["start"], call["end"])
        worker, reviewer = self.calls_made()
        self.assertEqual(worker["argv"][worker["argv"].index("--output-format") + 1], "json")
        self.assertIn("--json", reviewer["argv"])

    def test_a_failed_codex_workers_reason_shows_its_messages(self):
        self.stand_ins()
        (self.root / "codex-worker-fails").write_text("")
        _, command = self.plan()
        self.approve(command)
        command("run", "--brain", "codex", "--trust-host", code=1)
        attempt = command("status", code=1)["attempts"][-1]
        self.assertEqual(attempt["outcome"], "worker_failed")
        self.assertIn("exited 1", attempt["reason"])
        self.assertIn("All checks hold.", attempt["reason"])
        self.assertNotIn('"type"', attempt["reason"])
        self.assertNotIn("turn.completed", attempt["reason"])

    def test_a_codex_reviewer_without_a_reply_file_is_not_decoded_from_its_log(self):
        # The log holds the event stream (and here even a valid report): it is never the reply.
        self.stand_ins()
        (self.root / "codex-no-reply-file").write_text("")
        _, command = self.plan()
        self.approve(command)
        self.assertIn("wrote no reply", command("run", "--brain", "claude-code", "--reviewer-brain", "codex",
                                                "--trust-host", code=2))
        status = command("status")
        self.assertEqual(status["status"], "awaiting_review")  # the tested candidate stays pending
        self.assertNotIn("verdict", status["active"]["review"])
        self.assertEqual(status["attempts"], [])

    def test_a_different_reviewer_brain_also_completes(self):
        self.stand_ins()
        _, command = self.plan()
        self.approve(command)
        result = command("run", "--brain", "gemini-cli", "--reviewer-brain", "codex", "--trust-host")
        self.assertEqual(result["status"], "complete")
        attempt = result["attempts"][-1]
        self.assertEqual(attempt["adapter"], "gemini-cli")
        self.assertEqual(attempt["review"]["adapter"], "codex")
        self.assertEqual([(call["binary"], call["review"]) for call in self.calls_made()],
                         [("gemini", False), ("codex", True)])

    def test_config_maps_roles_to_named_brains(self):
        self.stand_ins()
        self.config('[brains.strong]\nuse = "gemini-cli"\nmodel = "flash"\n\n'
                    '[brains.reviewer]\nuse = "claude-code"\neffort = "high"\n\n'
                    '[roles]\nfrontend = "strong"\nreviewer = "reviewer"\n')
        _, command = self.plan()
        self.approve(command)
        result = command("run", "--trust-host")
        self.assertEqual(result["status"], "complete")
        attempt = result["attempts"][-1]
        self.assertEqual((attempt["provider"], attempt["review"]["provider"]), ("strong", "reviewer"))
        worker, reviewer = self.calls_made()
        self.assertEqual(worker["binary"], "gemini")
        self.assertEqual(worker["argv"][worker["argv"].index("-m") + 1], "flash")
        self.assertEqual(reviewer["binary"], "claude")
        self.assertEqual(reviewer["argv"][reviewer["argv"].index("--effort") + 1], "high")

    def test_missing_brain_is_refused_before_any_attempt(self):
        _, command = self.plan()
        self.approve(command)
        self.assertIn("map role frontend", command("run", "--trust-host", code=2))
        self.assertEqual(command("status")["attempts"], [])

    def test_provider_is_a_deprecated_alias(self):
        self.stand_ins()
        project, command = self.plan()
        self.approve(command)
        result = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "--project", str(project),
                                 "run", "--provider", "claude", "--reviewer-provider", "codex", "--trust-host"],
                                env=self.env, capture_output=True, text=True, cwd=self.repo)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--provider is deprecated", result.stderr)
        attempt = json.loads(result.stdout)["attempts"][-1]
        self.assertEqual((attempt["adapter"], attempt["review"]["adapter"]), ("claude-code", "codex"))
        self.assertIn("not allowed with argument", command("run", "--provider", "codex", "--brain", "codex",
                                                           "--trust-host", code=2))


if __name__ == "__main__":
    unittest.main()
