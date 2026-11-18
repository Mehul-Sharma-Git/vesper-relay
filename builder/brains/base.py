"""The base brain adapter: what every plug for one kind of AI declares and implements.

The core never names a vendor. It asks an adapter for a worker, reviewer or consult
command, the environment that process may see, and how to read its result, and it adapts
to the adapter's declared capabilities:

- no ``strict_output``: no schema is passed; the tolerant report parser reads the reply;
- no ``usage_report``: nothing but wall time is recorded for the call;
- no ``run_shell``: no brain process gets the shell tool, even inside a sandbox.

Tools (P1-T10) come from the role (``team.PROFILES``) as names: read, edit, write, search,
shell. The core grants shell only inside a real sandbox backend and never gives a reviewer
or consultant edit or write; each adapter translates the granted names into its own flags.
"""
import os
import shutil
from typing import NamedTuple

from ..contracts import require

# What a brain gets when the core passes no tools: today's file tools, never shell.
WORKER_TOOLS = frozenset({"read", "edit", "write", "search"})
READ_TOOLS = frozenset({"read", "search"})
# Workers and reviewers on the host see only these, plus their own brain's credentials.
BASE_ENV = frozenset({"PATH", "HOME", "LANG", "LC_ALL", "TERM", "TMPDIR", "USER", "LOGNAME"})


class Capabilities(NamedTuple):
    edit_files: bool      # can edit files in its workspace
    run_shell: bool       # can run commands (used only inside a sandbox, P1-T10)
    strict_output: bool   # can be held to a JSON Schema
    model_select: bool    # accepts a model choice
    effort_select: bool   # accepts an effort choice
    usage_report: bool    # reports tokens or usage per call
    sandbox_login: tuple  # ("env", NAME) or ("file", PATH mounted read-only) inside the sandbox


class Adapter:
    """One kind of brain. Subclasses set the class attributes and build the commands."""
    name = ""             # the adapter name used in config: [brains.X] use = "<name>"
    binary = ""           # the agent CLI; a launcher receives this name and builds its own command
    capabilities = None
    credentials = ()      # host variables that carry this brain's login (never given to gates)
    sandbox_hosts = ()    # the only hosts the brain may reach from the sandbox (HTTPS, through a proxy)
    sandbox_env = ()      # (name, value) pairs set inside the sandbox
    login_help = ""       # how to create the sandbox login named by capabilities.sandbox_login

    def executable(self):
        found = shutil.which(self.binary)
        require(found, f"Brain executable not found for adapter {self.name}: {self.binary}")
        return found

    # Every command takes ``program``: the CLI to start. None means this machine's
    # executable; the sandbox passes the bare name found on the image's PATH.
    # ``tools`` is the set of granted tool names (see the module docstring); "shell" in it
    # means the brain may run any command, which the core allows only inside a sandbox.
    def worker_command(self, *, model=None, effort=None, max_turns=20, program=None, tools=WORKER_TOOLS):
        """Edit the approved paths in the workspace (the current directory); prompt on stdin."""
        raise NotImplementedError

    def reviewer_command(self, *, response=None, schema=None, model=None, effort=None, max_turns=20,
                         program=None, tools=READ_TOOLS):
        """Read-only review of the copy in the current directory. ``response`` is a file the
        brain may write its final reply to; ``schema`` is given only to strict-output brains."""
        raise NotImplementedError

    def consult_command(self, *, response=None, model=None, effort=None, max_turns=20, program=None,
                        tools=READ_TOOLS):
        """Read-only consultation that returns a handoff as text."""
        raise NotImplementedError

    def parse_result(self, text):
        """Decode a reviewer reply into the report object (tolerant of prose and fences)."""
        from ..review_gate import decode_provider_report
        return decode_provider_report(text)

    def usage(self, text):
        """Token counts from a reviewer reply, or None. Called only when ``usage_report``."""
        return None

    def environment(self, launcher, environ=None):
        """The variables the brain's process sees. A launcher logs in on its own side."""
        environ = os.environ if environ is None else environ
        keys = BASE_ENV if launcher else BASE_ENV | set(self.credentials)
        return {key: value for key, value in environ.items() if key in keys}
