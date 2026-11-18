"""Toolchain support: ignored build directories and the build setup step (P1-T6)."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.contracts import BuilderError, inventory
from builder.git_bridge import change
from builder.runner import Runner

import test_builder

IGNORE = ["node_modules", "dist", ".pnpm-store", "test-results", ".turbo"]

# A stand-in for `pnpm install`: lays out a pnpm-like node_modules (with symlinks), records
# the environment it saw and counts its runs in the shared store directory.
FAKE_SETUP = (
    "import json, os, pathlib\n"
    "pkg = pathlib.Path('node_modules/.pnpm/left-pad@1/node_modules/left-pad')\n"
    "pkg.mkdir(parents=True)\n"
    "(pkg / 'index.js').write_text('module.exports = 1')\n"
    "os.symlink('.pnpm/left-pad@1/node_modules/left-pad', 'node_modules/left-pad')\n"
    "names = ('PNPM_STORE_DIR', 'npm_config_store_dir', 'GOMODCACHE', 'GOFLAGS', 'HOME')\n"
    "seen = {'cwd': os.getcwd(), **{n: os.environ.get(n) for n in names}}\n"
    "pathlib.Path('node_modules/setup.json').write_text(json.dumps(seen))\n"
    "store = pathlib.Path(os.environ['PNPM_STORE_DIR'])\n"
    "store.mkdir(parents=True, exist_ok=True)\n"
    "with (store / 'runs.txt').open('a') as runs: runs.write('run\\n')\n")

# A command gate that only passes when the setup output is present in its own work copy.
USES_SETUP = (
    "import json, os, pathlib\n"
    "assert pathlib.Path('node_modules/left-pad/index.js').read_text() == 'module.exports = 1'\n"
    "assert pathlib.Path('first.txt').read_text() == 'one'\n"
    "seen = json.loads(pathlib.Path('node_modules/setup.json').read_text())\n"
    "assert os.environ['GOMODCACHE'] == seen['GOMODCACHE'], (os.environ, seen)\n"
    "assert os.environ['PNPM_STORE_DIR'] == seen['PNPM_STORE_DIR']\n"
    "assert os.getcwd() != seen['cwd'], 'each gate gets its own throwaway copy'\n"
    "pathlib.Path('node_modules/left-pad/index.js').write_text('changed by a gate')\n"
    "print('SETUP ' + json.dumps(seen))\n")

PNPM_LOCK = ("lockfileVersion: '9.0'\n\nsettings:\n  autoInstallPeers: true\n"
             "  excludeLinksFromLockfile: false\n\nimporters:\n\n  .: {}\n")
NODE_TEST = ("import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"
             "import { existsSync } from 'node:fs';\nimport { add } from './app.mjs';\n\n"
             "test('setup ran before this gate', () => {\n"
             "  assert.ok(existsSync('node_modules/.modules.yaml'));\n});\n\n"
             "test('add', () => {\n  assert.equal(add(2, 3), 5);\n});\n")


class ToolchainTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    write_plan = test_builder.BuilderTests.write_plan
    args = test_builder.BuilderTests.args
    command = test_builder.BuilderTests.command
    approve = test_builder.BuilderTests.approve
    candidate = test_builder.BuilderTests.candidate

    def single_job(self, checks, paths, build=None):
        self.plan = {
            "title": "Fixture", "delivery": "local CLI",
            "requirements": [{"id": "R1", "description": "gates pass", "checks": [c["id"] for c in checks]}],
            "checks": checks,
            "jobs": [{"id": "J1", "role": "backend", "goal": "make the gates pass", "paths": paths,
                      "depends_on": [], "checks": [c["id"] for c in checks], "max_attempts": 3}],
        }
        if build is not None:
            self.plan["build"] = build
        self.write_plan()

    def last_attempt(self):
        return self.command("status")["attempts"][-1]

    def snapshot(self):
        return Path(self.command("status")["snapshot"])

    def add_build_dirs(self, workspace):
        """What a worker's tools leave behind: pnpm symlinks, a linked top-level dir, a built bundle."""
        pnpm = workspace / "node_modules" / ".pnpm" / "a@1" / "node_modules" / "a"
        pnpm.mkdir(parents=True)
        (pnpm / "index.js").write_text("module.exports = 1")
        os.symlink(".pnpm/a@1/node_modules/a", workspace / "node_modules" / "a")
        os.symlink("/nonexistent/target", workspace / "node_modules" / ".broken")
        os.link(pnpm / "index.js", workspace / "node_modules" / "hardlink.js")
        os.mkfifo(workspace / "node_modules" / "fifo")
        (workspace / "dist").mkdir()
        (workspace / "dist" / "bundle.js").write_text("built")
        os.symlink("/etc", workspace / ".turbo")

    # ---- ignore handling -------------------------------------------------------------

    def test_inventory_skips_only_ignored_top_level_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "first.txt").write_text("one")
            self.add_build_dirs(root)
            with self.assertRaises(BuilderError):
                inventory(root)
            self.assertEqual(set(inventory(root, IGNORE)), {"first.txt"})
            (root / "src").mkdir()
            os.symlink("../first.txt", root / "src" / "link.txt")
            with self.assertRaisesRegex(BuilderError, "Linked or special path is unsupported: src/link.txt"):
                inventory(root, IGNORE)
            (root / "src" / "link.txt").unlink()
            (root / "src" / "node_modules").mkdir()
            with self.assertRaisesRegex(BuilderError, "Invalid relative path"):
                inventory(root, IGNORE)  # only top-level directories are ignored

    def test_symlinks_in_ignored_dirs_are_allowed_and_never_reach_a_snapshot_export_or_patch(self):
        self.single_job([{"id": "G1", "script": "first.py"}], ["first.txt"], {"ignore": IGNORE})
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        self.add_build_dirs(workspace)
        self.command("submit", attempt["id"])
        self.assertEqual(self.last_attempt()["outcome"], "accepted")
        self.assertEqual(self.last_attempt()["changed"], ["first.txt"])
        self.assertEqual(sorted(path.name for path in self.snapshot().iterdir()), ["first.txt"])

        destination = self.project.parent / "export"
        self.command("export", str(destination))
        self.assertEqual(sorted(path.name for path in destination.iterdir()), ["first.txt"])

        runner = Runner(self.project)
        patch, summary = change(runner, runner.state(), {"path": "repo", "commit": "0" * 40})
        self.assertEqual(summary["files"], ["first.txt"])
        self.assertNotIn(b"node_modules", patch)
        self.assertNotIn(b"dist", patch)

    def test_symlink_or_nested_build_dir_outside_ignored_dirs_is_rejected(self):
        self.single_job([{"id": "G1", "script": "first.py"}], ["first.txt", "src"], {"ignore": IGNORE})
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        (workspace / "src").mkdir()
        os.symlink("../first.txt", workspace / "src" / "link.txt")
        self.command("submit", attempt["id"], code=1)
        self.assertIn("Linked or special path is unsupported: src/link.txt", self.last_attempt()["reason"])

        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        (workspace / "src" / "node_modules").mkdir(parents=True)
        self.command("submit", attempt["id"], code=1)
        self.assertIn("Invalid relative path: 'src/node_modules'", self.last_attempt()["reason"])
        self.assertEqual(self.command("status")["completed"], [])

    def test_without_build_ignore_build_dirs_stay_rejected(self):
        self.single_job([{"id": "G1", "script": "first.py"}], ["first.txt"])
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        (workspace / "node_modules").mkdir()
        self.command("submit", attempt["id"], code=1)
        self.assertIn("node_modules", self.last_attempt()["reason"])
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        (workspace / "dist").mkdir()
        self.command("submit", attempt["id"], code=1)
        self.assertIn("Changes outside job scope: dist", self.last_attempt()["reason"])

    def test_invalid_build_fails_review(self):
        cases = [
            ("node_modules", "Invalid build"),
            ({"ignore": ["dist"], "other": 1}, "Invalid build"),
            ({"ignore": "dist"}, "Invalid build ignore"),
            ({"ignore": ["dist", "dist"]}, "Invalid build ignore"),
            ({"ignore": ["web/dist"]}, "Invalid build ignore"),
            ({"ignore": [".."]}, "Invalid build ignore"),
            ({"ignore": [".git"]}, "Invalid build ignore"),
            ({"ignore": [".builder"]}, "Invalid build ignore"),
            ({"ignore": [""]}, "Invalid build ignore"),
            ({"setup": ["pnpm", "install"]}, "Invalid command for build setup"),
            ({"setup": [[]]}, "Invalid command for build setup"),
            ({"setup": "pnpm install"}, "Invalid build setup"),
            ({"setup": [["/usr/bin/pnpm", "install"]]}, "bare program name"),
            ({"setup": [["./pnpm"]]}, "bare program name"),
            ({"setup": [["pnpm", "install"]], "timeout": 0}, "Invalid build timeout"),
            ({"setup": [["pnpm", "install"]], "timeout": "60"}, "Invalid build timeout"),
            ({"ignore": ["first.txt"]}, "inside ignored build directory"),
        ]
        for build, message in cases:
            with self.subTest(build=build):
                self.single_job([{"id": "G1", "script": "first.py"}], ["first.txt"], build)
                self.assertIn(message, self.command("review", code=2))

    def test_job_paths_and_seed_must_stay_outside_ignored_dirs(self):
        self.single_job([{"id": "G1", "script": "first.py"}], ["first.txt", "dist/app.js"], {"ignore": ["dist"]})
        self.assertIn("inside ignored build directory", self.command("review", code=2))
        self.single_job([{"id": "G1", "script": "first.py"}], ["first.txt"], {"ignore": ["dist"]})
        (self.project / "seed" / "dist").mkdir()
        (self.project / "seed" / "dist" / "tracked.js").write_text("tracked")
        self.assertIn("Seed contains ignored build directory: dist", self.command("review", code=2))

    def test_repair_runs_refuse_build_setup(self):
        self.single_job([{"id": "G1", "script": "first.py"}], ["first.txt"], {"setup": [["pnpm", "install"]]})
        (self.project / "plan" / "repair.json").write_text("{}")
        self.assertIn("Vesper repairs cannot run build setup", self.command("review", code=2))

    # ---- setup step --------------------------------------------------------------------

    def test_setup_runs_once_before_the_first_command_gate_with_a_shared_cache(self):
        self.single_job([{"id": "G0", "script": "first.py"},
                         {"id": "G1", "command": ["python3", "-c", USES_SETUP]},
                         {"id": "G2", "command": ["python3", "-c", USES_SETUP]}],
                        ["first.txt"], {"ignore": IGNORE, "setup": [["python3", "-c", FAKE_SETUP]]})
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        self.command("submit", attempt["id"])
        done = self.last_attempt()
        self.assertEqual(done["outcome"], "accepted", done.get("reason"))
        self.assertEqual([item["exit_code"] for item in done["setup"]], [0])
        self.assertEqual([item["id"] for item in done["checks"]], ["G0", "G1", "G2"])

        cache = (self.project / ".builder" / "cache").resolve()
        self.assertEqual((cache / "pnpm-store" / "runs.txt").read_text(), "run\n")
        log = (self.project / done["checks"][1]["log"]).read_text()
        seen = json.loads(next(line for line in log.splitlines() if line.startswith("SETUP "))[6:])
        self.assertEqual(Path(seen["PNPM_STORE_DIR"]).resolve(), cache / "pnpm-store")
        self.assertEqual(seen["npm_config_store_dir"], seen["PNPM_STORE_DIR"])
        self.assertEqual(Path(seen["GOMODCACHE"]).resolve(), cache / "go-mod")
        self.assertEqual(seen["GOFLAGS"], "-modcacherw")
        self.assertFalse(Path(seen["cwd"]).exists(), "the prepared copy is removed after verification")
        self.assertEqual(sorted(path.name for path in self.snapshot().iterdir()), ["first.txt"])
        self.assertFalse(any(path.name == "node_modules"
                             for path in (self.project / ".builder" / "attempts").rglob("*")))

    def test_launcher_gets_a_setup_operation_before_check_command(self):
        record = self.project.parent / "launches.jsonl"
        launcher = self.project.parent / "launcher"
        launcher.write_text(
            f"#!{sys.executable}\nimport json, os, shutil, subprocess, sys\n"
            f"with open({str(record)!r}, 'a') as out:\n"
            "    out.write(json.dumps({'argv': sys.argv[1:3], 'cwd': os.getcwd(),\n"
            "                          'store': os.environ.get('PNPM_STORE_DIR')}) + '\\n')\n"
            "if sys.argv[1] == 'check':\n"
            "    raise SystemExit(subprocess.call([sys.executable, '-I', '-B', *sys.argv[2:]]))\n"
            "argv = sys.argv[sys.argv.index('--') + 1:]\n"
            "raise SystemExit(subprocess.call([shutil.which(argv[0]), *argv[1:]]))\n")
        launcher.chmod(0o700)
        self.single_job([{"id": "G0", "script": "first.py"},
                         {"id": "G1", "command": ["python3", "-c", USES_SETUP]}],
                        ["first.txt"], {"ignore": IGNORE, "setup": [["python3", "-c", FAKE_SETUP]]})
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        self.command("submit", attempt["id"], "--launcher", str(launcher))
        self.assertEqual(self.last_attempt()["outcome"], "accepted", self.last_attempt().get("reason"))
        launches = [json.loads(line) for line in record.read_text().splitlines()]
        self.assertEqual([item["argv"][0] for item in launches], ["check", "setup", "check-command"])
        setup, gate = launches[1], launches[2]
        self.assertEqual(os.path.realpath(setup["argv"][1]), os.path.realpath(setup["cwd"]))
        self.assertNotEqual(setup["cwd"], gate["cwd"])
        self.assertEqual(Path(setup["store"]).resolve(), (self.project / ".builder" / "cache" / "pnpm-store").resolve())

    def test_setup_does_not_run_for_script_gates(self):
        self.single_job([{"id": "G1", "script": "first.py"}], ["first.txt"],
                        {"ignore": IGNORE, "setup": [["python3", "-c", FAKE_SETUP]]})
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        self.command("submit", attempt["id"])
        self.assertEqual(self.last_attempt()["outcome"], "accepted")
        self.assertNotIn("setup", self.last_attempt())
        self.assertFalse((self.project / ".builder" / "cache" / "pnpm-store" / "runs.txt").exists())

    def test_failing_setup_rejects_the_candidate(self):
        self.single_job([{"id": "G1", "command": ["python3", "-c", "pass"]}], ["first.txt"],
                        {"ignore": IGNORE, "setup": [["python3", "-c", "print('lockfile out of date'); exit(3)"],
                                                      ["python3", "-c", "raise SystemExit('never runs')"]]})
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        self.command("submit", attempt["id"], code=1)
        done = self.last_attempt()
        self.assertEqual(done["failure_kind"], "check")
        self.assertIn("Build setup", done["reason"])
        self.assertIn("lockfile out of date", done["reason"])
        self.assertEqual([item["exit_code"] for item in done["setup"]], [3])
        self.assertEqual(done["checks"], [])

    def test_setup_that_changes_tracked_files_rejects_the_candidate(self):
        rewrite = "import pathlib; pathlib.Path('pnpm-lock.yaml').write_text('rewritten')"
        self.single_job([{"id": "G1", "command": ["python3", "-c", "pass"]}], ["first.txt", "pnpm-lock.yaml"],
                        {"ignore": IGNORE, "setup": [["python3", "-c", rewrite]]})
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        (workspace / "pnpm-lock.yaml").write_text(PNPM_LOCK)
        self.command("submit", attempt["id"], code=1)
        self.assertIn("Build setup changed tracked files: pnpm-lock.yaml", self.last_attempt()["reason"])

    @unittest.skipUnless(shutil.which("pnpm") and shutil.which("node"), "pnpm or node is not installed")
    def test_pnpm_setup_then_node_test_gate(self):
        (self.project / "checks" / "nodetests").mkdir()
        (self.project / "checks" / "nodetests" / "app.test.mjs").write_text(NODE_TEST)
        self.single_job([{"id": "G1", "command": ["node", "--test"],
                          "overlay": {"from": "nodetests", "to": "."}, "timeout": 300}],
                        ["package.json", "pnpm-lock.yaml", "app.mjs"],
                        {"ignore": IGNORE, "setup": [["pnpm", "install", "--frozen-lockfile"]], "timeout": 600})
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "package.json").write_text('{"name": "pocket", "version": "1.0.0", "private": true}\n')
        (workspace / "pnpm-lock.yaml").write_text(PNPM_LOCK)
        (workspace / "app.mjs").write_text("export const add = (a, b) => a + b;\n")
        self.command("submit", attempt["id"])
        done = self.last_attempt()
        logs = {item["id"]: (self.project / item["log"]).read_text() for item in done["checks"]}
        self.assertEqual(done["outcome"], "accepted", (done.get("reason"), logs))
        self.assertEqual([item["exit_code"] for item in done["setup"]], [0])
        self.assertIn("pass 2", logs["G1"])
        self.assertEqual(sorted(path.name for path in self.snapshot().iterdir()),
                         ["app.mjs", "package.json", "pnpm-lock.yaml"])


if __name__ == "__main__":
    unittest.main()
