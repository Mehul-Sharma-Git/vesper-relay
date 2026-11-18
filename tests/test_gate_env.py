"""Gate environment pass-through (P1-T4)."""
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.brains import CREDENTIALS

import test_builder

ENV_GATE = ("import json, os, sys\n"
            "from pathlib import Path\n"
            "print('GATE_ENV ' + json.dumps({name: os.environ.get(name) for name in\n"
            "    ('VESPER_TEST_DECLARED', 'VESPER_TEST_UNDECLARED', 'HOME')}))\n"
            "assert (Path(sys.argv[1]) / 'first.txt').read_text() == 'one'\n")


class GateEnvTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    write_plan = test_builder.BuilderTests.write_plan
    args = test_builder.BuilderTests.args
    command = test_builder.BuilderTests.command
    approve = test_builder.BuilderTests.approve
    candidate = test_builder.BuilderTests.candidate

    def host_env(self):
        return {**os.environ, "VESPER_TEST_DECLARED": "chromium-here",
                "VESPER_TEST_UNDECLARED": "should-not-leak", "HOME": "/host/home"}

    def gate_output(self, declared):
        (self.project / "checks" / "first.py").write_text(ENV_GATE)
        if declared is not None:
            self.plan["gate_env"] = declared
        self.write_plan()
        self.approve()
        attempt, workspace = self.candidate("J1")
        (workspace / "first.txt").write_text("one")
        result = self.command("submit", attempt["id"], env=self.host_env())
        log = (self.project / result["checks"][0]["log"]).read_text()
        line = next(item for item in log.splitlines() if item.startswith("GATE_ENV "))
        return json.loads(line[len("GATE_ENV "):])

    def test_declared_variable_reaches_the_gate_and_undeclared_stays_out(self):
        seen = self.gate_output(["VESPER_TEST_DECLARED"])
        self.assertEqual(seen["VESPER_TEST_DECLARED"], "chromium-here")
        self.assertIsNone(seen["VESPER_TEST_UNDECLARED"])
        self.assertNotEqual(seen["HOME"], "/host/home")

    def test_without_gate_env_the_gate_sees_neither(self):
        seen = self.gate_output(None)
        self.assertIsNone(seen["VESPER_TEST_DECLARED"])
        self.assertIsNone(seen["VESPER_TEST_UNDECLARED"])

    def test_declared_name_missing_on_the_host_is_absent(self):
        env = {key: value for key, value in self.host_env().items() if key != "VESPER_TEST_DECLARED"}
        self.host_env = lambda: env
        seen = self.gate_output(["VESPER_TEST_DECLARED"])
        self.assertIsNone(seen["VESPER_TEST_DECLARED"])

    def test_credential_names_fail_review(self):
        credentials = sorted(CREDENTIALS)
        self.assertIn("ANTHROPIC_API_KEY", credentials)
        self.assertIn("CODEX_HOME", credentials)
        for name in [*credentials, "GITHUB_TOKEN", "db_password", "MY_SECRET", "AWS_CREDENTIALS",
                     "NPM_AUTH", "Stripe_Key"]:
            with self.subTest(name=name):
                self.plan["gate_env"] = ["PLAYWRIGHT_BROWSERS_PATH", name]
                self.write_plan()
                self.assertIn(f"gate_env must not pass credentials: {name}", self.command("review", code=2))

    def test_gate_env_cannot_replace_the_fixed_gate_environment(self):
        for name in ("PATH", "HOME", "TMPDIR", "LANG", "PYTHONDONTWRITEBYTECODE"):
            with self.subTest(name=name):
                self.plan["gate_env"] = [name]
                self.write_plan()
                self.assertIn(f"gate_env cannot replace {name}", self.command("review", code=2))

    def test_malformed_gate_env_fails_review(self):
        for value in ("PLAYWRIGHT_BROWSERS_PATH", ["A", "A"], ["1BAD"], ["BAD-NAME"], ["BAD=VALUE"],
                      [""], [3], {"A": "b"}, None):
            with self.subTest(value=value):
                self.plan["gate_env"] = value
                self.write_plan()
                self.assertIn("Invalid gate_env", self.command("review", code=2))

    def test_gate_env_is_part_of_the_digest(self):
        before = self.command("review")["digest"]
        self.plan["gate_env"] = ["PLAYWRIGHT_BROWSERS_PATH"]
        self.write_plan()
        self.assertNotEqual(self.command("review")["digest"], before)
        self.plan["gate_env"] = []
        self.write_plan()
        self.command("review")


if __name__ == "__main__":
    unittest.main()
