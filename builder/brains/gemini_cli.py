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

Inside a sandbox it logs in with ``GEMINI_API_KEY``.
"""
import json

from ..contracts import BuilderError
from .base import Adapter, Capabilities

CLOSING = "Follow the instructions above, which came on standard input."
NO_MCP = ["--allowed-mcp-server-names", "vesper-none"]


class GeminiCli(Adapter):
    name = "gemini-cli"
    binary = "gemini"
    capabilities = Capabilities(edit_files=True, run_shell=True, strict_output=False, model_select=True,
                                effort_select=False, usage_report=True,
                                sandbox_login=("env", "GEMINI_API_KEY"))
    credentials = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION",
                   "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_APPLICATION_CREDENTIALS", "GEMINI_CLI_HOME")

    def command(self, mode, output, model):
        choice = ["-m", model] if model else []
        return [self.executable(), "--approval-mode", mode, "--output-format", output, *NO_MCP, *choice,
                "-p", CLOSING]

    def worker_command(self, *, model=None, effort=None, max_turns=20):
        return self.command("auto_edit", "text", model)

    def reviewer_command(self, *, response=None, schema=None, model=None, effort=None, max_turns=20):
        return self.command("plan", "json", model)

    def consult_command(self, *, response=None, model=None, effort=None, max_turns=20):
        return self.command("plan", "text", model)

    @staticmethod
    def wrapper(text):
        try:
            data = json.loads(text.strip())
        except (ValueError, RecursionError):
            return None
        if isinstance(data, dict) and ("response" in data or "error" in data) and "verdict" not in data:
            return data
        return None

    def parse_result(self, text):
        data = self.wrapper(text)
        if data is None:
            return super().parse_result(text)
        if data.get("error") or not isinstance(data.get("response"), str):
            raise BuilderError("Reviewer brain returned an error")
        return super().parse_result(data["response"])

    def usage(self, text):
        data = self.wrapper(text) or {}
        models = (data.get("stats") or {}).get("models") if isinstance(data.get("stats"), dict) else None
        if not isinstance(models, dict):
            return None
        return {name: {key: value for key, value in entry["tokens"].items() if type(value) is int}
                for name, entry in models.items()
                if isinstance(entry, dict) and isinstance(entry.get("tokens"), dict)} or None
