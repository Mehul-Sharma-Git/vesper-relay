"""Claude Code (``claude``). Flags checked against Claude Code 2.1.81 ``claude --help``:
``-p`` (print, prompt on stdin), ``--tools``/``--allowedTools``, ``--permission-mode``,
``--strict-mcp-config``/``--mcp-config``, ``--max-turns``, ``--output-format json``,
``--json-schema``, ``--model``, ``--effort`` (low, medium, high, max).

Inside a sandbox it logs in with ``CLAUDE_CODE_OAUTH_TOKEN`` from ``claude setup-token``:
the Mac keeps the normal login in the Keychain, which a sandbox cannot reach.
"""
import json

from .base import Adapter, Capabilities

WRITE_TOOLS = "Read,Edit,Write,Glob,Grep"
READ_TOOLS = "Read,Glob,Grep"


class ClaudeCode(Adapter):
    name = "claude-code"
    binary = "claude"
    capabilities = Capabilities(edit_files=True, run_shell=True, strict_output=True, model_select=True,
                                effort_select=True, usage_report=True,
                                sandbox_login=("env", "CLAUDE_CODE_OAUTH_TOKEN"))
    credentials = ("ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN")
    sandbox_hosts = ("api.anthropic.com",)
    sandbox_env = (("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1"), ("DISABLE_AUTOUPDATER", "1"))
    login_help = ("run `claude setup-token` once, then store the token: security add-generic-password "
                  "-s vesper-relay -a CLAUDE_CODE_OAUTH_TOKEN -w (or add it to ~/.config/vesper/secrets.env)")

    def command(self, tools, output, model, effort, max_turns, program):
        choice = (["--model", model] if model else []) + (["--effort", effort] if effort else [])
        return [program or self.executable(), "--restricted", "-p", "--strict-mcp-config", "--mcp-config",
                '{"mcpServers":{}}', "--permission-mode", "dontAsk", "--tools", tools,
                "--allowedTools", tools, "--max-turns", str(max_turns), *output, *choice]

    def worker_command(self, *, model=None, effort=None, max_turns=20, program=None):
        return self.command(WRITE_TOOLS, [], model, effort, max_turns, program)

    def reviewer_command(self, *, response=None, schema=None, model=None, effort=None, max_turns=20,
                         program=None):
        output = ["--output-format", "json"]
        if schema is not None:
            output += ["--json-schema", json.dumps(schema, separators=(",", ":"))]
        return self.command(READ_TOOLS, output, model, effort, max_turns, program)

    def consult_command(self, *, response=None, model=None, effort=None, max_turns=20, program=None):
        return self.command(READ_TOOLS, [], model, effort, max_turns, program)

    def usage(self, text):
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            return None
        counts = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(counts, dict):
            return None
        # Token counts only: Vesper never estimates in dollars.
        return {key: value for key, value in counts.items()
                if key.endswith("tokens") and type(value) is int} or None
