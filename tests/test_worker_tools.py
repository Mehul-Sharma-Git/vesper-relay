"""Worker tool layer (P1-T10): per-role tools, shell only inside a real sandbox.

Each role lists its tools in ``team.PROFILES``; the core grants shell only when a real
sandbox backend (docker, podman) runs the brain, and adapters translate the granted tools
into their own flags. Reviewers and consultants never get edit or write.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.brains import ADAPTERS, Brain, Selection, arguments, command, job as brain_job, tools
from builder.contracts import BuilderError
from builder.runner import Runner
from builder.sandbox import Docker, Podman, secrets
from builder.team import PROFILES, catalog, profile, tools as role_tools

import test_rc1
from test_sandbox import FakeSandbox

WRITERS = [role for role, entry in PROFILES.items() if entry[0] == "write"]
CONSULTANTS = [role for role, entry in PROFILES.items() if entry[0] == "consult"]
SHELL_PROMPT = "You can run commands inside your workspace."


def value_after(argv, flag):
    return [argv[index + 1] for index, item in enumerate(argv) if item == flag]


def grants_shell(name, argv):
    """True when an adapter's command lets the brain run any command it chooses."""
    argv = list(argv)
    if name == "claude-code":
        return "Bash" in value_after(argv, "--tools")[0].split(",")
    if name == "codex":
        return value_after(argv, "--sandbox") == ["danger-full-access"]
    return "run_shell_command" in ",".join(value_after(argv, "--allowed-tools"))


def grants_edit(name, argv):
    """True when an adapter's command lets the brain edit or write files."""
    argv = list(argv)
    if name == "claude-code":
        return bool({"Edit", "Write"} & set(value_after(argv, "--tools")[0].split(",")))
    if name == "codex":
        return value_after(argv, "--sandbox") != ["read-only"]
    return value_after(argv, "--approval-mode") != ["plan"]


class RoleToolTests(unittest.TestCase):
    def test_every_role_lists_its_tools(self):
        for role in WRITERS:
            self.assertEqual(role_tools(role), ("read", "edit", "write", "search", "shell"), role)
        self.assertEqual(role_tools("reviewer"), ("read", "search", "shell"))
        for role in CONSULTANTS:
            self.assertEqual(role_tools(role), ("read", "search"), role)
        self.assertEqual({role: entry["tools"] for role, entry in catalog().items()},
                         {role: list(role_tools(role)) for role in PROFILES})

    def test_unknown_role_is_refused(self):
        with self.assertRaises(BuilderError):
            role_tools("intern")

    def test_tools_stay_out_of_the_frozen_role_revision(self):
        # A role's revision fingerprints what the brain reads; the grant is the runner's policy.
        self.assertNotIn("tools", profile("frontend"))


class GrantTests(unittest.TestCase):
    def brain(self, name):
        return Brain(name, ADAPTERS[name])

    def test_shell_only_with_a_real_sandbox(self):
        for name in ADAPTERS:
            with self.subTest(adapter=name):
                self.assertIn("shell", tools(self.brain(name), "worker", "frontend", sandboxed=True))
                self.assertNotIn("shell", tools(self.brain(name), "worker", "frontend", sandboxed=False))

    def test_roles_outside_the_catalogue_get_the_operation_default(self):
        # Contracts without a team may name any role; such a worker is still a writer.
        brain = self.brain("claude-code")
        self.assertEqual(tools(brain, "worker", "implementer", sandboxed=True),
                         {"read", "edit", "write", "search", "shell"})
        self.assertEqual(tools(brain, "reviewer", "implementer", sandboxed=True), {"read", "search", "shell"})

    def test_shell_needs_the_adapter_capability(self):
        adapter = ADAPTERS["claude-code"]
        limited = adapter.capabilities._replace(run_shell=False)
        with mock.patch.object(type(adapter), "capabilities", limited):
            self.assertNotIn("shell", tools(self.brain("claude-code"), "worker", "backend", sandboxed=True))

    def test_reviewers_and_consultants_never_edit_or_write(self):
        for name in ADAPTERS:
            for operation, role in (("reviewer", "reviewer"), ("reviewer", "frontend"), ("consult", "planner"),
                                    ("consult", "backend")):
                for sandboxed in (True, False):
                    with self.subTest(adapter=name, operation=operation, role=role, sandboxed=sandboxed):
                        granted = tools(self.brain(name), operation, role, sandboxed)
                        self.assertFalse({"edit", "write"} & granted)

    def test_reviewer_gets_shell_in_the_sandbox_consultants_never(self):
        brain = self.brain("claude-code")
        self.assertEqual(tools(brain, "reviewer", sandboxed=True), {"read", "search", "shell"})
        for role in CONSULTANTS + WRITERS:
            self.assertEqual(tools(brain, "consult", role, sandboxed=True), {"read", "search"})


class AdapterFlagTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def host(self, name, operation, role=None):
        with mock.patch("builder.brains.base.shutil.which", return_value="/usr/local/bin/x"):
            return command(Brain(name, ADAPTERS[name]), operation, None, True, role=role)

    def test_worker_commands_include_shell_in_docker_and_podman(self):
        for name in ADAPTERS:
            for role in WRITERS:
                with self.subTest(adapter=name, role=role):
                    job = brain_job(Brain(name, ADAPTERS[name]), "worker", self.work, role=role)
                    self.assertTrue(grants_shell(name, job.argv), job.argv)
                    for engine in (Docker(image="vesper-sandbox:test"), Podman(image="vesper-sandbox:test")):
                        argv = engine.run_argv(job, "vesper-test", "none")
                        self.assertTrue(grants_shell(name, argv[argv.index("vesper-sandbox:test") + 1:]))

    def test_worker_commands_exclude_shell_with_none(self):
        for name in ADAPTERS:
            for role in WRITERS:
                with self.subTest(adapter=name, role=role):
                    argv = self.host(name, "worker", role)
                    self.assertFalse(grants_shell(name, argv), argv)
                    self.assertTrue(grants_edit(name, argv), argv)

    def test_host_commands_stay_as_before(self):
        # With no sandbox the commands are exactly the ones P1-T9 built.
        for name in ADAPTERS:
            for operation in ("worker", "reviewer", "consult"):
                with self.subTest(adapter=name, operation=operation):
                    with mock.patch("builder.brains.base.shutil.which", return_value="/usr/local/bin/x"):
                        self.assertEqual(self.host(name, operation),
                                         arguments(Brain(name, ADAPTERS[name]), operation))

    def test_reviewer_never_gets_edit_or_write(self):
        for name in ADAPTERS:
            with self.subTest(adapter=name, sandboxed=False):
                self.assertFalse(grants_edit(name, self.host(name, "reviewer")))
            with self.subTest(adapter=name, sandboxed=True):
                job = brain_job(Brain(name, ADAPTERS[name]), "reviewer", self.work, out=self.work)
                # In the sandbox the engine mounts the review copy read-only, whatever the CLI allows.
                self.assertTrue(job.work_readonly)
                argv = Docker(image="vesper-sandbox:test").run_argv(job, "vesper-test", "none")
                self.assertIn(f"type=bind,source={self.work},target=/work,readonly", value_after(argv, "--mount"))
                if name != "codex":
                    self.assertFalse(grants_edit(name, job.argv), job.argv)

    def test_a_sandboxed_codex_reviewer_can_run_commands(self):
        # P1-G run 3: inside the container Codex's own read-only sandbox (bubblewrap) cannot
        # create a user namespace, so every command failed and the critique read nothing.
        codex = Brain("codex", ADAPTERS["codex"])
        job = brain_job(codex, "reviewer", self.work, out=self.work)
        self.assertEqual(value_after(list(job.argv), "--sandbox"), ["danger-full-access"])
        self.assertEqual(value_after(self.host("codex", "reviewer"), "--sandbox"), ["read-only"])
        consult = brain_job(codex, "consult", self.work, out=self.work, role="planner")
        self.assertEqual(value_after(list(consult.argv), "--sandbox"), ["read-only"])
        claude = brain_job(Brain("claude-code", ADAPTERS["claude-code"]), "reviewer", self.work, out=self.work)
        self.assertEqual(value_after(list(claude.argv), "--tools"), ["Read,Glob,Grep,Bash"])

    def test_consultants_get_no_shell_even_in_the_sandbox(self):
        # `vesper consult` accepts writing roles too; a consultation still only reads.
        for name in ADAPTERS:
            for role in CONSULTANTS + WRITERS:
                with self.subTest(adapter=name, role=role):
                    argv = brain_job(Brain(name, ADAPTERS[name]), "consult", self.work, out=self.work, role=role).argv
                    self.assertFalse(grants_shell(name, argv), argv)
                    self.assertFalse(grants_edit(name, argv), argv)

    def test_writer_tools_cannot_reach_a_reviewer_command(self):
        writer = frozenset({"read", "edit", "write", "search", "shell"})
        for name in ADAPTERS:
            # Codex has no per-tool list: shell means danger-full-access, granted only in a sandbox
            # job, where the engine's read-only mount keeps the review copy unchanged (tested above).
            for granted in (writer, writer - {"shell"}) if name != "codex" else (writer - {"shell"},):
                with self.subTest(adapter=name, shell="shell" in granted):
                    argv = arguments(Brain(name, ADAPTERS[name]), "reviewer", program=ADAPTERS[name].binary,
                                     tools=granted)
                    self.assertFalse(grants_edit(name, argv), argv)

    def test_unknown_tools_are_refused(self):
        with self.assertRaises(BuilderError):
            arguments(Brain("claude-code", ADAPTERS["claude-code"]), "worker", program="claude",
                      tools=frozenset({"read", "network"}))


class RecordingSandbox(FakeSandbox):
    def __init__(self):
        super().__init__()
        self.inputs = []

    def run(self, job, *, input_text, log, timeout, on_start=None):
        self.inputs.append(input_text)
        return super().run(job, input_text=input_text, log=log, timeout=timeout, on_start=on_start)


class RunnerToolTests(unittest.TestCase):
    setUp = test_rc1.TeamTests.setUp
    cli = test_rc1.TeamTests.cli
    git = test_rc1.TeamTests.git
    plan = test_rc1.TeamTests.plan
    approve = test_rc1.TeamTests.approve

    def test_sandboxed_worker_gets_shell_and_is_told_to_run_the_app(self):
        project, command = self.plan()
        self.approve(command)
        fake = RecordingSandbox()
        with mock.patch.dict(os.environ, {"VESPER_STATE_DIR": self.env["VESPER_STATE_DIR"]}), \
                mock.patch.object(secrets, "keychain", return_value="token"):
            result = Runner(project).run(Selection(worker="claude-code", reviewer="claude-code", settings={}), fake)
        self.assertEqual(result["status"], "complete", result)
        worker, _, reviewer = fake.jobs
        self.assertTrue(grants_shell("claude-code", worker.argv))
        self.assertTrue(grants_edit("claude-code", worker.argv))
        self.assertFalse(grants_edit("claude-code", reviewer.argv))
        prompt = fake.inputs[0]
        self.assertIn(SHELL_PROMPT, prompt)
        self.assertIn("Run the project's own unit tests and start the app before finishing.", prompt)
        self.assertIn("Report the exact commands and results.", prompt)
        # Workers see the gates (owner decision, 2026-11-19): a copy in .vesper-gates/ and how to run each.
        self.assertIn(".vesper-gates/", prompt)
        self.assertIn("Run the gates before finishing.", prompt)

    def test_host_worker_is_told_to_read_the_gates_not_run_them(self):
        project, command = self.plan()
        self.approve(command)
        brief = Path(command("prepare")["brief"]).read_text()
        self.assertIn(".vesper-gates/", brief)
        self.assertIn("Read the gates", brief)
        self.assertNotIn("Run the gates before finishing.", brief)

    def test_prepared_attempt_on_the_host_is_not_told_about_shell(self):
        project, command = self.plan()
        self.approve(command)
        prepared = command("prepare")
        self.assertNotIn(SHELL_PROMPT, Path(prepared["brief"]).read_text())


if __name__ == "__main__":
    unittest.main()
