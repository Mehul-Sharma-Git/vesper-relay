"""Pluggable sandbox: backends, jobs, logins and the runner's use of them (P1-T9).

These tests need no container engine: they check the arguments each backend builds and
drive the runner through a fake backend. SandboxSelftest runs the real selftest only when
Docker and the built image are present.
"""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.brains import ADAPTERS, Brain, job as brain_job
from builder.contracts import BuilderError
from builder.runner import Runner
from builder.sandbox import (Docker, Job, Podman, Sandbox, agent_job, backend, check_job, command_job, image_tag,
                             secrets)

import test_rc1
from test_rc1 import verdict


ID = "f" * 64  # an engine's full image ID (Docker adds "sha256:", Podman does not)


def value_after(argv, flag):
    return [argv[index + 1] for index, item in enumerate(argv) if item == flag]


class ArgumentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.work = self.root / "work"
        self.work.mkdir()

    def build(self, engine, job, network="none"):
        return engine.run_argv(job, "vesper-test", network)

    def test_every_operation_is_hardened(self):
        jobs = {
            "worker": brain_job(Brain("codex", ADAPTERS["codex"]), "worker", self.work),
            "reviewer": brain_job(Brain("codex", ADAPTERS["codex"]), "reviewer", self.work, out=self.root),
            "consult": brain_job(Brain("gemini-cli", ADAPTERS["gemini-cli"]), "consult", self.work),
            "setup": command_job("setup", ["pnpm", "install"], self.work, dependencies=self.root),
            "check": check_job(self.work, "gate.py"),
            "check-command": command_job("check-command", ["go", "test"], self.work, dependencies=self.root),
        }
        for engine in (Docker(), Podman()):
            for operation, job in jobs.items():
                with self.subTest(engine=engine.name, operation=operation):
                    argv = self.build(engine, job)
                    self.assertEqual(argv[:2], [engine.program, "run"])
                    for flag in ("--rm", "-i", "--read-only", "--init"):
                        self.assertIn(flag, argv)
                    self.assertEqual(value_after(argv, "--cap-drop"), ["ALL"])
                    self.assertIn("no-new-privileges", value_after(argv, "--security-opt"))
                    user = value_after(argv, "--user")[0]
                    self.assertNotEqual(user.split(":")[0], "0")
                    self.assertTrue(value_after(argv, "--memory") and value_after(argv, "--pids-limit"))
                    self.assertIn(image_tag(), argv)
                    mounts = " ".join(value_after(argv, "--mount"))
                    self.assertNotIn(f"source={Path.home()},", mounts)
                    self.assertNotIn("docker.sock", " ".join(argv))
                    self.assertNotIn("-v", argv)
                    self.assertEqual(argv[argv.index(image_tag()) + 1:], list(job.argv))
                    if engine.name == "podman":
                        self.assertIn("--userns=keep-id", argv)

    def fake_engine(self, script, name="docker"):
        bin_dir = self.root / "engine-bin"
        bin_dir.mkdir(exist_ok=True)
        fake = bin_dir / name
        fake.write_text("#!/bin/sh\n" + script)
        fake.chmod(0o700)
        return mock.patch.dict(os.environ, {"PATH": str(bin_dir)})

    def test_jobs_run_the_image_id_the_check_resolved(self):
        with self.fake_engine(f'case "$*" in *"inspect"*) echo sha256:{ID};; *) exit 1;; esac\n'):
            engine = Docker().check()
        job = check_job(self.work, "gate.py")
        argv = self.build(engine, job)
        self.assertNotIn(image_tag(), argv)
        self.assertEqual(argv[argv.index(f"sha256:{ID}") + 1:], list(job.argv))
        for answer in ("", "sha256:feed", "--privileged"):
            with self.subTest(answer=answer), self.fake_engine(f'echo "{answer}"\n'), \
                    self.assertRaisesRegex(BuilderError, "gave no image ID"):
                Docker().check()

    def test_podman_ids_have_no_prefix_and_a_missing_image_is_not_known(self):
        # Podman prints the bare 64-hex storage ID and says "image not known" for a missing one.
        with self.fake_engine(f'case "$*" in *"inspect"*) echo {ID};; *) exit 1;; esac\n', "podman"):
            engine = Podman().check()
        self.assertEqual(engine.image_id, ID)
        self.assertIn(ID, self.build(engine, check_job(self.work, "gate.py")))
        missing = 'echo "Error: vesper-sandbox: image not known" >&2; exit 125\n'
        with self.fake_engine(missing, "podman"), self.assertRaisesRegex(BuilderError, "vesper sandbox build"):
            Podman().check()

    def test_a_listed_image_that_inspect_misses_is_used_by_id(self):
        # Docker Desktop 29.2 (containerd image store) at times answers "No such image" to
        # `image inspect <tag>` while `image ls` lists the tag; inspect by ID still works.
        script = ('case "$*" in\n'
                  f'  *"inspect"*"sha256:{ID}"*) echo sha256:{ID};;\n'
                  '  *"inspect"*) echo "Error response from daemon: No such image: x" >&2; exit 1;;\n'
                  f'  *"image ls -q --no-trunc"*) echo sha256:{ID};;\n'
                  '  *) exit 1;;\nesac\n')
        with self.fake_engine(script):
            engine = Docker().check()
        self.assertIn(f"sha256:{ID}", self.build(engine, check_job(self.work, "gate.py")))
        missing = script.replace(f'  *"image ls -q --no-trunc"*) echo sha256:{ID};;\n', "")
        with self.fake_engine(missing), self.assertRaisesRegex(BuilderError, "vesper sandbox build"):
            Docker().check()

    def test_image_has_python_playwright_and_its_chromium(self):
        # Gates are Python scripts (python3 -I in the image), so the image carries Python
        # Playwright at the Node version, with the Chromium build that package expects.
        text = (ROOT / "sandbox" / "Dockerfile").read_text()
        self.assertIn('"playwright==${PLAYWRIGHT_VERSION}"', text)
        self.assertIn("python3 -m playwright install chromium", text)
        self.assertRegex(text, r'"greenlet==\$\{GREENLET_VERSION\}"')
        self.assertRegex(text, r"ARG GREENLET_VERSION=\d+\.\d+\.\d+")

    def test_mounts_and_networks_follow_the_operation_table(self):
        docker = Docker()
        worker = brain_job(Brain("claude-code", ADAPTERS["claude-code"]), "worker", self.work)
        self.assertEqual(worker.network, "egress")
        self.assertIn(f"type=bind,source={self.work},target=/work", value_after(self.build(docker, worker), "--mount"))
        self.assertEqual(value_after(self.build(docker, worker, "vesper-egress-1"), "--network"), ["vesper-egress-1"])
        reviewer = brain_job(Brain("codex", ADAPTERS["codex"]), "reviewer", self.work, out=self.root / "out")
        mounts = value_after(self.build(docker, reviewer), "--mount")
        self.assertIn(f"type=bind,source={self.work},target=/work,readonly", mounts)
        self.assertIn(f"type=bind,source={self.root / 'out'},target=/out", mounts)
        self.assertEqual(reviewer.argv[reviewer.argv.index("--output-last-message") + 1], "/out/response.json")
        check = check_job(self.work, "gate.py")
        self.assertEqual((check.network, check.work_readonly), ("none", True))
        self.assertEqual(check.argv, ("python3", "-I", "-B", "/work/checks/gate.py", "/work/candidate"))
        self.assertEqual(value_after(self.build(docker, check), "--network"), ["none"])
        setup = command_job("setup", ["pnpm", "install"], self.work, dependencies=self.root / "cache")
        self.assertEqual(setup.network, "open")
        self.assertIn(f"type=bind,source={self.root / 'cache'},target=/cache", value_after(self.build(docker, setup), "--mount"))
        gate = command_job("check-command", ["pnpm", "test"], self.work, dependencies=self.root / "cache")
        self.assertEqual(gate.network, "none")
        self.assertIn(f"type=bind,source={self.root / 'cache'},target=/cache,readonly",
                      value_after(self.build(docker, gate), "--mount"))
        self.assertEqual(dict(gate.env)["PNPM_STORE_DIR"], "/cache/pnpm-store")
        self.assertEqual(value_after(self.build(docker, setup, "bridge"), "--network"), ["bridge"])

    def test_paths_that_break_mount_syntax_are_refused(self):
        odd = self.root / "a,b"
        odd.mkdir()
        with self.assertRaisesRegex(BuilderError, "comma"):
            self.build(Docker(), check_job(odd, "gate.py"))

    def test_logins_pass_by_name_never_by_value(self):
        claude = brain_job(Brain("claude-code", ADAPTERS["claude-code"]), "worker", self.work)
        self.assertEqual(claude.secrets, ("CLAUDE_CODE_OAUTH_TOKEN",))
        argv = self.build(Docker(), claude)
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN", value_after(argv, "-e"))
        codex = brain_job(Brain("codex", ADAPTERS["codex"]), "worker", self.work)
        self.assertEqual(codex.secrets, ())
        login = Path("~/.codex/auth.json").expanduser()
        self.assertIn(f"type=bind,source={login},target=/run/vesper-login/auth.json,readonly",
                      value_after(self.build(Docker(), codex), "--mount"))
        # The read-only login is copied into the private home before the CLI starts.
        self.assertEqual(codex.argv[:2], ("sh", "-c"))
        self.assertEqual(codex.argv[3:6], ("vesper-login", ".codex/auth.json", "/run/vesper-login/auth.json"))
        self.assertEqual(codex.argv[6:8], ("codex", "exec"))
        store = self.root / "secrets.env"
        store.write_text("CLAUDE_CODE_OAUTH_TOKEN=sk-test-value\n")
        store.chmod(0o600)
        with mock.patch.object(secrets, "keychain", return_value=None):
            env = Docker().cli_environment(claude, {"PATH": "/bin", "HOME": "/h", "OTHER": "x"}, store)
        self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "sk-test-value")
        self.assertNotIn("OTHER", env)
        self.assertNotIn("sk-test-value", " ".join(argv))

    def test_brain_model_and_effort_reach_the_sandbox(self):
        job = brain_job(Brain("claude-code", ADAPTERS["claude-code"], "opus", "high"), "reviewer", self.work,
                        out=self.root, schema={"type": "object"}, max_turns=9)
        self.assertEqual(job.argv[0], "claude")
        self.assertEqual(value_after(list(job.argv), "--model"), ["opus"])
        self.assertEqual(value_after(list(job.argv), "--effort"), ["high"])
        self.assertEqual(value_after(list(job.argv), "--max-turns"), ["9"])
        self.assertIn("--json-schema", job.argv)
        self.assertTrue(job.hosts)

    def test_every_adapter_declares_its_provider_hosts(self):
        for name, adapter in ADAPTERS.items():
            with self.subTest(adapter=name):
                self.assertTrue(adapter.sandbox_hosts)
                self.assertTrue(all("." in host and "/" not in host for host in adapter.sandbox_hosts))

    def test_proxy_allows_only_the_brain_hosts(self):
        config, filters = Docker().proxy_files(("api.anthropic.com", "chatgpt.com"))
        self.assertIn("FilterDefaultDeny Yes", config)
        self.assertIn("ConnectPort 443", config)
        self.assertEqual(filters.splitlines(), [r"^api\.anthropic\.com$", r"^chatgpt\.com$"])

    def test_the_proxy_log_is_kept_beside_the_job_log(self):
        # P1-G run 2: a worker died on ERR_PROXY_TUNNEL and the proxy's log went with its container.
        calls = self.root / "calls"
        script = (f'echo "$*" >> {calls}\n'
                  'case "$*" in\n'
                  '  logs*) echo "NOTICE: Proxying refused on filtered domain \\"statsig.anthropic.com\\"";;\n'
                  '  "run -d"*) echo proxy-id;;\n'
                  '  run*) echo "API Error: ERR_PROXY_TUNNEL"; exit 1;;\n'
                  'esac\n')
        job = agent_job("worker", ("claude", "-p"), self.work, hosts=("api.anthropic.com",))
        log = self.root / "worker.log"
        with self.fake_engine(script):
            code = Docker().run(job, input_text="", log=log, timeout=30)
        self.assertEqual(code, 1)
        kept = self.root / "worker.proxy.log"
        self.assertIn('refused on filtered domain "statsig.anthropic.com"', kept.read_text())
        commands = calls.read_text().splitlines()
        logs = next(i for i, line in enumerate(commands) if line.startswith("logs vesper-"))
        removed = next(i for i, line in enumerate(commands) if line.startswith("rm -f vesper-") and "-proxy" in line)
        self.assertLess(logs, removed)  # read before the container is gone

        # A proxy log that can't be read never changes the job's result.
        failing = script.replace('  logs*) echo', '  logs*) exit 1; echo')
        kept.unlink()
        with self.fake_engine(failing):
            self.assertEqual(Docker().run(job, input_text="", log=log, timeout=30), 1)
        self.assertFalse(kept.exists())

    def test_a_proxy_log_that_is_not_utf8_never_stops_the_cleanup(self):
        # A sandboxed worker can put raw bytes in the proxy's log (it logs refused host names).
        calls = self.root / "calls"
        script = (f'echo "$*" >> {calls}\n'
                  'case "$*" in\n'
                  '  logs*) printf \'NOTICE: Proxying refused on filtered domain "\\377\\376evil"\\n\';;\n'
                  '  "run -d"*) echo proxy-id;;\n'
                  '  run*) exit 0;;\n'
                  'esac\n')
        job = agent_job("worker", ("claude", "-p"), self.work, hosts=("api.anthropic.com",))
        log = self.root / "worker.log"
        with self.fake_engine(script):
            self.assertEqual(Docker().run(job, input_text="", log=log, timeout=30), 0)
        commands = calls.read_text().splitlines()
        self.assertTrue(any(line.startswith("rm -f vesper-") and line.endswith("-proxy") for line in commands))
        self.assertTrue(any(line.startswith("network rm vesper-") for line in commands))
        self.assertEqual(list(self.root.glob("vesper-proxy-*")), [])
        self.assertIn("\ufffd\ufffdevil", (self.root / "worker.proxy.log").read_text(encoding="utf-8"))

    def test_jobs_without_a_proxy_keep_no_proxy_log(self):
        log = self.root / "gate.log"
        with self.fake_engine("exit 0\n"):
            self.assertEqual(Docker().run(check_job(self.work, "gate.py"), input_text="", log=log, timeout=30), 0)
        self.assertFalse((self.root / "gate.proxy.log").exists())


class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Path(temp.name) / "secrets.env"

    def test_secrets_file_must_be_private(self):
        self.store.write_text("# comment\nGEMINI_API_KEY = 'abc'\n")
        self.store.chmod(0o644)
        with mock.patch.object(secrets, "keychain", return_value=None):
            with self.assertRaisesRegex(BuilderError, "mode 600"):
                secrets.read("GEMINI_API_KEY", self.store)
            self.store.chmod(0o600)
            self.assertEqual(secrets.read("GEMINI_API_KEY", self.store), "abc")
            self.assertIsNone(secrets.read("OPENAI_API_KEY", self.store))

    def test_keychain_comes_first(self):
        self.store.write_text("GEMINI_API_KEY=file\n")
        self.store.chmod(0o600)
        with mock.patch.object(secrets, "keychain", return_value="chain"):
            self.assertEqual(secrets.read("GEMINI_API_KEY", self.store), "chain")

    def test_missing_login_names_the_fix(self):
        with mock.patch.object(secrets, "keychain", return_value=None):
            with self.assertRaisesRegex(BuilderError, "claude setup-token"):
                Docker().cli_environment(brain_job(Brain("claude-code", ADAPTERS["claude-code"]), "worker",
                                                   Path("/tmp")), {"PATH": "/bin"}, self.store)


class FakeSandbox(Sandbox):
    """Runs jobs on the host with /work mapped to the job's work directory."""
    name = "fake"

    def __init__(self):
        self.jobs = []

    def check(self):
        return self

    def run(self, job, *, input_text, log, timeout, on_start=None):
        self.jobs.append(job)
        if job.operation == "worker":
            (job.work / "app.js").write_text("export const loading = false;\n")
            return 0
        if job.operation == "reviewer":
            packet = json.loads((job.work / "review.json").read_text())
            out = next(source for source, target, _ in job.mounts if target == "/out")
            report = {key: packet[key] for key in ("attempt_id", "base_digest", "candidate_digest")}
            report.update(verdict="approve", summary="Checked the candidate in the sandbox.", findings=[],
                          evidence={key: "Read the diff." for key in
                                    ("requirements", "correctness", "scope", "tests", "maintainability", "security")})
            (out / "response.json").write_text(json.dumps(report))
            return 0
        argv = [str(job.work) + item[5:] if item.startswith("/work") else item for item in job.argv]
        argv[0] = sys.executable if argv[0] == "python3" else argv[0]
        with log.open("wb") as output:
            return subprocess.run(argv, cwd=job.work, stdout=output, stderr=subprocess.STDOUT).returncode


class RunnerSandboxTests(unittest.TestCase):
    setUp = test_rc1.TeamTests.setUp
    cli = test_rc1.TeamTests.cli
    git = test_rc1.TeamTests.git
    plan = test_rc1.TeamTests.plan
    approve = test_rc1.TeamTests.approve

    def test_worker_gates_and_reviewer_all_run_through_the_backend(self):
        from builder.brains import Selection
        project, command = self.plan()
        self.approve(command)
        fake = FakeSandbox()
        with mock.patch.dict(os.environ, {"VESPER_STATE_DIR": self.env["VESPER_STATE_DIR"]}), \
                mock.patch.object(secrets, "keychain", return_value="token"):
            result = Runner(project).run(Selection(worker="claude-code", reviewer="codex", settings={}), fake)
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual([job.operation for job in fake.jobs], ["worker", "check", "reviewer"])
        worker, check, reviewer = fake.jobs
        self.assertFalse(worker.work_readonly)
        self.assertTrue(check.work_readonly and reviewer.work_readonly)
        self.assertIn("codex", reviewer.argv)
        self.assertEqual(result["attempts"][-1]["review"]["adapter"], "codex")


class CommandLineTests(unittest.TestCase):
    setUp = test_rc1.TeamTests.setUp
    cli = test_rc1.TeamTests.cli
    git = test_rc1.TeamTests.git
    plan = test_rc1.TeamTests.plan
    approve = test_rc1.TeamTests.approve

    def test_none_backend_warns_on_every_run(self):
        _, command = self.plan()
        self.approve(command)
        self.env["PATH"] = self.empty_path()
        for flags in (("--sandbox", "none"), ("--trust-host",)):
            with self.subTest(flags=flags):
                error = command("run", "--brain", "codex", *flags, code=2)
                self.assertIn("WARNING: no sandbox", error)

    def test_default_backend_comes_from_the_config_and_needs_its_engine(self):
        _, command = self.plan()
        self.approve(command)
        self.env["PATH"] = self.empty_path()
        config = Path(self.env["HOME"]) / ".config" / "vesper" / "config.toml"
        config.unlink()  # the built-in default: docker
        self.assertIn("docker not found", command("run", "--brain", "codex", code=2))
        attempt = command("prepare")
        self.assertIn("docker not found", command("submit", attempt["id"], code=2))
        command("abandon", attempt["id"])
        config.write_text('[sandbox]\nbackend = "podman"\n')
        self.assertIn("podman not found", command("run", "--brain", "codex", code=2))
        self.assertIn("docker not found", command("run", "--brain", "codex", "--sandbox", "docker", code=2))
        self.assertEqual([item["outcome"] for item in command("status")["attempts"]], ["interrupted"])

    def empty_path(self):
        empty = self.root / "empty-bin"
        empty.mkdir(exist_ok=True)
        return str(empty)

    def test_missing_image_names_the_build_command(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "docker"
        fake.write_text("#!/bin/sh\necho 'Error response from daemon: No such image: x' >&2\nexit 1\n")
        fake.chmod(0o700)
        _, command = self.plan()
        self.approve(command)
        self.env["PATH"] = str(bin_dir)
        (Path(self.env["HOME"]) / ".config" / "vesper" / "config.toml").unlink()
        self.assertIn("vesper sandbox build", command("run", "--brain", "codex", code=2))
        fake.write_text("#!/bin/sh\necho 'Cannot connect to the Docker daemon' >&2\nexit 1\n")
        self.assertIn("docker could not be reached", command("run", "--brain", "codex", code=2))


def engine_ready():
    # The runner's own check, so Docker Desktop's tag-lookup flake (finding 39) doesn't skip these.
    try:
        return bool(shutil.which("docker")) and bool(Docker().check().image_id)
    except BuilderError:
        return False


@unittest.skipUnless(engine_ready(), "Docker and the sandbox image are needed (vesper sandbox build)")
class SandboxSelftest(unittest.TestCase):
    setUp = test_rc1.TeamTests.setUp
    cli = test_rc1.TeamTests.cli
    git = test_rc1.TeamTests.git
    plan = test_rc1.TeamTests.plan
    approve = test_rc1.TeamTests.approve

    def test_supervised_gates_run_in_docker(self):
        project, command = self.plan()
        path = project / "plan" / "contract.json"
        contract = json.loads(path.read_text())
        contract["checks"].append({"id": "G2", "command": [
            "python3", "-c", "import os, pathlib, sys; sys.exit(0 if os.getuid() and 'false' in "
            "pathlib.Path('app.js').read_text() and not pathlib.Path(os.path.expanduser('~')).joinpath("
            "'.ssh').exists() else 1)"]})
        contract["requirements"][0]["checks"].append("G2")
        contract["jobs"][0]["checks"].append("G2")
        path.write_text(json.dumps(contract))
        self.approve(command)
        attempt = command("prepare")
        (Path(attempt["workspace"]) / "app.js").write_text("export const loading = false;\n")
        result = command("submit", attempt["id"], "--sandbox", "docker")
        self.assertEqual(result["outcome"], "awaiting_review", result)
        self.assertEqual([(item["id"], item["exit_code"]) for item in result["checks"]], [("G1", 0), ("G2", 0)])

    def test_python_playwright_drives_chromium_in_a_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / "checks").mkdir()
            (home / "candidate").mkdir()
            (home / "checks" / "gate.py").write_text(
                "from playwright.sync_api import sync_playwright\n"
                "with sync_playwright() as p:\n"
                "    browser = p.chromium.launch()\n"
                "    page = browser.new_page()\n"
                "    page.set_content('<h1>ok</h1>')\n"
                "    assert page.inner_text('h1') == 'ok'\n"
                "    browser.close()\n"
                "print('chromium ok')\n")
            log = home / "gate.log"
            code = Docker().check().run(check_job(home, "gate.py"), input_text="", log=log, timeout=180)
            self.assertEqual(code, 0, log.read_text())
            self.assertIn("chromium ok", log.read_text())

    def test_selftest_passes(self):
        result = subprocess.run(["sh", str(ROOT / "sandbox" / "selftest.sh"), "docker"],
                                capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
