#!/usr/bin/env python3
"""Test-only stand-in for a human confirmer.

Vesper uses it only when VESPER_TEST_CONFIRMER names this file, which `vesper doctor`
warns about: it lets tests and replays run protected actions without a person. It
receives the action as its argument and the full approval sheet on standard input,
saves the sheet in VESPER_TEST_SHEETS when that names a folder, and answers with
VESPER_TEST_CONFIRM_ANSWER ("yes" by default; anything else refuses).
"""
import os
from pathlib import Path
import sys
import time

action = sys.argv[1]
sheet = sys.stdin.read()
folder = os.environ.get("VESPER_TEST_SHEETS")
if folder:
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / f"{time.time_ns()}-{action}.txt").write_text(sheet, encoding="utf-8")
raise SystemExit(0 if os.environ.get("VESPER_TEST_CONFIRM_ANSWER", "yes") == "yes" else 1)
