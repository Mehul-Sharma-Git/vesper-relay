"""Claude Code (``claude``). Flags checked against Claude Code 2.1.81 ``claude --help``:
``-p`` (print, prompt on stdin), ``--tools``/``--allowedTools``, ``--permission-mode``,
``--strict-mcp-config``/``--mcp-config``, ``--max-turns``, ``--output-format json``,
``--json-schema``, ``--model``, ``--effort`` (low, medium, high, max).

Tools (P1-T10): read is ``Read``, edit ``Edit``, write ``Write``, search ``Glob,Grep`` and
shell ``Bash``. ``--tools`` limits the built-in tools to that list and ``--allowedTools``
lets them run without a prompt.

``vesper doctor`` (P1-T11) checks these flags against ``claude --help``. ``--max-turns`` is
accepted but not listed there (Claude Code 2.1.327, the image's pinned version), so it is
declared hidden. ``--restricted`` is listed there, but Claude Code 2.1.81 rejects it
("unknown option"), so a host CLI that old fails ``vesper doctor`` (finding 37).

Inside a sandbox it logs in with ``CLAUDE_CODE_OAUTH_TOKEN`` from ``claude setup-token``:
the Mac keeps the normal login in the Keychain, which a sandbox cannot reach.
"""
import json

from .base import READ_TOOLS, WORKER_TOOLS, Adapter, Capabilities

# Each Vesper tool name as Claude Code tools, in a fixed order.
NAMES = (("read", ("Read",)), ("edit", ("Edit",)), ("write", ("Write",)), ("search", ("Glob", "Grep")),
         ("shell", ("Bash",)))


def tool_list(tools, read_only=False):
    granted = set(tools) - ({"edit", "write"} if read_only else set())
    return ",".join(name for tool, names in NAMES if tool in granted for name in names)


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
    install_help = "npm install -g @anthropic-ai/claude-code"
    hidden_flags = ("--max-turns",)

    def command(self, tools, output, model, effort, max_turns, program):
        choice = (["--model", model] if model else []) + (["--effort", effort] if effort else [])
        return [program or self.executable(), "--restricted", "-p", "--strict-mcp-config", "--mcp-config",
                '{"mcpServers":{}}', "--permission-mode", "dontAsk", "--tools", tools,
                "--allowedTools", tools, "--max-turns", str(max_turns), *output, *choice]

    def worker_command(self, *, model=None, effort=None, max_turns=20, program=None, tools=WORKER_TOOLS):
        # JSON output carries a usage block for the ledger (P2-T3); summary() keeps the human text.
        return self.command(tool_list(tools), ["--output-format", "json"], model, effort, max_turns, program)

    def summary(self, text):
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            return text
        return data["result"] if isinstance(data, dict) and isinstance(data.get("result"), str) else text

    def reviewer_command(self, *, response=None, schema=None, model=None, effort=None, max_turns=20,
                         program=None, tools=READ_TOOLS):
        output = ["--output-format", "json"]
        if schema is not None:
            output += ["--json-schema", json.dumps(schema, separators=(",", ":"))]
        return self.command(tool_list(tools, read_only=True), output, model, effort, max_turns, program)

    def consult_command(self, *, response=None, model=None, effort=None, max_turns=20, program=None,
                        tools=READ_TOOLS):
        return self.command(tool_list(tools, read_only=True), [], model, effort, max_turns, program)

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
