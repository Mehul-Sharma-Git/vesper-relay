"""A stable verifier for proposed changes to Vesper itself."""

MAINTENANCE_GATE = """\
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

candidate = Path(sys.argv[1])
baseline = Path(__file__).parent / "baseline_tests"
with tempfile.TemporaryDirectory() as temporary:
    workspace = Path(temporary) / "vesper"
    shutil.copytree(candidate, workspace)
    tests = workspace / "tests"
    if tests.exists():
        shutil.rmtree(tests)
    shutil.copytree(baseline, tests)
    discovery = (
        "import sys, unittest; "
        "sys.path.insert(0, '.'); "
        "unittest.main(module=None, argv=['unittest', 'discover', '-s', 'tests'])"
    )
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", discovery],
        cwd=workspace, check=True
    )
"""
