import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "build_local.py")]


class BuilderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name) / "project"
        self.command("init", "--idea", "Write two files")
        (self.project / "plan" / "product.md").write_text("# Approved idea\n")
        (self.project / "plan" / "design.md").write_text("# CLI behavior\n")
        (self.project / "plan" / "architecture.md").write_text("# File layout\n")
        (self.project / "plan" / "decisions.md").write_text("# Delegated choices\n")
        (self.project / "checks" / "first.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "assert (Path(sys.argv[1]) / 'first.txt').read_text() == 'one'\n")
        (self.project / "checks" / "last.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "assert (Path(sys.argv[1]) / 'second.txt').read_text() == 'two'\n")
        self.plan = {
            "title": "Fixture", "delivery": "local CLI",
            "requirements": [{"id": "R1", "description": "two files", "checks": ["G1", "G2"]}],
            "checks": [{"id": "G1", "script": "first.py"}, {"id": "G2", "script": "last.py"}],
            "jobs": [
                {"id": "J1", "role": "backend", "goal": "write first", "paths": ["first.txt"],
                 "depends_on": [], "checks": ["G1"], "max_attempts": 3},
                {"id": "J2", "role": "frontend", "goal": "write second", "paths": ["second.txt"],
                 "depends_on": ["J1"], "checks": ["G2"], "max_attempts": 3},
            ]
        }
        self.write_plan()

    def write_plan(self):
        (self.project / "plan" / "contract.json").write_text(json.dumps(self.plan))

    def args(self, *args):
        return [*CLI, "--project", str(self.project), *args]

    def command(self, *args, code=0, env=None):
        result = subprocess.run(self.args(*args), capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout) if result.stdout else result.stderr

    def approve(self):
        review = self.command("review")
        self.command("approve", "--digest", review["digest"])

    def candidate(self, job):
        attempt = self.command("prepare")
        self.assertEqual(attempt["job"], job)
        return attempt, Path(attempt["workspace"])

    def test_approval_requires_exact_review_and_blocks_jobs(self):
        self.command("prepare", code=2)
        digest = self.command("review")["digest"]
        (self.project / "plan" / "design.md").write_text("changed")
        self.command("approve", "--digest", digest, code=2)
        self.approve()
        (self.project / "checks" / "first.py").write_text("raise SystemExit(0)\n")
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("wrong")
        self.command("submit", attempt["id"], code=1)
        self.assertEqual(self.command("status")["completed"], [])

    def test_rejects_cyclic_jobs_and_uncovered_requirements(self):
        self.plan["jobs"][0]["depends_on"] = ["J2"]
        self.write_plan()
        self.assertIn("cycle", self.command("review", code=2))
        self.plan["jobs"][0]["depends_on"] = []
        self.plan["requirements"][0]["checks"] = []
        self.write_plan()
        self.command("review", code=2)

    def test_rejects_out_of_scope_and_symlink_then_promotes_only_verified_files(self):
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        (workspace / "second.txt").write_text("bypass")
        self.command("submit", attempt["id"], code=1)
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").symlink_to("/etc/passwd")
        self.command("submit", attempt["id"], code=1)
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        self.command("submit", attempt["id"])
        self.assertEqual(self.command("status")["completed"], ["J1"])
        (workspace / "first.txt").write_text("later")
        attempt, workspace = self.candidate("J2")
        self.assertEqual((workspace / "first.txt").read_text(), "one")
        (workspace / "second.txt").write_text("two")
        self.command("submit", attempt["id"])
        state = self.command("status")
        self.assertEqual(state["completed"], ["J1", "J2"])
        self.assertEqual(state["status"], "complete")
        self.assertEqual([item["id"] for item in state["attempts"][-1]["checks"]], ["G1", "G2"])

    def test_rejects_out_of_scope_directory_changes(self):
        (self.project / "seed" / "protected").mkdir()
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        (workspace / "protected").chmod(0o777)
        (workspace / "unexpected").mkdir()
        result = self.command("submit", attempt["id"], code=1)
        self.assertIn("protected", result["reason"])
        self.assertIn("unexpected", result["reason"])

    def test_gate_mutation_is_caught_before_the_next_gate(self):
        (self.project / "checks" / "first.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "(Path(sys.argv[1]) / 'second.txt').write_text('temporary')\n")
        (self.project / "checks" / "last.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "(Path(sys.argv[1]) / 'second.txt').write_text('two')\n")
        self.plan["jobs"] = [dict(self.plan["jobs"][0], paths=["first.txt", "second.txt"], checks=["G1", "G2"])]
        self.write_plan()
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        (workspace / "second.txt").write_text("two")
        result = self.command("submit", attempt["id"], code=1)
        self.assertEqual([check["id"] for check in result["checks"]], ["G1"])
        self.assertEqual(self.command("status")["completed"], [])

    def test_retry_grant_is_explicit_and_preserves_failed_attempt(self):
        self.plan["jobs"][0]["max_attempts"] = 1
        self.write_plan()
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("wrong")
        self.command("submit", attempt["id"], code=1)
        self.assertEqual(self.command("status", code=1)["status"], "blocked")
        self.command("prepare", code=2)
        self.command("retry", "--reason", "Fixed local provider login")
        replacement, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        self.command("submit", replacement["id"])
        state = self.command("status")
        self.assertEqual([item["outcome"] for item in state["attempts"]], ["rejected", "accepted"])
        self.assertEqual(state["retry_grants"][0]["reason"], "Fixed local provider login")

    def test_isolation_launcher_receives_workers_and_checks(self):
        self.approve()
        launcher = self.project.parent / "launcher"
        launcher.write_text(
            f"#!{sys.executable}\n"
            "import os, sys\nfrom pathlib import Path\n"
            "assert 'PILOT_SECRET' not in os.environ\n"
            "if sys.argv[1] == 'worker':\n"
            " assert sys.argv[2] == 'codex'\n"
            " prompt = sys.stdin.read()\n"
            " if 'Job J1' in prompt: Path('first.txt').write_text('one')\n"
            " else: Path('second.txt').write_text('two')\n"
            "elif sys.argv[1] == 'check':\n"
            " os.execv(sys.executable, [sys.executable, '-I', '-B', *sys.argv[2:]])\n"
            "else: raise AssertionError(sys.argv)\n")
        launcher.chmod(0o700)
        env = dict(os.environ, PILOT_SECRET="should not cross the worker boundary")
        self.command("run", "--provider", "codex", "--launcher", str(launcher), env=env)
        self.assertEqual(self.command("status")["status"], "complete")

    def test_rejects_tampered_accepted_snapshot(self):
        self.approve()
        accepted = Path(self.command("status")["snapshot"])
        (accepted / "extra.txt").write_text("unexpected")
        self.command("status", code=2)
        self.command("prepare", code=2)

    def test_only_one_manual_attempt_can_be_active_and_abandon_resumes(self):
        self.approve()
        attempt, _ = self.candidate("J1")
        self.command("prepare", code=2)
        self.command("abandon", attempt["id"])
        replacement, _ = self.candidate("J1")
        self.assertNotEqual(replacement["id"], attempt["id"])

    def provider_environment(self, body, name="codex"):
        bin_dir = self.project.parent / "bin"
        bin_dir.mkdir(exist_ok=True)
        exe = bin_dir / name
        exe.write_text(f"#!{sys.executable}\n" + body)
        exe.chmod(0o700)
        return dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])

    def test_provider_dispatch_checks_protocol_and_uses_fresh_scoped_jobs(self):
        self.approve()
        self.command("run", "--provider", "codex", code=2)
        env = self.provider_environment(
            "from pathlib import Path\nimport sys\n"
            "assert '--skip-git-repo-check' in sys.argv and sys.argv[-1] == '-'\n"
            "prompt = sys.stdin.read()\n"
            "assert 'Approved contract' in prompt and 'write' in prompt\n"
            "if 'Job J1' in prompt: Path('first.txt').write_text('one')\n"
            "elif 'Job J2' in prompt: Path('second.txt').write_text('two')\n"
            "else: raise AssertionError(prompt)\n")
        self.command("run", "--provider", "codex", "--trust-host", env=env)
        self.assertEqual(self.command("status")["status"], "complete")

    def test_claude_adapter_supports_provider_switch(self):
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        self.command("submit", attempt["id"])
        env = self.provider_environment(
            "from pathlib import Path\nimport sys\n"
            "assert '-p' in sys.argv and 'Job J2' in sys.stdin.read()\n"
            "assert Path('first.txt').read_text() == 'one'\n"
            "Path('second.txt').write_text('two')\n", name="claude")
        self.command("run", "--provider", "claude", "--trust-host", env=env)
        self.assertEqual(self.command("status")["status"], "complete")

    def test_supervisor_stops_descendants_when_leader_and_coordinator_exit(self):
        self.approve()
        env = self.provider_environment(
            "import os, time\nfrom pathlib import Path\n"
            "pid = os.fork()\n"
            "if pid == 0:\n"
            " time.sleep(1)\n"
            " Path('escaped').touch()\n"
            "else:\n"
            " Path('spawned').touch()\n"
            " while not Path('release').exists(): time.sleep(.01)\n"
            " Path('leader-done').touch()\n")
        proc = subprocess.Popen(self.args("run", "--provider", "codex", "--trust-host"), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        supervisor = None
        try:
            for _ in range(90):
                active = self.command("status")["active"]
                if active and active.get("child_pid"):
                    workspace = self.project / ".builder" / "attempts" / active["id"] / "workspace"
                    if (workspace / "spawned").exists():
                        supervisor = active["child_pid"]
                        break
                time.sleep(.01)
            self.assertIsNotNone(supervisor)
            os.kill(supervisor, signal.SIGSTOP)
            proc.kill()
            proc.wait(timeout=2)
            (workspace / "release").touch()
            for _ in range(30):
                if (workspace / "leader-done").exists():
                    break
                time.sleep(.01)
            self.assertTrue((workspace / "leader-done").exists())
            time.sleep(.08)
            os.kill(supervisor, signal.SIGCONT)
            time.sleep(1)
            self.assertFalse((workspace / "escaped").exists())
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if supervisor:
                try:
                    os.killpg(supervisor, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_killed_runner_preserves_checkpoint_and_recovers_in_new_process(self):
        self.approve()
        env = self.provider_environment(
            "from pathlib import Path\nimport time\n"
            "Path('first.txt').write_text('unverified')\n"
            "time.sleep(20)\n")
        proc = subprocess.Popen(self.args("run", "--provider", "codex", "--trust-host"), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = self.command("status")
                if state["active"] and state["active"].get("child_pid"):
                    break
                time.sleep(0.03)
            else:
                self.fail("worker did not start")
            self.command("prepare", code=2)
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=3)
            self.assertFalse((Path(state["snapshot"]) / "first.txt").exists())
            env = self.provider_environment(
                "from pathlib import Path\nimport sys\n"
                "p = sys.stdin.read()\n"
                "assert not Path('first.txt').exists() if 'Job J1' in p else True\n"
                "if 'Job J1' in p: Path('first.txt').write_text('one')\n"
                "else: Path('second.txt').write_text('two')\n")
            self.command("run", "--provider", "codex", "--trust-host", env=env)
            state = self.command("status")
            self.assertEqual(state["attempts"][0]["outcome"], "interrupted")
            self.assertEqual(state["completed"], ["J1", "J2"])
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if "state" in locals() and state.get("active") and state["active"].get("child_pid"):
                try:
                    os.killpg(state["active"]["child_pid"], signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    unittest.main()
