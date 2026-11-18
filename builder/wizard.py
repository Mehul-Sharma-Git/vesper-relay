"""`vesper setup`: an interactive first-run wizard that works for anyone, not just the owner.

It detects the OS and the AI CLIs on this machine, asks which brain does the work (one AI is
enough; a different reviewer is optional), checks the sandbox engine and offers its install
and start commands, builds the sandbox image, walks through the sandbox login of each brain
in use (secrets go to the macOS Keychain or the private secrets file, never the config), asks
for the plan-usage reserve, writes the personal config, and finishes with `vesper doctor`.

``ask``, ``hidden`` (for secrets) and ``say`` are the terminal; tests pass scripted ones.
Running commands for the user (Homebrew installs, ``colima start``, the image build) is
always offered, never done without a yes, and never uses sudo.
"""
from datetime import date
import os
from pathlib import Path
import tempfile

from .brains import ADAPTERS
from .config import DEFAULTS, load_config, personal_path
from .contracts import BuilderError
from .doctor import Probe, doctor, install_engine, render, start_engine
from .sandbox import SANDBOX_DIR, image_tag
from .team import PROFILES

ENGINES = ("docker", "podman")
WORKER_BRAIN, REVIEWER_BRAIN = "strong", "reviewer"


def choose(ask, say, question, options, default):
    """Ask until the answer is one of ``options`` (or its number in the list); empty means default."""
    options = list(options)
    while True:
        answer = ask(f"{question} ({', '.join(options)}) [{default}]: ").strip().lower()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        if answer in options:
            return answer
        say(f"Please answer one of: {', '.join(options)}.")


def confirm(ask, question, default):
    answer = ask(f"{question} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not answer else answer in ("y", "yes")


def offer(ask, say, probe, argv, text):
    """Show the fix; when it is a command Vesper may run, offer to run it."""
    say(f"  To fix it: {text}")
    if not argv:
        return False
    if confirm(ask, f"Run `{' '.join(argv)}` now?", False):
        code = probe.show(argv)
        say(f"  `{' '.join(argv)}` finished with exit {code}.")
        return code == 0
    return False


def pick_brains(ask, say, probe):
    found = [name for name, adapter in ADAPTERS.items() if probe.which(adapter.binary)]
    if found:
        say("AI command-line tools found: " + ", ".join(f"{name} ({ADAPTERS[name].binary})" for name in found))
    else:
        say("No supported AI command-line tool was found on this machine. Install one (one is enough):")
        for adapter in ADAPTERS.values():
            say(f"  {adapter.name}: {adapter.install_help}")
    say("One AI is enough for every role; the reviewer stays independent through a fresh, read-only process.")
    main = choose(ask, say, "Which AI should do the work?", ADAPTERS, found[0] if found else next(iter(ADAPTERS)))
    reviewer = choose(ask, say, "Which AI should review? (optional: a different one)", ADAPTERS, main)
    return main, reviewer


def pick_sandbox(ask, say, probe, system):
    found = [name for name in ENGINES if probe.which(name)]
    extra = " (with Colima)" if probe.which("colima") else ""
    say("Sandbox engines found: " + (", ".join(found) + extra if found else "none"))
    default = found[0] if found else "docker"
    while True:
        name = choose(ask, say, "Which sandbox should run the AI workers and checks?", (*ENGINES, "none"), default)
        if name != "none" or confirm(
                ask, "With none, AI workers and checks run on this machine with your files and network. Use it "
                     "only on a disposable machine. Continue without a sandbox?", False):
            return name


def prepare_engine(ask, say, probe, name, system):
    """Installed, running, image built: True when the sandbox is ready."""
    program = probe.which(name)
    if not program:
        say(f"{name} is not installed.")
        argv, text = install_engine(name, system, probe)
        offer(ask, say, probe, argv, text)
        program = probe.which(name)
        if not program:
            say(f"Install {name}, then run vesper setup again (or vesper doctor to check).")
            return False
    code, _ = probe.run([program, "info"])
    if code != 0:
        say(f"{name} is installed but not running.")
        argv, text = start_engine(name, system, probe)
        offer(ask, say, probe, argv, text)
        code, _ = probe.run([program, "info"])
        if code != 0:
            say(f"Start {name}, then run vesper doctor.")
            return False
    say(f"{name} is running.")
    tag = image_tag()
    code, _ = probe.run([program, "image", "inspect", tag])
    if code == 0:
        say(f"The sandbox image {tag} is ready.")
        return True
    say(f"The sandbox image {tag} is not built yet. It holds Python, Go, Node, browsers and the AI CLIs "
        "(several GB; the first build takes a while).")
    if confirm(ask, "Build it now?", True):
        code = probe.show([program, "build", "-t", tag, str(SANDBOX_DIR)])
        say(f"The image build finished with exit {code}.")
        return code == 0
    say(f"Build it later: vesper sandbox build --backend {name}")
    return False


def sandbox_login(ask, hidden, say, probe, adapter):
    """Make sure the brain can log in inside the sandbox; secrets never reach the config."""
    kind, value = adapter.capabilities.sandbox_login
    if probe.login_ready((kind, value)):
        say(f"{adapter.name}: sandbox login found.")
        return True
    say(f"{adapter.name} needs a login that works inside the sandbox: {adapter.login_help}.")
    if kind == "file":
        answer = ask(f"Press Enter when {probe.login_file(value)} exists, or type skip: ").strip().lower()
        if answer != "skip" and probe.login_ready((kind, value)):
            say(f"{adapter.name}: sandbox login found.")
            return True
        say(f"{adapter.name}: no login yet; vesper doctor will remind you.")
        return False
    secret = hidden(f"Paste {value} (hidden; leave empty to skip): ").strip()
    if not secret:
        say(f"{adapter.name}: skipped; vesper doctor will remind you.")
        return False
    where = "file"
    if probe.keychain():
        where = choose(ask, say, f"Where should {value} be kept?", ("keychain", "file"), "keychain")
    try:
        probe.store(value, secret, where)
    except BuilderError as exc:
        say(f"{adapter.name}: could not store the login: {exc}")
        return False
    say(f"{adapter.name}: {value} stored in " + ("the macOS Keychain." if where == "keychain" else
                                                 "~/.config/vesper/secrets.env (mode 600)."))
    return True


def pick_reserve(ask, say):
    default = DEFAULTS["limits.reserve_percent"]
    while True:
        answer = ask("How much of your AI plan's usage must Vesper always leave for you, in percent? "
                     f"[{default}]: ").strip().rstrip("%")
        if not answer:
            return default
        if answer.isdigit() and 0 <= int(answer) <= 100:
            return int(answer)
        say("Please answer a whole number from 0 to 100.")


def config_text(main, reviewer, backend, reserve, today=None):
    roles = "".join(f'{role} = "{REVIEWER_BRAIN if role == "reviewer" else WORKER_BRAIN}"\n'
                    for role in sorted(PROFILES))
    return (f"# Personal Vesper Relay config, written by `vesper setup` on {(today or date.today()).isoformat()}.\n"
            "# Edit freely; `vesper config show` explains every value. Secrets never go here: they\n"
            "# live in the macOS Keychain or ~/.config/vesper/secrets.env (mode 600).\n\n"
            f'[brains.{WORKER_BRAIN}]\nuse = "{main}"\n\n'
            f'[brains.{REVIEWER_BRAIN}]\nuse = "{reviewer}"\n\n'
            f"[roles]\n{roles}\n"
            f'[sandbox]\nbackend = "{backend}"\n\n'
            f"[limits]\nreserve_percent = {reserve}\n")


def write_config(ask, say, path, text):
    """Write the config after checking it; an existing file is replaced only on a yes, with a backup."""
    if path.exists():
        say(f"A personal config already exists at {path}.")
        if not confirm(ask, f"Replace it? The current file is kept as {path.name}.bak", False):
            say("Kept the existing config.")
            return False
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".config-", suffix=".toml", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            output.write(text)
        os.chmod(temporary, 0o644)
        load_config(Path(temporary), path.parent / ".no-project-file", explicit=True)
        if path.exists():
            backup = path.with_name(path.name + ".bak")
            backup.write_bytes(path.read_bytes())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    say(f"Wrote {path}.")
    return True


def setup(*, ask, say, hidden, probe=None, config=None, call=True):
    """Run the wizard; return the exit status of the closing `vesper doctor` (0 when it passes)."""
    probe = probe or Probe()
    system = probe.system()
    say(f"Vesper Relay setup on {system} ({probe.machine()}).")
    if system not in ("Darwin", "Linux"):
        say("Vesper runs on macOS and Linux; on Windows, run it inside WSL2.")
    main, reviewer = pick_brains(ask, say, probe)
    backend = pick_sandbox(ask, say, probe, system)
    if backend == "none":
        say("No sandbox: each AI uses its own login on this machine.")
    else:
        prepare_engine(ask, say, probe, backend, system)
        for name in dict.fromkeys((main, reviewer)):
            sandbox_login(ask, hidden, say, probe, ADAPTERS[name])
    reserve = pick_reserve(ask, say)
    path, _ = personal_path(config, probe.environ)
    write_config(ask, say, path, config_text(main, reviewer, backend, reserve))
    say("Running vesper doctor...")
    report = doctor(config=path, call=call, probe=probe)
    say(render(report))
    return 0 if report["status"] == "ok" else 1
