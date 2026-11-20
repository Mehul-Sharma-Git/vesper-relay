"""Test-only environment for the test process and every subprocess it starts.

Importing this module sets, unless a test chose another value:
- VESPER_TEST_CONFIRMER: protected actions go through the stand-in confirmer (P2-T2);
- VESPER_STATE_DIR: a temporary folder, removed when the tests end, so runs, the usage
  ledger, learning and repository confirmations never reach the owner's real state
  (found at P2-G: test calls in the real ledger distorted plan estimates)."""
import atexit
import os
from pathlib import Path
import shutil
import tempfile

STAND_IN = Path(__file__).resolve().parents[1] / "examples" / "stand_in_confirmer.py"
os.environ.setdefault("VESPER_TEST_CONFIRMER", str(STAND_IN))
if "VESPER_STATE_DIR" not in os.environ:
    STATE = tempfile.mkdtemp(prefix="vesper-test-state-")
    atexit.register(shutil.rmtree, STATE, ignore_errors=True)
    os.environ["VESPER_STATE_DIR"] = STATE
