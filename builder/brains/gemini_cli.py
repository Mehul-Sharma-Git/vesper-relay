"""Gemini CLI (``gemini``). New in P1-T8.

The CLI was not installed on the implementation machine, so its flags come from the upstream
reference (google-gemini/gemini-cli ``docs/cli/cli-reference.md`` and ``docs/cli/headless.md``,
package version 0.70.0-nightly.20261110, read 2026-11-18). Re-check with ``gemini --help``
when it is installed:

- ``-p/--prompt TEXT``: "Prompt text. Appended to stdin input if provided. Forces
  non-interactive mode." The job prompt goes on stdin; ``-p`` adds one closing line.
- ``--approval-mode default|auto_edit|yolo|plan``: workers use ``auto_edit`` (file edits
  approved; anything else needs approval, which headless mode treats as deny); reviewers
  and consultants use ``plan`` ("a strict, read-only mode").
- ``-o/--output-format text|json|stream-json``: ``json`` is one object with ``response``
  (the final answer), ``stats`` (token usage per model) and, on failure, ``error``.
- ``-m/--model NAME`` (aliases ``auto``, ``pro``, ``flash``, ``flash-lite``).
- ``--allowed-mcp-server-names``: an allowlist; one unused name leaves no MCP server enabled.
- No effort flag, no JSON Schema flag, and no turn-limit flag (the turn limit is the
  ``model.maxSessionTurns`` setting; headless exit code 53 is "turn limit exceeded"). The
  wall-time limit bounds it.

Tools (P1-T10): file reading, search and (for ``auto_edit``) edits come with the approval
mode. Shell is the ``run_shell_command`` tool ("Shell tool (`run_shell_command`)",
docs/tools/shell.md); by default it needs a confirmation, which headless mode treats as a
deny (docs/reference/policy-engine.md: "In non-interactive mode, this is treated as
`deny`"). When shell is granted (only inside a Vesper sandbox) the command adds
``--allowed-tools run_shell_command`` ("Tools that are allowed to run without
confirmation"; marked deprecated in favour of policy files, still accepted by the pinned
CLI; ``vesper doctor`` re-checks it). Reviewers and consultants keep ``plan`` mode, so they
never edit or write; the docs do not say whether ``plan`` mode honours the shell allowance.

Inside a sandbox it logs in with ``GEMINI_API_KEY``.
"""

from ..contracts import BuilderError
from .base import READ_TOOLS, WORKER_TOOLS, Adapter, Capabilities

CLOSING = "Follow the instructions above, which came on standard input."
NO_MCP = ["--allowed-mcp-server-names", "vesper-none"]
SHELL = ["--allowed-tools", "run_shell_command"]


class GeminiCli(Adapter):
    name = "gemini-cli"
    binary = "gemini"
    capabilities = Capabilities(edit_files=True, run_shell=True, strict_output=False, model_select=True,
                                effort_select=False, usage_report=True,
                                sandbox_login=("env", "GEMINI_API_KEY"))
    sandbox_hosts = ("generativelanguage.googleapis.com", "cloudcode-pa.googleapis.com", "oauth2.googleapis.com")
    login_help = ("create a Gemini API key, then store it: security add-generic-password -s vesper-relay "
                  "-a GEMINI_API_KEY -w (or add it to ~/.config/vesper/secrets.env)")
    credentials = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION",
                   "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_APPLICATION_CREDENTIALS", "GEMINI_CLI_HOME")

    def command(self, mode, output, model, program, tools):
        choice = ["-m", model] if model else []
        shell = SHELL if "shell" in tools else []
        return [program or self.executable(), "--approval-mode", mode, "--output-format", output, *NO_MCP, *shell,
                *choice, "-p", CLOSING]

    def worker_command(self, *, model=None, effort=None, max_turns=20, program=None, tools=WORKER_TOOLS):
        return self.command("auto_edit", "text", model, program, tools)

    def reviewer_command(self, *, response=None, schema=None, model=None, effort=None, max_turns=20,
                         program=None, tools=READ_TOOLS):
        return self.command("plan", "json", model, program, tools)

    def consult_command(self, *, response=None, model=None, effort=None, max_turns=20, program=None,
                        tools=READ_TOOLS):
        return self.command("plan", "text", model, program, tools)

    @staticmethod
    def envelope(data):
        """True for the ``-o json`` envelope ({"response", "stats", "error"}), not a report."""
        return isinstance(data, dict) and ("response" in data or "error" in data) and "verdict" not in data

    def parse_result(self, text):
        # The reviewer log merges stdout and stderr, so lines may surround the envelope:
        # find it with the same tolerant search as a report, then decode what it carries.
        data = super().parse_result(text)
        if not self.envelope(data):
            return data
        if data.get("error") or not isinstance(data.get("response"), str):
            raise BuilderError("Reviewer brain returned an error")
        return super().parse_result(data["response"])

    def usage(self, text):
        try:
            data = super().parse_result(text)
        except BuilderError:
            return None
        data = data if self.envelope(data) else {}
        models = (data.get("stats") or {}).get("models") if isinstance(data.get("stats"), dict) else None
        if not isinstance(models, dict):
            return None
        return {name: {key: value for key, value in entry["tokens"].items() if type(value) is int}
                for name, entry in models.items()
                if isinstance(entry, dict) and isinstance(entry.get("tokens"), dict)} or None
