"""`vesper setup`, `vesper doctor` and the Python-finding launcher (P1-T11).

Every test runs in a fake environment: a PATH that holds only stand-in programs (container
engine, AI CLIs, Homebrew, uv, Keychain, Python), a private HOME and state directory, and
scripted answers. Nothing touches the real machine's engines, logins or Keychain.
"""
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.brains import ADAPTERS
from builder.doctor import Probe, doctor, host_arch, render, used_flags
from builder.sandbox import image_tag
from builder.team import PROFILES
from builder.wizard import setup

TAG = image_tag()
IMAGE_ID = "sha256:" + "56d7b7cbe179" * 5 + "abcd"  # what the fake engine resolves TAG to; jobs run this ID
HOST = host_arch(platform.machine())
OTHER = "amd64" if HOST == "arm64" else "arm64"


def script(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


class FakeProbe(Probe):
    """The real probe on a fake environment, with the OS and Python version chosen by the test."""

    def __init__(self, environ, system="Linux", python=(3, 12, 1)):
        super().__init__(environ)
        self._system, self._python = system, python

    def system(self):
        return self._system

    def python(self):
        return self._python


class Machine(unittest.TestCase):
    """A fake machine: bin/ is the whole PATH, state/ holds the stand-ins' switches and records."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bin = self.root / "bin"
        self.state = self.root / "fake"
        self.home = self.root / "home"
        for path in (self.bin, self.state, self.home):
            path.mkdir()
        self.env = {"PATH": str(self.bin), "HOME": str(self.home), "VESPER_STATE_DIR": str(self.root / "state"),
                    "LANG": "C.UTF-8"}
        os.symlink(shutil.which("test"), self.bin / "test")  # the image's `test`, for the folder check
        self.config = self.home / ".config" / "vesper" / "config.toml"
        self.secrets = self.home / ".config" / "vesper" / "secrets.env"

    # Stand-ins ---------------------------------------------------------------------------
    def docker(self, running=True, image=True, arch=HOST, name="docker"):
        """A container engine; its `run` executes the command after the image tag from PATH."""
        s = shlex.quote(str(self.state))
        (self.state / "arch").write_text(arch + "\n")
        for flag, on in (("down", not running), ("noimage", not image)):
            marker = self.state / flag
            marker.write_text("") if on else marker.unlink(missing_ok=True)
        return script(self.bin / name, f'''S={s}
echo "$*" >> "$S/{name}-calls"
case "$1" in
  info) [ -e "$S/down" ] && {{ echo "Cannot connect to the Docker daemon" >&2; exit 1; }}; echo aarch64; exit 0;;
  image) [ "$2" = ls ] && {{ [ -e "$S/listed" ] && echo 56d7b7cbe179; exit 0; }}
         [ -e "$S/noimage" ] && {{ echo "Error: No such image: {TAG}" >&2; exit 1; }}
         case "$*" in *"{{{{.Id}}}}"*) echo {IMAGE_ID}; exit 0;; esac; /bin/cat "$S/arch"; exit 0;;
  build) /bin/rm -f "$S/noimage"; exit 0;;
  run) for a in "$@"; do
         case "$a" in
           -d) exit 0;;
           type=bind,source=*,target=/work*) [ -e "$S/noshare" ] || {{ src=${{a#type=bind,source=}}; cd "${{src%%,target=*}}"; }};;
         esac
       done
       while [ $# -gt 0 ] && [ "$1" != "{TAG}" ] && [ "$1" != "{IMAGE_ID}" ]; do shift; done
       [ $# -gt 0 ] || exit 125
       shift; exec "$@";;
  *) exit 0;;
esac
''')

    def cli(self, adapter, drop=(), fails=False):
        """An AI CLI whose --help lists the adapter's flags (minus ``drop``) and that replies OK."""
        name = ADAPTERS[adapter].binary
        flags = [flag for flag in sorted(used_flags(ADAPTERS[adapter])) if flag not in drop]
        help_file = self.state / f"{name}-help"
        help_file.write_text("Usage: " + name + " [options]\n" + "".join(f"  {flag} <value>   option\n"
                                                                         for flag in flags))
        failing = self.state / f"{name}-fails"
        failing.write_text("") if fails else failing.unlink(missing_ok=True)
        return script(self.bin / name, f'''for a in "$@"; do
  [ "$a" = "--help" ] && {{ /bin/cat {shlex.quote(str(help_file))}; exit 0; }}
done
/bin/cat > /dev/null
[ -e {shlex.quote(str(failing))} ] && {{ echo "Invalid API key"; exit 1; }}
echo OK
''')

    def secret_file(self, **values):
        self.secrets.parent.mkdir(parents=True, exist_ok=True)
        self.secrets.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
        self.secrets.chmod(0o600)

    def write_config(self, text):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(text)

    def calls(self, name):
        path = self.state / f"{name}-calls"
        return path.read_text().splitlines() if path.exists() else []


ONE_BRAIN = '[brains.strong]\nuse = "claude-code"\n\n[roles]\nfrontend = "strong"\n\n[sandbox]\nbackend = "docker"\n'


class DoctorTests(Machine):
    def run_doctor(self, system="Linux", python=(3, 12, 1), call=False):
        return doctor(call=call, probe=FakeProbe(self.env, system, python))

    def by_name(self, report):
        return {item["check"]: item for item in report["checks"]}

    def ready(self):
        self.docker()
        self.cli("claude-code")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-test")
        self.write_config(ONE_BRAIN)

    def test_everything_ready_passes(self):
        self.ready()
        report = self.run_doctor()
        self.assertEqual(report["status"], "ok", json.dumps(report, indent=2))
        checks = self.by_name(report)
        for name in ("python", "config", "sandbox engine", "sandbox running", "sandbox image", "sandbox folders",
                     "claude-code cli", "claude-code flags", "claude-code login"):
            self.assertEqual(checks[name]["status"], "ok", name)
        self.assertEqual(checks["brain strong: dry call"]["status"], "skip")
        # The CLI and its flags are checked inside the image, where brains actually run.
        self.assertTrue(any(line.startswith("run ") and "claude --help" in line for line in self.calls("docker")))

    def test_a_missing_flag_is_reported_when_the_cli_help_changes(self):
        self.ready()
        self.cli("claude-code", drop=("--effort",))
        report = self.run_doctor()
        self.assertEqual(report["status"], "failed")
        flags = self.by_name(report)["claude-code flags"]
        self.assertEqual(flags["status"], "fail")
        self.assertIn("--effort", flags["detail"])
        self.assertIn("builder/brains/claude_code.py", flags["fix"])

    def test_every_adapter_flag_list_is_checked(self):
        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter):
                flags = used_flags(ADAPTERS[adapter])
                self.assertTrue(flags and all(flag.startswith("-") for flag in flags), flags)
                self.assertTrue(set(ADAPTERS[adapter].hidden_flags).isdisjoint(flags))
        self.assertIn("--max-turns", ADAPTERS["claude-code"].hidden_flags)
        self.assertIn("--skip-git-repo-check", used_flags(ADAPTERS["codex"]))
        self.assertIn("--json", used_flags(ADAPTERS["codex"]))  # P2-T10: the event stream
        self.assertIn("--approval-mode", used_flags(ADAPTERS["gemini-cli"]))

    def test_old_python_fails_with_a_fix(self):
        self.ready()
        check = self.by_name(self.run_doctor(python=(3, 10, 4)))["python"]
        self.assertEqual(check["status"], "fail")
        self.assertIn("3.10.4", check["detail"])
        self.assertIn("python@3.12", check["fix"])

    def test_invalid_config_fails_and_the_rest_uses_defaults(self):
        self.docker()
        self.write_config("[sandbox\n")
        checks = self.by_name(self.run_doctor())
        self.assertEqual(checks["config"]["status"], "fail")
        self.assertIn("vesper setup", checks["config"]["fix"])
        self.assertEqual(checks["sandbox engine"]["status"], "ok")  # default backend: docker

    def test_missing_engine_offers_the_install_command(self):
        self.write_config(ONE_BRAIN)
        self.cli("claude-code")
        for system, fix in (("Darwin", "brew install colima docker"), ("Linux", "docs.docker.com")):
            with self.subTest(system=system):
                checks = self.by_name(self.run_doctor(system=system))
                self.assertEqual(checks["sandbox engine"]["status"], "fail")
                self.assertIn(fix, checks["sandbox engine"]["fix"])
                # Brain checks that need the sandbox are skipped, not failed twice.
                self.assertEqual(checks["claude-code cli"]["status"], "skip")

    def test_stopped_engine_names_the_start_command(self):
        self.ready()
        self.docker(running=False)
        script(self.bin / "colima", "exit 0\n")
        checks = self.by_name(self.run_doctor(system="Darwin"))
        self.assertEqual(checks["sandbox running"]["status"], "fail")
        self.assertIn("colima start", checks["sandbox running"]["fix"])
        self.assertEqual(checks["sandbox image"]["status"], "skip")

    def test_missing_image_names_the_build_command(self):
        self.ready()
        self.docker(image=False)
        check = self.by_name(self.run_doctor())["sandbox image"]
        self.assertEqual(check["status"], "fail")
        self.assertIn("vesper sandbox build --backend docker", check["fix"])

    def test_a_listed_image_that_cannot_be_inspected_is_told_apart(self):
        self.ready()
        self.docker(image=False)
        (self.state / "listed").write_text("")
        check = self.by_name(self.run_doctor())["sandbox image"]
        self.assertEqual(check["status"], "fail")
        self.assertIn("cannot inspect", check["detail"])
        self.assertIn("again in a minute", check["fix"])

    def test_a_state_folder_the_engine_cannot_see_fails(self):
        self.ready()
        (self.state / "noshare").write_text("")
        checks = self.by_name(self.run_doctor())
        self.assertEqual(checks["sandbox folders"]["status"], "fail")
        self.assertIn(str(self.root / "state"), checks["sandbox folders"]["detail"])
        self.assertIn("Colima shares only your home folder", checks["sandbox folders"]["fix"])
        self.assertEqual(checks["claude-code cli"]["status"], "skip")

    def test_wrong_image_architecture_fails(self):
        self.ready()
        self.docker(arch=OTHER)
        check = self.by_name(self.run_doctor())["sandbox image"]
        self.assertEqual(check["status"], "fail")
        self.assertIn(OTHER, check["detail"])
        self.assertIn(f"--platform linux/{HOST}", check["fix"])

    def test_missing_cli_in_the_image_names_the_rebuild(self):
        self.ready()
        (self.bin / "claude").unlink()
        check = self.by_name(self.run_doctor())["claude-code cli"]
        self.assertEqual(check["status"], "fail")
        self.assertIn("vesper sandbox build", check["fix"])

    def test_missing_sandbox_login_names_the_login_step(self):
        self.ready()
        self.secrets.unlink()
        checks = self.by_name(self.run_doctor())
        self.assertEqual(checks["claude-code login"]["status"], "fail")
        self.assertIn("claude setup-token", checks["claude-code login"]["fix"])
        self.assertEqual(checks["brain strong: dry call"]["status"], "skip")

    def test_file_login_is_checked_for_codex(self):
        self.docker()
        self.cli("codex")
        self.write_config('[brains.reviewer]\nuse = "codex"\n')
        check = self.by_name(self.run_doctor())["codex login"]
        self.assertEqual(check["status"], "fail")
        self.assertIn("codex login", check["fix"])
        auth = self.home / ".codex" / "auth.json"
        auth.parent.mkdir()
        auth.write_text("{}")
        self.assertEqual(self.by_name(self.run_doctor())["codex login"]["status"], "ok")

    def test_codex_json_is_checked_against_codex_exec_help_in_the_image(self):
        # P2-T10: every Codex command now carries --json; a codex whose `exec --help` lacks it fails.
        self.docker()
        self.write_config('[brains.reviewer]\nuse = "codex"\n')
        self.cli("codex")
        self.assertEqual(self.by_name(self.run_doctor())["codex flags"]["status"], "ok")
        self.assertTrue(any(line.startswith("run ") and "codex exec --help" in line for line in self.calls("docker")))
        self.cli("codex", drop=("--json",))
        flags = self.by_name(self.run_doctor())["codex flags"]
        self.assertEqual(flags["status"], "fail")
        self.assertIn("--json", flags["detail"])

    def test_no_brains_is_a_warning(self):
        self.docker()
        report = self.run_doctor()
        self.assertEqual(report["status"], "ok")
        self.assertEqual(self.by_name(report)["brains"]["status"], "warn")
        self.assertIn("vesper setup", self.by_name(report)["brains"]["fix"])

    def test_no_sandbox_warns_and_checks_the_host_cli(self):
        self.cli("gemini-cli")
        self.write_config('[brains.g]\nuse = "gemini-cli"\n\n[sandbox]\nbackend = "none"\n')
        checks = self.by_name(self.run_doctor())
        self.assertEqual(checks["sandbox"]["status"], "warn")
        self.assertEqual(checks["gemini-cli cli"]["status"], "ok")
        self.assertEqual(checks["gemini-cli flags"]["status"], "ok")
        self.assertEqual(checks["gemini-cli login"]["status"], "skip")
        self.assertNotIn("sandbox engine", checks)

    def test_each_distinct_brain_gets_one_dry_call(self):
        self.ready()
        self.write_config('[brains.strong]\nuse = "claude-code"\nmodel = "opus"\n\n[brains.reviewer]\n'
                          'use = "claude-code"\nmodel = "opus"\n\n[brains.fast]\nuse = "claude-code"\n'
                          'model = "sonnet"\n')
        names = [item["check"] for item in self.run_doctor()["checks"] if "dry call" in item["check"]]
        self.assertEqual(names, ["brain fast: dry call", "brain reviewer: dry call"])

    def test_render_prints_a_fix_for_each_failure(self):
        self.ready()
        self.secrets.unlink()
        text = render(self.run_doctor())
        self.assertIn("FAIL", text)
        self.assertIn("fix: ", text)
        self.assertIn("claude setup-token", text)


class DoctorCommandTests(Machine):
    """`vesper doctor` end to end: the real dry call goes through the sandbox backend."""

    def vesper(self, *args, code=None, stdin=""):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), *args], env=self.env,
                                cwd=self.root, input=stdin, capture_output=True, text=True, timeout=120)
        if code is not None:
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_doctor_makes_a_tiny_dry_call_in_the_sandbox(self):
        self.docker()
        self.cli("claude-code")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-test")
        self.write_config(ONE_BRAIN)
        report = json.loads(self.vesper("doctor", "--json", code=0).stdout)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["brain strong: dry call"]["status"], "ok", checks)
        self.cli("claude-code", fails=True)
        result = self.vesper("doctor", code=1)
        self.assertIn("dry call", result.stdout)
        self.assertIn("Invalid API key", result.stdout)
        self.assertIn("fix: ", result.stdout)
        no_call = json.loads(self.vesper("doctor", "--json", "--no-call", code=0).stdout)
        self.assertEqual({item["check"]: item for item in no_call["checks"]}["brain strong: dry call"]["status"],
                         "skip")

    def test_setup_command_reads_answers_and_writes_the_config(self):
        self.docker()
        self.cli("claude-code")
        answers = "\n".join(["claude-code", "", "docker", "sk-pasted", "", ""]) + "\n"
        result = self.vesper("setup", "--no-call", stdin=answers, code=0)
        self.assertIn("vesper doctor", result.stdout)
        values = tomllib.loads(self.config.read_text())
        self.assertEqual(values["brains"]["strong"]["use"], "claude-code")
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN=sk-pasted", self.secrets.read_text())
        self.assertNotIn("sk-pasted", result.stdout + result.stderr)

    def test_setup_without_answers_stops_cleanly(self):
        result = self.vesper("setup", stdin="", code=2)
        self.assertIn("answers", result.stderr)
        self.assertFalse(self.config.exists())


class WizardTests(Machine):
    def wizard(self, *answers, system="Linux"):
        queue, self.prompts, self.said = list(answers), [], []

        def ask(prompt):
            self.prompts.append(prompt)
            self.assertTrue(queue, "the wizard asked more than the test answered: " + prompt)
            return queue.pop(0)

        code = setup(probe=FakeProbe(self.env, system), ask=ask, say=self.said.append, hidden=ask, call=False)
        self.assertEqual(queue, [], "unused answers; prompts were:\n" + "\n".join(self.prompts))
        return code

    def output(self):
        return "\n".join(self.said)

    def values(self):
        return tomllib.loads(self.config.read_text())

    def test_one_ai_for_every_role(self):
        self.docker()
        self.cli("claude-code")
        code = self.wizard("", "", "", "sk-pasted", "30")
        self.assertEqual(code, 0, self.output())
        values = self.values()
        self.assertEqual(values["brains"], {"strong": {"use": "claude-code"}, "reviewer": {"use": "claude-code"}})
        self.assertEqual(set(values["roles"]), set(PROFILES))
        self.assertEqual(values["roles"]["reviewer"], "reviewer")
        self.assertEqual({brain for role, brain in values["roles"].items() if role != "reviewer"}, {"strong"})
        self.assertEqual(values["sandbox"]["backend"], "docker")
        self.assertEqual(values["limits"]["reserve_percent"], 30)
        self.assertEqual(stat.S_IMODE(self.secrets.stat().st_mode), 0o600)
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN=sk-pasted", self.secrets.read_text())
        self.assertNotIn("sk-pasted", self.config.read_text() + self.output())
        self.assertIn("Linux", self.output())
        self.assertIn("claude-code", self.output())  # detected CLIs are listed

    def test_a_different_reviewer_and_a_skipped_file_login(self):
        self.docker()
        self.cli("claude-code")
        self.cli("codex")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-old")
        code = self.wizard("claude-code", "codex", "docker", "skip", "")
        self.assertEqual(code, 1)  # doctor: codex has no login yet
        self.assertEqual(self.values()["brains"]["reviewer"], {"use": "codex"})
        self.assertIn("codex login", self.output())
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN=sk-old", self.secrets.read_text())

    def test_a_file_login_found_after_the_user_logs_in(self):
        self.docker()
        self.cli("codex")
        auth = self.home / ".codex" / "auth.json"
        auth.parent.mkdir()

        def ask_and_login(*_):
            auth.write_text("{}")
            return ""
        queue = ["codex", "", "docker"]
        prompts = []

        def ask(prompt):
            prompts.append(prompt)
            if "Enter" in prompt:
                return ask_and_login()
            return queue.pop(0) if queue else ""
        code = setup(probe=FakeProbe(self.env), ask=ask, say=lambda _: None, hidden=ask, call=False)
        self.assertEqual(code, 0)
        self.assertTrue(any("Enter" in prompt for prompt in prompts), prompts)

    def test_invalid_answers_are_asked_again(self):
        self.docker()
        self.cli("claude-code")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-old")
        code = self.wizard("chatbot", "1", "", "kubernetes", "docker", "150", "lots", "")
        self.assertEqual(code, 0, self.output())
        # Choices may be numbers from the listed order.
        self.assertEqual(self.values()["brains"]["strong"]["use"], list(ADAPTERS)[0])
        self.assertEqual(self.values()["limits"]["reserve_percent"], 25)

    def test_no_ai_found_lists_how_to_install_each(self):
        self.docker()
        self.wizard("", "", "", "", "")
        for adapter in ADAPTERS.values():
            self.assertIn(adapter.install_help, self.output())

    def test_missing_engine_on_a_mac_offers_homebrew(self):
        self.cli("claude-code")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-old")
        record, fake_docker = shlex.quote(str(self.state / "brew-calls")), self.state / "docker-ready"
        engine = self.docker()
        shutil.move(engine, fake_docker)
        script(self.bin / "brew", f'echo "$*" >> {record}\n/bin/cp {shlex.quote(str(fake_docker))} '
                                  f'{shlex.quote(str(self.bin / "docker"))}\n')
        code = self.wizard("", "", "", "y", "", system="Darwin")
        self.assertEqual(code, 0, self.output())
        self.assertEqual((self.state / "brew-calls").read_text().split(), ["install", "colima", "docker"])

    def test_missing_engine_on_linux_prints_instructions_only(self):
        self.cli("claude-code")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-old")
        code = self.wizard("", "", "", "", system="Linux")
        self.assertEqual(code, 1)
        self.assertIn("docs.docker.com", self.output())
        self.assertFalse(any("Run" in prompt for prompt in self.prompts), self.prompts)

    def test_stopped_engine_offers_colima_start(self):
        self.cli("claude-code")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-old")
        self.docker(running=False)
        down = shlex.quote(str(self.state / "down"))
        script(self.bin / "colima", f'echo "$*" > {shlex.quote(str(self.state / "colima-calls"))}\n'
                                   f'/bin/rm -f {down}\n')
        code = self.wizard("", "", "", "y", "", system="Darwin")
        self.assertEqual(code, 0, self.output())
        self.assertEqual(self.calls("colima"), ["start"])

    def test_missing_image_is_built_on_request(self):
        self.cli("claude-code")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-old")
        self.docker(image=False)
        code = self.wizard("", "", "", "", "")
        self.assertEqual(code, 0, self.output())
        built = [line for line in self.calls("docker") if line.startswith("build")]
        self.assertEqual(len(built), 1)
        self.assertIn(f"-t {TAG}", built[0])
        self.assertTrue(built[0].endswith(str(ROOT / "sandbox")))

    def test_declining_the_image_build_leaves_doctor_failing(self):
        self.cli("claude-code")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-old")
        self.docker(image=False)
        self.assertEqual(self.wizard("", "", "", "n", ""), 1)
        self.assertIn("vesper sandbox build", self.output())

    def test_no_sandbox_needs_confirmation_and_asks_no_logins(self):
        self.cli("claude-code")
        code = self.wizard("", "", "none", "n", "none", "y", "")
        self.assertEqual(code, 0, self.output())
        self.assertEqual(self.values()["sandbox"]["backend"], "none")
        self.assertFalse(self.secrets.exists())
        self.assertIn("disposable", "\n".join(self.prompts))

    def test_existing_config_is_kept_unless_replaced(self):
        self.docker()
        self.cli("claude-code")
        self.secret_file(CLAUDE_CODE_OAUTH_TOKEN="sk-old")
        self.write_config(ONE_BRAIN)
        self.wizard("", "", "", "", "n")
        self.assertEqual(self.config.read_text(), ONE_BRAIN)
        self.wizard("", "", "", "", "y")
        self.assertEqual(self.config.with_name("config.toml.bak").read_text(), ONE_BRAIN)
        self.assertIn("reviewer", self.values()["brains"])

    @unittest.skipUnless(sys.platform == "darwin", "the Keychain exists only on macOS")
    def test_mac_token_goes_to_the_keychain_through_stdin(self):
        self.docker()
        self.cli("claude-code")
        store = shlex.quote(str(self.state / "keychain"))
        # `security -i` reads one command line on stdin; find-generic-password prints the value.
        script(self.bin / "security", f'''case "$1" in
  -i) read line; echo "$line" > {store}; echo "-i $*" >> {shlex.quote(str(self.state / "security-calls"))};;
  find-generic-password) [ -e {store} ] || exit 44; set -- $(/bin/cat {store}); while [ "$1" != "-w" ]; do shift; done; echo "$2";;
esac
''')
        code = self.wizard("", "", "", "sk-mac.Token_1", "", "", system="Darwin")
        self.assertEqual(code, 0, self.output())
        stored = (self.state / "keychain").read_text()
        self.assertIn("add-generic-password -U -s vesper-relay -a CLAUDE_CODE_OAUTH_TOKEN -w sk-mac.Token_1",
                      stored)
        self.assertFalse(any("sk-mac" in line for line in self.calls("security")))  # never on a command line
        self.assertFalse(self.secrets.exists())

    def test_secrets_file_store_replaces_one_line_and_stays_private(self):
        from builder.sandbox import secrets
        self.secret_file(OTHER_LOGIN="x", CLAUDE_CODE_OAUTH_TOKEN="old")
        self.secrets.chmod(0o600)
        secrets.store("CLAUDE_CODE_OAUTH_TOKEN", "new", "file", environ=self.env)
        self.assertEqual(self.secrets.read_text(), "OTHER_LOGIN=x\nCLAUDE_CODE_OAUTH_TOKEN=new\n")
        self.assertEqual(stat.S_IMODE(self.secrets.stat().st_mode), 0o600)
        with self.assertRaises(Exception):
            secrets.store("CLAUDE_CODE_OAUTH_TOKEN", "two\nlines", "file", environ=self.env)


class LauncherTests(Machine):
    """bin/vesper finds a Python 3.11+ itself, so nobody needs a virtual environment."""

    def setUp(self):
        super().setUp()
        self.env["VESPER_PYTHON_DIRS"] = ""  # no Homebrew fallbacks from the real machine

    def python(self, name, supported=True):
        record = shlex.quote(str(self.state / f"{name}-ran"))
        return script(self.bin / name, f'case "$1" in -c) exit {0 if supported else 1};; esac\n'
                                       f'echo "$*" > {record}\n')

    def launch(self, *args, stdin=""):
        return subprocess.run(["/bin/sh", str(ROOT / "bin" / "vesper"), *args], env=self.env, input=stdin,
                              capture_output=True, text=True, timeout=60)

    def test_picks_the_first_supported_python(self):
        self.python("python3", supported=False)
        self.python("python3.12")
        result = self.launch("root")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / "python3.12-ran").read_text().split(), ["-B", str(ROOT / "vesper.py"), "root"])
        self.assertFalse((self.state / "python3-ran").exists())

    def test_the_recorded_python_comes_first(self):
        self.python("python3.12")
        chosen = self.python("chosen-python")
        self.env["VESPER_PYTHON"] = str(chosen)
        self.assertEqual(self.launch("root").returncode, 0)
        self.assertTrue((self.state / "chosen-python-ran").exists())
        self.assertFalse((self.state / "python3.12-ran").exists())

    def test_uv_managed_python_is_found(self):
        found = self.python("uv-python")
        found.rename(self.state / "uv-python")
        script(self.bin / "uv", f'[ "$1 $2" = "python find" ] && echo {shlex.quote(str(self.state / "uv-python"))}\n')
        self.assertEqual(self.launch("root").returncode, 0)
        self.assertTrue((self.state / "uv-python-ran").exists())

    def test_without_python_every_command_names_the_fix(self):
        self.python("python3", supported=False)
        result = self.launch("doctor")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Python 3.11", result.stderr)
        self.assertIn("vesper setup", result.stderr)

    def test_setup_offers_to_install_python(self):
        record = shlex.quote(str(self.state / "uv-calls"))
        good = self.python("installed-python")
        good.rename(self.state / "installed-python")
        installed = shlex.quote(str(self.state / "installed"))
        script(self.bin / "uv", f'''echo "$*" >> {record}
case "$1 $2" in
  "python install") : > {installed};;
  "python find") [ -e {installed} ] && echo {shlex.quote(str(self.state / "installed-python"))} || exit 2;;
esac
''')
        declined = self.launch("setup", stdin="n\n")
        self.assertEqual(declined.returncode, 2)
        self.assertNotIn("python install 3.12", (self.state / "uv-calls").read_text())
        accepted = self.launch("setup", stdin="y\n")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("python install 3.12", (self.state / "uv-calls").read_text())
        self.assertEqual((self.state / "installed-python-ran").read_text().split(),
                         ["-B", str(ROOT / "vesper.py"), "setup"])

    def test_installed_command_runs_the_launcher(self):
        env = dict(os.environ, HOME=str(self.home), VESPER_STATE_DIR=str(self.root / "state"))
        result = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "install", "--for", "codex"],
                                env=env, capture_output=True, text=True, check=True)
        shim = Path(json.loads(result.stdout)["command"])
        text = shim.read_text()
        self.assertIn(str(ROOT / "bin" / "vesper"), text)
        self.assertIn("VESPER_PYTHON", text)
        root = subprocess.run([str(shim), "root"], env=env, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(root.stdout)["checkout"], str(ROOT))


if __name__ == "__main__":
    unittest.main()
