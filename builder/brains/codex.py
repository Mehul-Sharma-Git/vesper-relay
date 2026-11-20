"""Codex CLI (``codex exec``), moved unchanged from the old provider module.

Flags: ``exec`` (non-interactive, prompt ``-`` on stdin), ``-c approval_policy="never"``,
``--skip-git-repo-check``, ``--sandbox workspace-write|read-only``, ``--ignore-user-config``,
``--json``, ``--output-last-message FILE``, ``-m MODEL``, ``-c model_reasoning_effort="LEVEL"``.
Codex has no turn-limit flag; the wall-time limit bounds it. Its ``--output-schema`` is not
wired yet, so it is not declared strict and reviewers rely on the tolerant parser.

Events and tokens (P2-T10): ``--json`` prints Codex's events to stdout as JSON lines. The
call's log holds stdout and stderr together, so non-JSON lines (warnings) sit between the
events. The reviewer's and consultant's reply still arrives through ``--output-last-message``;
the log is never the reply (``reply_in_log``). Each ``turn.completed`` event carries a
``usage`` block; in codex-cli 0.170.0 its fields are ``input_tokens``, ``cached_input_tokens``,
``cache_write_input_tokens``, ``output_tokens`` and ``reasoning_output_tokens`` (the serde
names of its exec ``Usage``). The cached and cache-write counts are part of ``input_tokens``
and the reasoning count is part of ``output_tokens``, so ``usage`` returns only
``input_tokens`` and ``output_tokens``, summed over the turns: ``usage.total_tokens`` adds every
number in the dict, and each token must count once.

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
import json

from .base import READ_TOOLS, WORKER_TOOLS, Adapter, Capabilities

COUNTED = ("input_tokens", "output_tokens")  # no overlap; see the module docstring


def events(text):
    """(event or None, line) for each non-empty line of a log: None for a line that is not a
    JSON object (stderr, or an event cut off where a tail read began)."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            event = None
        yield (event if isinstance(event, dict) else None), line


class Codex(Adapter):
    name = "codex"
    binary = "codex"
    capabilities = Capabilities(edit_files=True, run_shell=True, strict_output=False, model_select=True,
                                effort_select=True, usage_report=True,
                                sandbox_login=("file", "~/.codex/auth.json"))
    credentials = ("OPENAI_API_KEY", "CODEX_HOME")
    # The API, plus ChatGPT sign-in (chatgpt.com) and its token refresh (auth.openai.com).
    sandbox_hosts = ("api.openai.com", "chatgpt.com", "auth.openai.com")
    login_help = "run `codex login` on this machine (it writes ~/.codex/auth.json)"
    install_help = "npm install -g @openai/codex"
    help_command = ("exec", "--help")
    reply_in_log = False  # with --json the log is the event stream, never the reply

    def command(self, mode, response, model, effort, program):
        output = ["--output-last-message", str(response)] if response else []
        choice = (["-m", model] if model else []) + (
            ["-c", f'model_reasoning_effort="{effort}"'] if effort else [])
        return [program or self.executable(), "exec", "-c", 'approval_policy="never"', "--skip-git-repo-check",
                "--sandbox", mode, "--ignore-user-config", "--json", *output, *choice, "-"]

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

    def usage(self, text):
        """Input and output tokens summed over every turn's usage block in the event log."""
        totals, found = dict.fromkeys(COUNTED, 0), False
        for event, _ in events(text):
            counts = event.get("usage") if event and event.get("type") == "turn.completed" else None
            if not isinstance(counts, dict):
                continue
            for key in COUNTED:
                if type(counts.get(key)) is int:
                    totals[key] += counts[key]
                    found = True
        return totals if found else None

    def summary(self, text):
        """The agent's messages and errors, plus any plain lines (stderr); never raw events."""
        said = []
        for event, line in events(text):
            if event is None:
                if not line.endswith("}"):  # a line ending in } is a cut-off event
                    said.append(line)
                continue
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            error = event.get("error") if isinstance(event.get("error"), dict) else {}
            for value in ((item.get("text") if event.get("type") == "item.completed"
                           and item.get("type") == "agent_message" else None),
                          event.get("message") if event.get("type") == "error" else None,
                          error.get("message") if event.get("type") == "turn.failed" else None):
                if isinstance(value, str) and value.strip():
                    said.append(value.strip())
        return "\n".join(said)
