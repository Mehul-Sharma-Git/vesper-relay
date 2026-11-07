"""Reproduce and fix a real HTTP filter regression in a disposable Git checkout."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def replay(destination):
    destination.mkdir(parents=True, exist_ok=False)
    repo = destination / "stockroom-site"
    shutil.copytree(ROOT / "examples" / "stockroom-app", repo)
    env = dict(os.environ, VESPER_STATE_DIR=str(destination / "vesper-state"))
    server = repo / "server.py"
    correct = server.read_text()
    original = "if key in filters:"
    assert original in correct
    broken = correct.replace(original, 'if key in filters and key != "status":', 1)
    server.write_text(broken)
    notes = repo / "notes.md"
    notes.write_text("Committed notes.\n")

    def call(command, *, code=0):
        result = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True)
        if result.returncode != code:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout

    call(["git", "init", "-q"])
    call(["git", "add", "."])
    call(["git", "-c", "user.name=Vesper Pilot", "-c", "user.email=pilot@example.com",
          "commit", "-qm", "Stockroom with a broken status filter"])
    notes.write_text("Unrelated local edits.\n")
    cli = [sys.executable, "-B", str(ROOT / "vesper.py")]

    def vesper(*args, code=0):
        return json.loads(call([*cli, *args], code=code))

    started = vesper("start", "--mode", "bug", "--idea", "Bought items appear under Needed.")
    project = Path(started["project"])

    def run(*args, **kwargs):
        return vesper("--project", str(project), *args, **kwargs)

    plan = project / "plan"
    for name, content in {
        "product": "Bought items should disappear from the Needed API filter.",
        "design": "Preserve the browser's existing room and status filter UI.",
        "architecture": "Restore the SQLite WHERE condition for status in the HTTP API.",
        "decisions": "Limit the fix to server.py. Verify the status filter and restart.",
    }.items():
        (plan / f"{name}.md").write_text(content + "\n")
    shutil.copy2(ROOT / "examples" / "stockroom" / "checks" / "api.py", project / "checks" / "api.py")
    (plan / "contract.json").write_text(json.dumps({
        "title": "Fix Stockroom status filter", "delivery": "Reviewed Git patch",
        "requirements": [{"id": "R1", "description": "Needed excludes bought items", "checks": ["G_API"]}],
        "checks": [{"id": "G_API", "script": "api.py"}],
        "jobs": [{"id": "J_API", "role": "backend engineer", "goal": "Restore status filtering",
                  "paths": ["server.py"], "depends_on": [], "checks": ["G_API"]}],
    }))
    run("approve", "--digest", run("review")["digest"])
    initial = run("prepare")
    rejected = run("submit", initial["id"], code=1)
    assert rejected["checks"][0]["exit_code"] != 0
    fix = run("prepare")
    (Path(fix["workspace"]) / "server.py").write_text(correct)
    assert run("submit", fix["id"])["outcome"] == "accepted"
    review = run("review-change")
    assert review["files"] == ["server.py"]
    assert server.read_text() == broken
    run("apply", "--digest", review["digest"])
    assert server.read_text() == correct and notes.read_text() == "Unrelated local edits.\n"
    assert call(["git", "diff", "--cached", "--name-only"]) == ""
    assert vesper("learn")["signals"] == {"reproduce-first": 1}
    print("Repo pilot passed: HTTP bug reproduced, verified one-file patch applied, unrelated edit preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New local directory for the pilot")
    replay(parser.parse_args().destination.resolve())
