"""Repair contract validation with command gates (appendix-b finding 21)."""
from pathlib import Path
import sys
import unittest

import stand_in  # noqa: F401  (test-only environment: confirmer and state folder)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.contracts import BuilderError
from builder.repair import validate_repair

PACKET = {"paths": ["vesper.py"], "failure_id": "managed-run-discovery"}


def contract(*extra_checks):
    checks = [{"id": "VESPER_REPRO", "script": "vesper_repro.py"},
              {"id": "VESPER_REGRESSION", "script": "vesper_regression.py"}, *extra_checks]
    return {"team": 1, "checks": checks,
            "jobs": [{"id": "J1", "role": "backend", "review": "security", "paths": ["vesper.py"],
                      "checks": [item["id"] for item in checks]}]}


class RepairValidationTests(unittest.TestCase):
    def test_valid_repair_contract_passes(self):
        validate_repair(contract(), PACKET)

    def test_command_gate_alongside_the_repair_gates_does_not_crash(self):
        validate_repair(contract({"id": "LINT", "command": ["python3", "-m", "pyflakes"]}), PACKET)

    def test_command_gate_in_place_of_a_repair_gate_is_refused_cleanly(self):
        broken = contract()
        broken["checks"][0] = {"id": "VESPER_REPRO", "command": ["python3", "vesper_repro.py"]}
        with self.assertRaisesRegex(BuilderError, "Repair requires the independent reproducer"):
            validate_repair(broken, PACKET)


if __name__ == "__main__":
    unittest.main()
