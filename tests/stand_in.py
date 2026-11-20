"""Tests run protected actions through the test-only stand-in confirmer (P2-T2).

Importing this module sets VESPER_TEST_CONFIRMER for the test process and every
subprocess it starts, unless a test chose another value."""
import os
from pathlib import Path

STAND_IN = Path(__file__).resolve().parents[1] / "examples" / "stand_in_confirmer.py"
os.environ.setdefault("VESPER_TEST_CONFIRMER", str(STAND_IN))
