"""Brains: any AI as Vesper's brain, named by purpose in the config.

A brain is a name the user chooses (``[brains.strong] use = "claude-code"``, optional
``model`` and ``effort``) or an adapter name used directly. Roles map to brains under
``[roles]`` (``frontend = "strong"``, ``reviewer = "reviewer"``). Every choice resolves as:
command flag > config > fallback. One brain is enough for every role: the reviewer's
independence comes from a fresh process, a read-only copy, no access to the worker's
reasoning and its own checklist, not from a different AI.

Brains of kind 1 (the host assistant in supervised mode) need no adapter: they drive Vesper
through its commands (``prepare``/``submit``, ``review-candidate --report``).
"""
import os
from pathlib import Path
import re
import shutil
import sys
from typing import NamedTuple
from uuid import uuid4

from ..contracts import require
from .base import Adapter, Capabilities
from .claude_code import ClaudeCode
from .codex import Codex
from .gemini_cli import GeminiCli

ADAPTERS = {adapter.name: adapter for adapter in (ClaudeCode(), Codex(), GeminiCli())}
# Deprecated --provider values (kept for one release) and the adapter each one meant.
LEGACY = {"claude": "claude-code", "codex": "codex"}
# Every brain's login variables: never passed to gates.
CREDENTIALS = frozenset(name for adapter in ADAPTERS.values() for name in adapter.credentials)
# Values the core records for work no brain did: a manual attempt and an attested report.
RESERVED = ("manual", "operator")
CHOICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
OPERATIONS = ("worker", "reviewer", "consult")


class Brain(NamedTuple):
    name: str
    adapter: Adapter
    model: str = None
    effort: str = None


def brain(name, adapter_name, model=None, effort=None):
    """A brain on one adapter, with the model and effort choices the adapter accepts."""
    adapter = ADAPTERS.get(adapter_name)
    require(adapter, f"Brain {name} names adapter {adapter_name!r}; known adapters: " + ", ".join(ADAPTERS))
    for value, capability, label in ((model, "model_select", "a model"), (effort, "effort_select", "an effort")):
        if value is None:
            continue
        key = f"brains.{name}.{label.split()[-1]}"
        require(isinstance(value, str) and CHOICE.fullmatch(value),
                f"{key} must be a plain name (letters, digits, . _ : / -)")
        require(getattr(adapter.capabilities, capability),
                f"Adapter {adapter.name} does not accept {label} choice ({key})")
    return Brain(name, adapter, model, effort)


def load_settings(environ=os.environ):
    """The effective config values (personal file, then the current directory's vesper.toml)."""
    from ..config import PROJECT_FILE, load_config, personal_path
    personal, explicit = personal_path(None, environ)
    values = load_config(personal, Path.cwd() / PROJECT_FILE, explicit=explicit)["values"]
    return {key: entry["value"] for key, entry in values.items()}


def resolve(name, settings):
    """A brain by name: a [brains.NAME] table in the config, else an adapter name."""
    require(isinstance(name, str) and name, "Name a brain")
    require(name not in RESERVED, f"Brain name {name!r} is reserved; choose another name under [brains]")
    use = settings.get(f"brains.{name}.use")
    if use is not None:
        return brain(name, use, settings.get(f"brains.{name}.model"), settings.get(f"brains.{name}.effort"))
    require(name in ADAPTERS, f"Unknown brain {name!r}: define [brains.{name}] in the config or use an "
                              "adapter name (" + ", ".join(ADAPTERS) + ")")
    return Brain(name, ADAPTERS[name])


def legacy(provider, flag="--provider"):
    """A deprecated --provider value as the brain it meant, with a warning."""
    replacement = "--reviewer-brain" if flag == "--reviewer-provider" else "--brain"
    print(f"vesper: {flag} is deprecated and will be removed; use {replacement} {LEGACY[provider]}",
          file=sys.stderr)
    return Brain(LEGACY[provider], ADAPTERS[LEGACY[provider]])


class Selection:
    """Which brain each role uses: the command flag, then [roles] in the config, then a fallback.

    ``worker`` and ``reviewer`` are flag values: a Brain, a brain name, or None. The config
    is read only when a name must be resolved.
    """

    def __init__(self, worker=None, reviewer=None, settings=None):
        self.flags = {"worker": worker, "reviewer": reviewer}
        self.settings = settings

    def values(self):
        if self.settings is None:
            self.settings = load_settings()
        return self.settings

    def named(self, value):
        return value if isinstance(value, Brain) else resolve(value, self.values())

    def worker(self, role):
        if self.flags["worker"]:
            return self.named(self.flags["worker"])
        mapped = self.values().get(f"roles.{role}")
        require(mapped, f"Choose --brain NAME or map role {role} to a brain under [roles] in the config")
        return resolve(mapped, self.values())

    def reviewer(self, fallback=None):
        """The reviewer brain; ``fallback`` (a callable, usually the job's worker brain) last."""
        if self.flags["reviewer"]:
            return self.named(self.flags["reviewer"])
        mapped = self.values().get("roles.reviewer")
        if mapped:
            return resolve(mapped, self.values())
        require(fallback, "Choose a reviewer brain (--brain NAME) or map reviewer under [roles] in the config")
        return fallback()


def arguments(brain, operation, *, response=None, schema=None, max_turns=20, program=None):
    """The brain's own command line for one operation, adapted to its capabilities."""
    adapter = brain.adapter
    choice = {"model": brain.model, "effort": brain.effort, "max_turns": max_turns, "program": program}
    if operation == "worker":
        return adapter.worker_command(**choice)
    if operation == "reviewer":
        return adapter.reviewer_command(response=response,
                                        schema=schema if adapter.capabilities.strict_output else None, **choice)
    return adapter.consult_command(response=response, **choice)


def job(brain, operation, work, *, out=None, schema=None, max_turns=20):
    """The sandbox job for one brain process: its CLI by bare name, the reply in /out."""
    from ..providers import review_limits
    from ..sandbox import agent_job
    review_limits(max_turns=max_turns)
    require(operation in OPERATIONS, f"Unknown brain operation {operation}")
    adapter = brain.adapter
    argv = arguments(brain, operation, response="/out/response.json" if out is not None else None,
                     schema=schema, max_turns=max_turns, program=adapter.binary)
    return agent_job(operation, argv, work, out=out, login=adapter.capabilities.sandbox_login,
                     hosts=adapter.sandbox_hosts, env=adapter.sandbox_env, login_help=adapter.login_help)


def command(brain, operation, launcher, trust_host, *, response=None, schema=None, max_turns=20):
    """Check that the brain can start and return its argv: a launcher gets ``<operation> <cli>`` and
    builds the command itself (it finds the schema as review.schema.json), a sandbox backend gets
    a job (its login is checked here), and the host gets the CLI directly."""
    from ..providers import check_launcher, review_limits
    from ..sandbox import Sandbox
    review_limits(max_turns=max_turns)
    require(operation in OPERATIONS, f"Unknown brain operation {operation}")
    require(launcher or trust_host, "Select --launcher PATH or explicitly opt into --trust-host")
    if isinstance(launcher, Sandbox):
        prepared = job(brain, operation, Path("/"), max_turns=max_turns)
        launcher.preflight(prepared)
        return list(prepared.argv)
    if launcher:
        return [check_launcher(launcher), operation, brain.adapter.binary]
    return arguments(brain, operation, response=response, schema=schema, max_turns=max_turns)


def launch(brain, operation, launcher, trust_host, *, work, input_text, log, timeout, response=None, schema=None,
           max_turns=20, on_start=None):
    """Run one brain process in ``work`` and return its exit status. A reply the brain writes to a
    file arrives at ``response``."""
    from ..process import run_process
    from ..sandbox import Sandbox
    if not isinstance(launcher, Sandbox):
        argv = command(brain, operation, launcher, trust_host, response=response, schema=schema,
                       max_turns=max_turns)
        return run_process(argv, cwd=work, input_text=input_text, env=environment(brain, launcher), log=log,
                           timeout=timeout, on_start=on_start or (lambda _: None))
    out = None
    if response is not None:
        out = Path(response).parent / ("out-" + uuid4().hex)
        out.mkdir()
    try:
        code = launcher.run(job(brain, operation, work, out=out, schema=schema, max_turns=max_turns),
                            input_text=input_text, log=log, timeout=timeout, on_start=on_start)
        reply = out / "response.json" if out else None
        if reply and reply.is_file() and not reply.is_symlink():
            os.replace(reply, response)
        return code
    finally:
        if out:
            shutil.rmtree(out, ignore_errors=True)


def environment(brain, launcher):
    return brain.adapter.environment(launcher)


def parse_result(brain, text):
    return brain.adapter.parse_result(text)


def usage(brain, text):
    """Token usage from a reply, only for brains that report it; otherwise time only."""
    return brain.adapter.usage(text) if brain.adapter.capabilities.usage_report else None


__all__ = ["ADAPTERS", "Brain", "Capabilities", "CREDENTIALS", "LEGACY", "Selection", "arguments", "brain",
           "command", "environment", "job", "launch", "legacy", "load_settings", "parse_result", "resolve",
           "usage"]
