import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_vesper


def verdict(preview, decision="approve"):
    findings = [] if decision == "approve" else [
        {"severity": "blocking", "path": "app.js", "evidence": "The fallback skips a required branch.",
         "recommendation": "Handle the failed-save branch explicitly."}
    ]
    return {"attempt_id": preview["id"], "base_digest": preview["review"]["base_digest"],
            "candidate_digest": preview["review"]["candidate_digest"], "verdict": decision,
            "summary": "Inspected the committed baseline, candidate and gate evidence.",
            "evidence": {key: "Checked independently against the diff and fixtures."
                         for key in ("requirements", "correctness", "scope", "tests", "maintainability", "security")},
            "findings": findings}


class TeamTests(unittest.TestCase):
    setUp = test_vesper.VesperTests.setUp
    cli = test_vesper.VesperTests.cli
    git = test_vesper.VesperTests.git

    def plan(self, role="frontend", skills=None):
        project = Path(self.cli("start", "--mode", "bug", "--idea", "Spinner never stops")["project"])

        def command(*args, **kwargs):
            return self.cli("--project", project, *args, **kwargs)

        for name in ("product", "design", "architecture", "decisions"):
            (project / "plan" / f"{name}.md").write_text("Spinner stops on failure.\n")
        contract = {
            "team": 1, "title": "Fix spinner", "delivery": "Git patch",
            "requirements": [{"id": "R1", "description": "Spinner stops on failure", "checks": ["G1"]}],
            "checks": [{"id": "G1", "script": "gate.py"}],
            "jobs": [{"id": "J1", "role": role, "goal": "Fix spinner", "paths": ["app.js"],
                      "depends_on": [], "checks": ["G1"], "skills": skills or []}],
        }
        (project / "plan" / "contract.json").write_text(json.dumps(contract))
        (project / "checks" / "gate.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "assert (Path(sys.argv[1]) / 'app.js').read_text() == 'export const loading = false;\\n'\n")
        return project, command

    def approve(self, command):
        command("approve", "--digest", command("review")["digest"])

    def submit(self, command):
        attempt = command("prepare")
        (Path(attempt["workspace"]) / "app.js").write_text("export const loading = false;\n")
        return attempt, command("submit", attempt["id"])

    def write_report(self, data):
        report = self.root / "report.json"
        report.write_text(json.dumps(data))
        return report

    def test_rejects_nonwriting_role_and_incompatible_skill(self):
        _, command = self.plan("designer")
        self.assertIn("writing", command("review", code=2))
        _, command = self.plan("frontend", ["postgres"])
        self.assertIn("postgres", command("review", code=2))
        project, command = self.plan()
        path = project / "plan" / "contract.json"
        contract = json.loads(path.read_text())
        del contract["team"]
        path.write_text(json.dumps(contract))
        self.assertIn("requires a team contract", command("review", code=2))

    def test_review_gate_binds_verdict_and_promotes_the_tested_copy(self):
        _, command = self.plan("frontend", ["react"])
        self.approve(command)
        attempt, preview = self.submit(command)
        brief = Path(attempt["brief"]).read_text()
        self.assertIn("frontend-delivery", brief)
        self.assertIn("react", brief)
        self.assertNotIn("## Skill: postgres", brief)
        self.assertEqual(command("status")["status"], "awaiting_review")
        self.assertEqual(command("status")["completed"], [])
        command("review-change", code=2)
        invalid = {**verdict(preview), "candidate_digest": "wrong"}
        command("review-candidate", "--report", self.write_report(verdict(preview)), code=2)
        command("review-candidate", "--report", self.write_report(invalid), "--attest-independent", code=2)
        (Path(attempt["workspace"]) / "app.js").write_text("unreviewed\n")
        command("review-candidate", "--report", self.write_report(verdict(preview)), "--attest-independent")
        result = command("status")
        self.assertEqual(result["status"], "complete")
        self.assertEqual((Path(result["snapshot"]) / "app.js").read_text(), "export const loading = false;\n")

    def test_blocking_verdict_does_not_accept_the_candidate(self):
        _, command = self.plan()
        self.approve(command)
        _, preview = self.submit(command)
        result = command("review-candidate", "--report",
                         self.write_report(verdict(preview, "request_changes")), "--attest-independent", code=1)
        self.assertEqual(result["outcome"], "rejected")
        self.assertEqual(command("status")["completed"], [])
        attempt = command("prepare")
        self.assertIn("failed-save branch", Path(attempt["brief"]).read_text())

    def test_visual_work_requires_distinct_design_directions_and_design_review(self):
        project, command = self.plan()
        path = project / "plan" / "contract.json"
        contract = json.loads(path.read_text())
        path.write_text(json.dumps(dict(contract, design_required=True)))
        self.assertIn("design.json", command("review", code=2))
        design = {
            "audience": "Two warehouse operators", "primary_task": "Find a pending shipment",
            "representative_content": "Order 42 and a failed save",
            "chosen": "Ledger", "reason": "Promotes quick comparison",
            "avoid": "Interchangeable dashboard cards", "narrow": "Labeled rows",
            "wide": "A compact table", "focus": "Return to the failed row",
            "motion": "Static", "browser_evidence": "Keyboard-only retry at 320px",
            "states": {"error": "Retry next to the affected row"},
            "directions": [
                {"name": "Ledger", "composition": "Grouped rows", "benefit": "Scan", "tradeoff": "Dense"},
                {"name": "Queue", "composition": "Grouped rows", "benefit": "Focus", "tradeoff": "Tall"},
            ],
        }
        brief = project / "plan" / "design.json"
        brief.write_text(json.dumps(design))
        self.assertIn("distinct", command("review", code=2))
        design["directions"][1]["composition"] = "A single ordered timeline"
        brief.write_text(json.dumps(design))
        self.approve(command)
        _, preview = self.submit(command)
        data = verdict(preview)
        command("review-candidate", "--report", self.write_report(data), "--attest-independent", code=2)
        data["evidence"]["design"] = "Compared the chosen composition and recorded browser evidence."
        command("review-candidate", "--report", self.write_report(data), "--attest-independent")

    def test_reviewer_runs_in_separate_launcher_and_never_gets_writer_workspace(self):
        _, command = self.plan()
        self.approve(command)
        script = self.root / "launcher.py"
        script.write_text("#!" + sys.executable + "\n" + """
import json
from pathlib import Path
import subprocess
import sys

operation = sys.argv[1]
if operation == 'worker':
    Path('app.js').write_text('export const loading = false;\\n')
elif operation == 'check':
    raise SystemExit(subprocess.call([sys.executable, '-I', '-B', *sys.argv[2:]]))
elif operation == 'reviewer':
    assert not Path('app.js').exists()
    assert 'loading = false' in Path('candidate/app.js').read_text()
    assert 'loading = true' in Path('base/app.js').read_text()
    packet = json.loads(Path('review.json').read_text())
    report = {key: packet[key] for key in ('attempt_id', 'base_digest', 'candidate_digest')}
    report.update(verdict='approve', summary='Independently verified the candidate.', findings=[],
                  evidence={k:'Read the diff and verification result.'
                            for k in ('requirements','correctness','scope','tests','maintainability','security')})
    print(json.dumps(report))
else:
    raise SystemExit(3)
""")
        script.chmod(0o700)
        result = command("run", "--provider", "codex", "--launcher", script)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["attempts"][-1]["review"]["verdict"], "approve")

    def test_engineer_can_draft_a_read_only_preapproval_handoff(self):
        project, command = self.plan()
        launcher = self.root / "consult"
        launcher.write_text(f"#!{sys.executable}\n" + '''from pathlib import Path
import sys

assert sys.argv[1:] == ["consult", "codex"]
prompt = sys.stdin.read()
assert "read-only consultation" in prompt and "backend-delivery" in prompt
assert "draft the error contract" in prompt
assert Path("app.js").is_file()
print("Use a stable conflict code and document when the frontend may retry.")
''')
        launcher.chmod(0o700)
        result = command("consult", "--role", "backend", "--task", "draft the error contract",
                         "--provider", "codex", "--launcher", launcher)
        self.assertIn("stable conflict code", result["report"])
        self.assertEqual((project / "seed" / "app.js").read_text(), "export const loading = true;\n")


class RepairTests(unittest.TestCase):
    git = test_vesper.VesperTests.git
    setUp = test_vesper.VesperTests.setUp
    cli = test_vesper.VesperTests.cli

    def source(self):
        import shutil
        source = self.root / "installed-vesper"
        shutil.copytree(test_vesper.ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        shutil.rmtree(source / "tests")
        (source / "tests").mkdir()
        (source / "tests" / "test_baseline.py").write_text(
            "import unittest\nclass Baseline(unittest.TestCase):\n"
            " def test_smoke(self): self.assertTrue(True)\n")
        subprocess.run(["git", "-C", str(source), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(source), "-c", "user.name=Test", "-c",
                        "user.email=test@example.com", "commit", "-qm", "repair fixture"], check=True)
        return source

    def test_repair_requires_reproduction_and_commits_reviewed_bytes_to_a_branch(self):
        source = self.source()
        probe = self.root / "repro.py"
        probe.write_text("from pathlib import Path\nimport sys\n"
                         "assert 'REPAIR_OK = True' in (Path(sys.argv[1]) / 'vesper.py').read_text()\n")
        result = self.cli("repair", "--idea", "Repair a reproducible coordinator defect",
                          "--repro", probe, "--path", "vesper.py", checkout=source)
        project = Path(result["project"])

        def cmd(*args, **kwargs):
            return self.cli("--project", project, *args, checkout=source, **kwargs)

        digest = cmd("review")["digest"]
        self.assertIn("reproduc", cmd("approve", "--digest", digest, code=2).lower())
        cmd("repair-reproduce", "--trust-host")
        cmd("approve", "--digest", digest)
        attempt = cmd("prepare")
        target = Path(attempt["workspace"]) / "vesper.py"
        target.write_text(target.read_text() + "\nREPAIR_OK = True\n")
        cmd("submit", attempt["id"], code=2)
        report = self.root / "verdict.json"
        launcher = self.root / "reviewer.py"
        launcher.write_text("#!" + sys.executable + "\n"
                            "import subprocess, sys\nfrom pathlib import Path\n"
                            "if sys.argv[1] == 'check':\n"
                            "    raise SystemExit(subprocess.call([sys.executable, '-I', '-B', *sys.argv[2:]]))\n"
                            "assert sys.argv[1] == 'reviewer'\n"
                            f"print(Path({str(report)!r}).read_text())\n")
        launcher.chmod(0o700)
        preview = cmd("submit", attempt["id"], "--launcher", launcher)
        report.write_text(json.dumps(verdict(preview)))
        cmd("review-candidate", "--report", report, "--attest-independent", code=2)
        cmd("review-candidate", "--provider", "codex", "--launcher", launcher)
        patch = cmd("review-change")
        fixed = cmd("repair-commit", "--digest", patch["digest"])
        self.assertTrue(fixed["branch"].startswith("vesper/repair/"))
        self.assertEqual(cmd("repair-commit", "--digest", patch["digest"])["commit"], fixed["commit"])
        self.assertNotIn("REPAIR_OK = True", (source / "vesper.py").read_text())
        self.assertIn(b"REPAIR_OK = True", subprocess.check_output(
            ["git", "-C", str(source), "show", fixed["commit"] + ":vesper.py"]))
        self.assertEqual(subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"]), b"")

    def test_repair_run_reproduces_reviews_commits_and_records_learning(self):
        source = self.source()
        probe = self.root / "repro.py"
        probe.write_text("from pathlib import Path\nimport sys\n"
                         "assert 'REPAIR_OK = True' in (Path(sys.argv[1]) / 'vesper.py').read_text()\n")
        project = self.cli("repair", "--idea", "Repair a coordinator defect", "--repro", probe,
                           "--path", "vesper.py", checkout=source)["project"]

        def cmd(*args, **kwargs):
            return self.cli("--project", project, *args, checkout=source, **kwargs)

        launcher = self.root / "launcher"
        launcher.write_text(f"#!{sys.executable}\n" + '''import json
from pathlib import Path
import subprocess
import sys

operation = sys.argv[1]
if operation == "check":
    raise SystemExit(subprocess.call([sys.executable, "-I", "-B", *sys.argv[2:]]))
if operation == "worker":
    source = Path("vesper.py")
    source.write_text(source.read_text() + "\\nREPAIR_OK = True\\n")
elif operation == "reviewer":
    assert sys.argv[2] == "claude"
    assert "REPAIR_OK = True" not in Path("base/vesper.py").read_text()
    assert "REPAIR_OK = True" in Path("candidate/vesper.py").read_text()
    packet = json.loads(Path("review.json").read_text())
    report = {key: packet[key] for key in ("attempt_id", "base_digest", "candidate_digest")}
    report.update(verdict="approve", summary="Verified fixture repair.", findings=[],
                  evidence={area: "Checked against the scoped fixture patch."
                            for area in ("requirements", "correctness", "scope", "tests", "maintainability", "security")})
    print(json.dumps(report))
else:
    raise SystemExit(3)
''')
        launcher.chmod(0o700)
        result = cmd("repair-run", "--digest", cmd("review")["digest"], "--provider", "codex",
                     "--reviewer-provider", "claude", "--launcher", launcher, "--commit")
        self.assertTrue(result["branch"].startswith("vesper/repair/"))
        history = self.cli("learn", checkout=source)
        self.assertIn(result["commit"], json.dumps(history["repairs"]))
        self.assertNotIn("REPAIR_OK = True", (source / "vesper.py").read_text())
