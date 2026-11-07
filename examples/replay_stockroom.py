#!/usr/bin/env python3
"""Replay the packaged pilot through real local checks with supervised job outputs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def replay(destination):
    project = destination / "project"
    output = destination / "app"
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(EXAMPLES / "stockroom", project)
    (project / "seed").mkdir(exist_ok=True)

    def command(*args, exit_code=0):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "build_local.py"),
                                 "--project", str(project), *args], capture_output=True, text=True)
        if result.returncode != exit_code:
            raise RuntimeError(result.stderr or result.stdout)
        return json.loads(result.stdout)

    reviewed = command("review")
    command("approve", "--digest", reviewed["digest"])
    bad_backend = command("prepare")
    (Path(bad_backend["workspace"]) / "server.py").write_text("raise SystemExit('Injected startup fault')\n")
    result = command("submit", bad_backend["id"], exit_code=1)
    assert result["outcome"] == "rejected" and result["checks"][0]["id"] == "G_API"
    assert command("status")["completed"] == []

    backend = command("prepare")
    shutil.copy2(EXAMPLES / "stockroom-app" / "server.py", Path(backend["workspace"]) / "server.py")
    assert command("submit", backend["id"])["outcome"] == "accepted"
    assert command("status")["completed"] == ["J_API"]

    bad_frontend = command("prepare")
    (Path(bad_frontend["workspace"]) / "server.py").write_text("raise SystemExit('Outside frontend scope')\n")
    result = command("submit", bad_frontend["id"], exit_code=1)
    assert "outside job scope" in result["reason"]
    assert command("status")["completed"] == ["J_API"]

    frontend = command("prepare")
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copy2(EXAMPLES / "stockroom-app" / name, Path(frontend["workspace"]) / name)
    result = command("submit", frontend["id"])
    assert [item["id"] for item in result["checks"]] == ["G_API", "G_UI"]
    status = command("status")
    assert status["status"] == "complete" and status["completed"] == ["J_API", "J_UI"]
    command("export", str(output))
    print(f"Pilot passed: 2 accepted jobs, 2 injected faults rejected, final regression passed.\nApp: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="A new directory for the project and app")
    replay(parser.parse_args().destination.resolve())
