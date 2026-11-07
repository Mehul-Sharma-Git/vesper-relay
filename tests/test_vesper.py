import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VesperTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "site"
        self.repo.mkdir()
        self.env = dict(os.environ, VESPER_STATE_DIR=str(self.root / "state"),
                        HOME=str(self.root / "home"))
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        (self.repo / "app.js").write_text("export const loading = true;\n")
        (self.repo / "notes.txt").write_text("original\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], env=self.env)

    def cli(self, *args, code=0, cwd=None, binary=False, checkout=ROOT):
        p = subprocess.run([sys.executable, "-B", str(checkout / "vesper.py"), *map(str, args)],
                           cwd=cwd or self.repo, env=self.env, capture_output=True)
        self.assertEqual(p.returncode, code, p.stdout.decode() + p.stderr.decode())
        return p.stdout if binary else json.loads(p.stdout) if p.stdout else p.stderr.decode()

    def build(self):
        project = Path(self.cli("start", "--mode", "bug", "--idea", "Spinner never stops")["project"])
        command = lambda *args, **kwargs: self.cli("--project", project, *args, **kwargs)
        for name in ("product", "design", "architecture", "decisions"):
            (project / "plan" / f"{name}.md").write_text("Spinner stops on failure.\n")
        contract = {"title": "Fix spinner", "delivery": "Git patch",
                    "requirements": [{"id": "R1", "description": "Spinner stops on failure", "checks": ["G1"]}],
                    "checks": [{"id": "G1", "script": "gate.py"}],
                    "jobs": [{"id": "J1", "role": "frontend engineer", "goal": "Fix the spinner",
                              "paths": ["app.js"], "depends_on": [], "checks": ["G1"]}]}
        (project / "plan" / "contract.json").write_text(json.dumps(contract))
        (project / "checks" / "gate.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "assert (Path(sys.argv[1]) / 'app.js').read_text() == 'export const loading = false;\\n'\n")
        command("approve", "--digest", command("review")["digest"])
        attempt = command("prepare")
        command("submit", attempt["id"], code=1)
        attempt = command("prepare")
        (Path(attempt["workspace"]) / "app.js").write_text("export const loading = false;\n")
        command("submit", attempt["id"])
        return project, command

    def test_existing_repo_preserves_unrelated_work_and_requires_reviewed_patch(self):
        (self.repo / "notes.txt").write_text("work in progress\n")
        (self.repo / ".env").write_text("PRIVATE=secret")
        project, command = self.build()
        self.assertFalse((project / "seed" / ".env").exists())
        self.assertEqual((project / "seed" / "notes.txt").read_text(), "original\n")
        self.assertEqual((self.repo / "app.js").read_text(), "export const loading = true;\n")
        patch = command("patch", binary=True)
        self.assertIn(b"loading = false", patch)
        result = command("review-change")
        self.assertEqual(result["files"], ["app.js"])
        self.assertEqual(self.cli("runs", "--repo", self.repo)["runs"][0]["project"], str(project))
        command("apply", "--digest", "invalid", code=2)
        command("apply", "--digest", result["digest"])
        self.assertEqual((self.repo / "app.js").read_text(), "export const loading = false;\n")
        self.assertEqual((self.repo / "notes.txt").read_text(), "work in progress\n")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), b"")

    def test_apply_refuses_conflicting_edits_and_moved_head(self):
        _, command = self.build()
        digest = command("review-change")["digest"]
        (self.repo / "app.js").write_text("user edit\n")
        command("apply", "--digest", digest, code=2)
        self.assertEqual((self.repo / "app.js").read_text(), "user edit\n")
        self.git("add", "app.js")
        self.git("commit", "-qm", "head moved")
        command("apply", "--digest", digest, code=2)

    def test_staged_rename_cannot_be_bypassed_by_restoring_its_source(self):
        _, command = self.build()
        digest = command("review-change")["digest"]
        self.git("mv", "app.js", "renamed.js")
        (self.repo / "app.js").write_bytes((self.repo / "renamed.js").read_bytes())
        self.assertIn("Staged change overlaps", command("apply", "--digest", digest, code=2))
        self.assertEqual((self.repo / "app.js").read_text(), "export const loading = true;\n")

    def test_worktree_content_filter_cannot_rewrite_reviewed_bytes(self):
        _, command = self.build()
        digest = command("review-change")["digest"]
        (self.repo / ".gitattributes").write_text("*.js filter=unspecified\n")
        self.git("config", "filter.unspecified.smudge", "sed s/false/true/")
        self.assertIn("Git conversion attribute filter", command("apply", "--digest", digest, code=2))
        self.assertEqual((self.repo / "app.js").read_text(), "export const loading = true;\n")

    def test_installer_shares_skill_and_cli_does_not_overwrite_unrelated_file(self):
        installation = self.cli("install", "--for", "both")
        self.assertEqual(len(installation["skills"]), 2)
        files = [Path(path) for path in installation["skills"]]
        self.assertEqual(files[0].read_bytes(), files[1].read_bytes())
        self.assertTrue(files[0].read_text().startswith("---\nname: vesper-relay\n"))
        executable = Path(installation["command"])
        result = subprocess.run([str(executable), "--help"], env=self.env, capture_output=True, check=True)
        self.assertIn(b"Vesper Relay", result.stdout)
        self.cli("install", "--for", "both")
        executable.write_text("unrelated\n")
        self.cli("install", "--for", "both", code=2)
        self.assertEqual(executable.read_text(), "unrelated\n")

    def test_maintenance_requires_frozen_baseline_regression(self):
        checkout = self.root / "maintenance-source"
        shutil.copytree(ROOT, checkout, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        for args in (("init", "-q"), ("add", "."), ("-c", "user.name=Test", "-c",
                     "user.email=test@example.com", "commit", "-qm", "maintenance fixture")):
            subprocess.check_call(["git", "-C", str(checkout), *args], env=self.env)
        project = Path(self.cli("maintain", checkout=checkout)["project"])
        command = lambda *args, **kwargs: self.cli("--project", project, *args, **kwargs)
        for name in ("product", "design", "architecture", "decisions"):
            (project / "plan" / f"{name}.md").write_text("Maintenance request.\n")
        contract = {"title": "Improve toolkit", "delivery": "Git patch",
                    "requirements": [{"id": "R1", "description": "Verified change", "checks": ["G1"]}],
                    "checks": [{"id": "G1", "script": "vesper_regression.py"}],
                    "jobs": [{"id": "J1", "role": "maintainer", "goal": "Fix the issue",
                              "paths": ["README.md"], "depends_on": [], "checks": ["G1"]}]}
        target = project / "plan" / "contract.json"
        target.write_text(json.dumps(contract))
        self.assertIn("requires the VESPER_REGRESSION", command("review", code=2))
        for item in (contract["requirements"][0], contract["jobs"][0]):
            item["checks"] = ["VESPER_REGRESSION"]
        contract["checks"][0]["id"] = "VESPER_REGRESSION"
        target.write_text(json.dumps(contract))
        (project / "checks" / "vesper_regression.py").write_text("pass\n")
        self.assertIn("regression script changed", command("review", code=2))
        intake = project / "plan" / "intake.json"
        intake.write_text(json.dumps({**json.loads(intake.read_text()), "mode": "bug"}))
        self.assertIn("Managed intake metadata changed", command("review", code=2))

    def test_repeated_verified_failures_propose_and_promote_scoped_guidance(self):
        first, _ = self.build()
        self.assertEqual(self.cli("learn")["signals"]["reproduce-first"], 1)
        self.cli("--project", first, "learn")
        result = self.cli("--project", first, "learn")
        self.assertEqual(result["signals"]["reproduce-first"], 1)
        self.assertEqual(result["proposals"], [])
        second, _ = self.build()
        result = self.cli("--project", second, "learn")
        self.assertEqual(result["proposals"], ["reproduce-first"])
        result = self.cli("learn", "--promote", "reproduce-first")
        self.assertIn("reproduce-first", result["active"])
        result = self.cli("start", "--mode", "bug", "--idea", "Another bug")
        self.assertIn("reproduce-first", result["guidance"])
        result = self.cli("start", "--mode", "design", "--idea", "New colors")
        self.assertNotIn("reproduce-first", result["guidance"])


if __name__ == "__main__":
    unittest.main()
