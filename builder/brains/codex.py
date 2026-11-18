"""Codex CLI (``codex exec``), moved unchanged from the old provider module.

Flags: ``exec`` (non-interactive, prompt ``-`` on stdin), ``-c approval_policy="never"``,
``--skip-git-repo-check``, ``--sandbox workspace-write|read-only``, ``--ignore-user-config``,
``--output-last-message FILE``, ``-m MODEL``, ``-c model_reasoning_effort="LEVEL"``.
Codex has no turn-limit flag; the wall-time limit bounds it. Its ``--output-schema`` is not
wired yet, so it is not declared strict and reviewers rely on the tolerant parser.

Inside a sandbox it logs in through ``~/.codex/auth.json`` mounted read-only (or
``OPENAI_API_KEY``).
"""
from .base import Adapter, Capabilities


class Codex(Adapter):
    name = "codex"
    binary = "codex"
    capabilities = Capabilities(edit_files=True, run_shell=True, strict_output=False, model_select=True,
                                effort_select=True, usage_report=False,
                                sandbox_login=("file", "~/.codex/auth.json"))
    credentials = ("OPENAI_API_KEY", "CODEX_HOME")
    # The API, plus ChatGPT sign-in (chatgpt.com) and its token refresh (auth.openai.com).
    sandbox_hosts = ("api.openai.com", "chatgpt.com", "auth.openai.com")
    login_help = "run `codex login` on this machine (it writes ~/.codex/auth.json)"

    def command(self, mode, response, model, effort, program):
        output = ["--output-last-message", str(response)] if response else []
        choice = (["-m", model] if model else []) + (
            ["-c", f'model_reasoning_effort="{effort}"'] if effort else [])
        return [program or self.executable(), "exec", "-c", 'approval_policy="never"', "--skip-git-repo-check",
                "--sandbox", mode, "--ignore-user-config", *output, *choice, "-"]

    def worker_command(self, *, model=None, effort=None, max_turns=20, program=None):
        return self.command("workspace-write", None, model, effort, program)

    def reviewer_command(self, *, response=None, schema=None, model=None, effort=None, max_turns=20,
                         program=None):
        return self.command("read-only", response, model, effort, program)

    def consult_command(self, *, response=None, model=None, effort=None, max_turns=20, program=None):
        return self.command("read-only", response, model, effort, program)
