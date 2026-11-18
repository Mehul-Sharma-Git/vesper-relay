"""Command gates in any language (P1-T5)."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.contracts import inventory
from builder.runner import execute_command_check

import test_builder

GO_MOD = "module example.com/calc\n\ngo 1.21\n"
GO_BROKEN = "package calc\n\nfunc Add(a, b int) int { return a - b }\n"
GO_FIXED = "package calc\n\nfunc Add(a, b int) int { return a + b }\n"
GO_TEST = ('package calc\n\nimport "testing"\n\n'
           'func TestAdd(t *testing.T) {\n'
           '\tif got := Add(2, 3); got != 5 {\n\t\tt.Fatalf("Add(2, 3) = %d, want 5", got)\n\t}\n}\n')

PROBE = ("import json, os, pathlib\n"
         "assert pathlib.Path('t/probe.txt').read_text() == 'qa', 'overlay must win'\n"
         "assert pathlib.Path('first.txt').read_text() == 'one'\n"
         "pathlib.Path('first.txt').write_text('mutated by the gate')\n"
         "pathlib.Path('report.out').write_text('tool output')\n"
         "names = ('HOME', 'TMPDIR', 'GOCACHE', 'GOPATH', 'XDG_CACHE_HOME', 'PATH')\n"
         "print('GATE ' + json.dumps({'cwd': os.getcwd(), **{n: os.environ.get(n) for n in names}}))\n")


class CommandGateTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    write_plan = test_builder.BuilderTests.write_plan
    args = test_builder.BuilderTests.args
    command = test_builder.BuilderTests.command
    approve = test_builder.BuilderTests.approve
    candidate = test_builder.BuilderTests.candidate

    def single_job(self, check, paths):
        self.plan = {
            "title": "Fixture", "delivery": "local CLI",
            "requirements": [{"id": "R1", "description": "gate passes", "checks": ["G1"]}],
            "checks": [dict(check, id="G1")],
            "jobs": [{"id": "J1", "role": "backend", "goal": "make the gate pass", "paths": paths,
                      "depends_on": [], "checks": ["G1"], "max_attempts": 3}],
        }
        self.write_plan()

    def exported(self):
        destination = self.project.parent / "export"
        self.command("export", str(destination))
        return destination

    @unittest.skipUnless(shutil.which("go"), "go is not installed")
    def test_go_overlay_test_fails_broken_candidate_and_passes_fixed_one(self):
        (self.project / "checks" / "gotests").mkdir()
        (self.project / "checks" / "gotests" / "calc_test.go").write_text(GO_TEST)
        self.single_job({"command": ["go", "test", "./..."], "overlay": {"from": "gotests", "to": "."},
                         "timeout": 600}, ["go.mod", "calc.go"])
        self.approve()

        attempt, workspace = self.candidate("J1")
        (workspace / "go.mod").write_text(GO_MOD)
        (workspace / "calc.go").write_text(GO_BROKEN)
        result = self.command("submit", attempt["id"], code=1)
        self.assertNotEqual(result["checks"][0]["exit_code"], 0)
        self.assertIn("Add(2, 3) = -1, want 5", (self.project / result["checks"][0]["log"]).read_text())

        attempt, workspace = self.candidate("J1")
        (workspace / "go.mod").write_text(GO_MOD)
        (workspace / "calc.go").write_text(GO_FIXED)
        result = self.command("submit", attempt["id"])
        self.assertEqual(result["checks"][0]["exit_code"], 0, (self.project / result["checks"][0]["log"]).read_text())
        self.assertEqual(self.command("status")["completed"], ["J1"])
        self.assertEqual(sorted(path.name for path in self.exported().iterdir()), ["calc.go", "go.mod"])

    def test_command_gate_runs_in_a_throwaway_copy_with_its_overlay(self):
        (self.project / "checks" / "qa").mkdir()
        (self.project / "checks" / "qa" / "probe.txt").write_text("qa")
        self.single_job({"command": ["python3", "-c", PROBE], "overlay": {"from": "qa", "to": "t"}},
                        ["first.txt", "t"])
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        (workspace / "t").mkdir()
        (workspace / "t" / "probe.txt").write_text("worker")
        result = self.command("submit", attempt["id"])
        log = (self.project / result["checks"][0]["log"]).read_text()
        self.assertEqual(result["checks"][0]["exit_code"], 0, log)
        seen = json.loads(next(line for line in log.splitlines() if line.startswith("GATE "))[5:])

        home = os.path.realpath(seen["HOME"])
        self.assertEqual(os.path.realpath(seen["TMPDIR"]), home)
        for name in ("GOCACHE", "GOPATH", "XDG_CACHE_HOME", "cwd"):
            self.assertTrue(os.path.realpath(seen[name]).startswith(home + os.sep), (name, seen))
        self.assertFalse(Path(home).exists(), "the gate's temporary directory is removed")
        self.assertIn(os.path.dirname(shutil.which("python3")), seen["PATH"].split(os.pathsep))

        app = self.exported()
        self.assertEqual((app / "first.txt").read_text(), "one")
        self.assertEqual((app / "t" / "probe.txt").read_text(), "worker")
        self.assertFalse((app / "report.out").exists())

    def test_command_must_start_with_a_bare_program_name(self):
        for command in (["/bin/sh", "-c", "true"], ["./go", "test"], ["bin/go"], ["..", "x"], [".hidden"],
                        ["C:\\go\\go.exe"], ["-rf"], [""]):
            with self.subTest(command=command):
                self.single_job({"command": command}, ["first.txt"])
                self.assertIn("bare program name", self.command("review", code=2))

    def test_malformed_command_checks_fail_review(self):
        (self.project / "checks" / "qa").mkdir()
        (self.project / "checks" / "qa" / "probe.txt").write_text("qa")
        cases = [
            ({"command": []}, "Invalid command"),
            ({"command": "go test ./..."}, "Invalid command"),
            ({"command": ["go", 3]}, "Invalid command"),
            ({"command": ["go", "a\0b"]}, "Invalid command"),
            ({"script": "first.py", "command": ["go", "test"]}, "exactly one of script or command"),
            ({}, "exactly one of script or command"),
            ({"script": "first.py", "overlay": {"from": "qa", "to": "t"}}, "overlay needs a command"),
            ({"command": ["go"], "overlay": {"from": "missing", "to": "t"}}, "Overlay directory missing"),
            ({"command": ["go"], "overlay": {"from": "first.py", "to": "t"}}, "Overlay directory missing"),
            ({"command": ["go"], "overlay": {"from": "qa", "to": "../t"}}, "Invalid relative path"),
            ({"command": ["go"], "overlay": {"from": "qa", "to": "/t"}}, "Invalid relative path"),
            ({"command": ["go"], "overlay": {"from": "qa/../qa", "to": "t"}}, "Invalid relative path"),
            ({"command": ["go"], "overlay": {"from": "qa"}}, "Invalid overlay"),
            ({"command": ["go"], "overlay": {"from": "qa", "to": "t", "mode": "x"}}, "Invalid overlay"),
            ({"command": ["go"], "overlay": "qa"}, "Invalid overlay"),
        ]
        for check, message in cases:
            with self.subTest(check=check):
                self.single_job(check, ["first.txt"])
                self.assertIn(message, self.command("review", code=2))

    def test_gate_env_cannot_replace_the_tool_cache_locations(self):
        for name in ("GOCACHE", "GOPATH", "XDG_CACHE_HOME"):
            with self.subTest(name=name):
                self.plan["gate_env"] = [name]
                self.write_plan()
                self.assertIn(f"gate_env cannot replace {name}", self.command("review", code=2))

    def test_command_and_overlay_are_part_of_the_digest(self):
        (self.project / "checks" / "qa").mkdir()
        (self.project / "checks" / "qa" / "probe.txt").write_text("qa")
        self.single_job({"command": ["go", "test", "./..."]}, ["first.txt"])
        digests = {self.command("review")["digest"]}
        self.single_job({"command": ["go", "test", "./pkg"]}, ["first.txt"])
        digests.add(self.command("review")["digest"])
        self.single_job({"command": ["go", "test", "./pkg"], "overlay": {"from": "qa", "to": "."}}, ["first.txt"])
        digests.add(self.command("review")["digest"])
        (self.project / "checks" / "qa" / "probe.txt").write_text("changed")
        digests.add(self.command("review")["digest"])
        self.assertEqual(len(digests), 4)


class ExecuteCommandCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.checks = self.root / "checks"
        (self.checks / "qa").mkdir(parents=True)
        (self.checks / "qa" / "probe.txt").write_text("qa")
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        (self.candidate / "app.txt").write_text("app")
        self.log = self.root / "logs" / "G1.log"
        self.log.parent.mkdir()

    def run_gate(self, command, launcher=None, overlay=None):
        return execute_command_check(command, overlay, self.checks, inventory(self.checks), self.candidate,
                                     inventory(self.candidate), self.log, launcher, timeout=30)

    def python(self, code):
        return ["python3", "-c", code]

    def test_writing_into_the_verified_candidate_is_detected(self):
        target = self.candidate / "app.txt"
        code, intact = self.run_gate(self.python(f"open({str(target)!r}, 'w').write('changed')"))
        self.assertEqual(code, 0)
        self.assertFalse(intact)

    def test_writing_into_checks_is_detected(self):
        target = self.checks / "qa" / "probe.txt"
        code, intact = self.run_gate(self.python(f"open({str(target)!r}, 'w').write('changed')"))
        self.assertEqual(code, 0)
        self.assertFalse(intact)

    def test_writing_into_the_work_copy_is_allowed(self):
        code, intact = self.run_gate(self.python("open('app.txt', 'w').write('x'); open('new', 'w').write('y')"),
                                     overlay={"from": "qa", "to": "."})
        self.assertEqual((code, intact), (0, True), self.log.read_text())
        self.assertEqual((self.candidate / "app.txt").read_text(), "app")
        self.assertFalse((self.candidate / "probe.txt").exists())

    def test_missing_program_fails_the_gate(self):
        code, intact = self.run_gate(["vesper-no-such-program-p1t5", "--version"])
        self.assertEqual((code, intact), (127, True))
        self.assertIn("vesper-no-such-program-p1t5", self.log.read_text())

    def test_overlay_cannot_replace_a_candidate_directory_with_a_file(self):
        (self.candidate / "probe.txt").mkdir()
        code, intact = self.run_gate(self.python("pass"), overlay={"from": "qa", "to": "."})
        self.assertNotEqual(code, 0)
        self.assertTrue(intact)
        self.assertIn("Overlay", self.log.read_text())

    def test_launcher_gets_check_command_with_cwd_and_argv(self):
        record = self.root / "launcher-args.json"
        launcher = self.root / "launcher"
        launcher.write_text(f"#!{sys.executable}\nimport json, os, sys\n"
                            f"json.dump({{'argv': sys.argv[1:], 'cwd': os.getcwd(),\n"
                            f"           'overlay': open('probe.txt').read()}}, open({str(record)!r}, 'w'))\n")
        launcher.chmod(0o755)
        code, intact = self.run_gate(["go", "test", "./..."], launcher=str(launcher),
                                     overlay={"from": "qa", "to": "."})
        self.assertEqual((code, intact), (0, True), self.log.read_text())
        seen = json.loads(record.read_text())
        self.assertEqual(seen["argv"][0], "check-command")
        self.assertEqual(os.path.realpath(seen["argv"][1]), os.path.realpath(seen["cwd"]))
        self.assertEqual(seen["argv"][2:], ["--", "go", "test", "./..."])
        self.assertEqual(seen["overlay"], "qa")
        self.assertNotEqual(os.path.realpath(seen["cwd"]), os.path.realpath(self.candidate))


if __name__ == "__main__":
    unittest.main()
