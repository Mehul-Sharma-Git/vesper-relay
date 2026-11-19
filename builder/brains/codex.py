"""Codex CLI (``codex exec``), moved unchanged from the old provider module.

Flags: ``exec`` (non-interactive, prompt ``-`` on stdin), ``-c approval_policy="never"``,
``--skip-git-repo-check``, ``--sandbox workspace-write|read-only``, ``--ignore-user-config``,
``--output-last-message FILE``, ``-m MODEL``, ``-c model_reasoning_effort="LEVEL"``.
Codex has no turn-limit flag; the wall-time limit bounds it. Its ``--output-schema`` is not
wired yet, so it is not declared strict and reviewers rely on the tolerant parser.

Tools (P1-T10): Codex reads, searches and edits through its own command tool, confined by
its own ``--sandbox`` policy, so it has no per-tool list. Without shell (no sandbox backend)
the worker keeps ``workspace-write`` and reviewers and consultants ``read-only``, as before.
With shell, inside a Vesper sandbox, the worker gets ``danger-full-access``: the Codex config
reference describes it as disabling Codex's own sandboxing, "use only if your environment
already isolates processes" (learn.chatgpt.com/docs/config-file/config-advanced, read
2026-11-18); the container is that isolation (read-only root, /work the only writable mount,
provider hosts only). A reviewer granted shell (only inside a Vesper sandbox) gets
``danger-full-access`` too: there Codex's own Linux sandbox (bubblewrap) cannot create a user
namespace, so under ``read-only`` every command failed and a P1-G plan critique read nothing.
The engine mounts the review copy read-only, so the reviewer still cannot change it.
Consultants (never granted shell) and every reviewer on the host stay ``read-only``.

``vesper doctor`` (P1-T11) checks these flags against ``codex exec --help`` (all listed in
codex-cli 0.170.0, the image's pinned version).

Inside a sandbox it logs in through ``~/.codex/auth.json`` mounted read-only (or
``OPENAI_API_KEY``).
"""
from .base import READ_TOOLS, WORKER_TOOLS, Adapter, Capabilities


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
    install_help = "npm install -g @openai/codex"
    help_command = ("exec", "--help")

    def command(self, mode, response, model, effort, program):
        output = ["--output-last-message", str(response)] if response else []
        choice = (["-m", model] if model else []) + (
            ["-c", f'model_reasoning_effort="{effort}"'] if effort else [])
        return [program or self.executable(), "exec", "-c", 'approval_policy="never"', "--skip-git-repo-check",
                "--sandbox", mode, "--ignore-user-config", *output, *choice, "-"]

    def worker_command(self, *, model=None, effort=None, max_turns=20, program=None, tools=WORKER_TOOLS):
        mode = "danger-full-access" if "shell" in tools else "workspace-write"
        return self.command(mode, None, model, effort, program)

    def reviewer_command(self, *, response=None, schema=None, model=None, effort=None, max_turns=20,
                         program=None, tools=READ_TOOLS):
        mode = "danger-full-access" if "shell" in tools else "read-only"
        return self.command(mode, response, model, effort, program)

    def consult_command(self, *, response=None, model=None, effort=None, max_turns=20, program=None,
                        tools=READ_TOOLS):
        return self.command("read-only", response, model, effort, program)
