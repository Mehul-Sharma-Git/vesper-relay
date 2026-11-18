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
import sys
from typing import NamedTuple

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


def command(brain, operation, launcher, trust_host, *, response=None, schema=None, max_turns=20):
    """The argv for one brain process. A launcher gets ``<operation> <cli>`` and builds the
    command itself (it finds the schema as review.schema.json), so max_turns reaches only a
    direct brain."""
    from ..providers import check_launcher, review_limits
    review_limits(max_turns=max_turns)
    require(operation in OPERATIONS, f"Unknown brain operation {operation}")
    require(launcher or trust_host, "Select --launcher PATH or explicitly opt into --trust-host")
    adapter = brain.adapter
    if launcher:
        return [check_launcher(launcher), operation, adapter.binary]
    choice = {"model": brain.model, "effort": brain.effort, "max_turns": max_turns}
    if operation == "worker":
        return adapter.worker_command(**choice)
    if operation == "reviewer":
        return adapter.reviewer_command(response=response,
                                        schema=schema if adapter.capabilities.strict_output else None, **choice)
    return adapter.consult_command(response=response, **choice)


def environment(brain, launcher):
    return brain.adapter.environment(launcher)


def parse_result(brain, text):
    return brain.adapter.parse_result(text)


def usage(brain, text):
    """Token usage from a reply, only for brains that report it; otherwise time only."""
    return brain.adapter.usage(text) if brain.adapter.capabilities.usage_report else None


__all__ = ["ADAPTERS", "Brain", "Capabilities", "CREDENTIALS", "LEGACY", "Selection", "brain", "command",
           "environment", "legacy", "load_settings", "parse_result", "resolve", "usage"]
