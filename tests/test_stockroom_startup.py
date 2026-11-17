import importlib.util
from pathlib import Path
import tempfile
import unittest


CHECK = Path(__file__).resolve().parents[1] / "examples/stockroom/checks/api.py"
SERVER = CHECK.parents[2] / "stockroom-app/server.py"
spec = importlib.util.spec_from_file_location("stockroom_api_gate", CHECK)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class StockroomStartupTests(unittest.TestCase):
    def test_loopback_readiness_does_not_require_hostname_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server.py").write_text(
                "import runpy, socket\n"
                "def unexpected_lookup(*args):\n"
                "    raise AssertionError('loopback startup attempted reverse DNS')\n"
                "socket.getfqdn = socket.gethostbyaddr = unexpected_lookup\n"
                f"runpy.run_path({str(SERVER)!r}, run_name='__main__')\n"
            )
            with api.server(root, root / "inventory.sqlite3", timeout=3) as base:
                self.assertEqual(api.request(base, "/health"), (200, {"status": "ok"}))

    def test_bind_timeout_reports_child_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server.py").write_text(
                "import runpy, sys, time\n"
                "def delay(event, args):\n"
                "    if event == 'socket.bind':\n"
                "        print('injected bind delay', flush=True)\n"
                "        time.sleep(20)\n"
                "sys.addaudithook(delay)\n"
                f"runpy.run_path({str(SERVER)!r}, run_name='__main__')\n"
            )
            with self.assertRaises(AssertionError) as error:
                with api.server(root, root / "inventory.sqlite3", timeout=2):
                    self.fail("unexpected readiness")
            message = str(error.exception)
            self.assertIn("injected bind delay", message)
            self.assertIn("Last startup stage: http-binding.", message)
            self.assertIn("Exit status: unavailable (running)", message)

    def test_timeout_preserves_last_stage_and_recent_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server.py").write_text(
                "import sys, time\n"
                "print('STARTUP sqlite-initializing', file=sys.stderr, flush=True)\n"
                "print('STARTUP http-binding', file=sys.stderr, flush=True)\n"
                "print('old-output')\n"
                "for _ in range(25): print('progress')\n"
                "print('recent marker', flush=True)\n"
                "sys.stdout.write('incomplete line'); sys.stdout.flush()\n"
                "time.sleep(20)\n"
            )
            with self.assertRaises(AssertionError) as error:
                with api.server(root, root / "inventory.sqlite3", timeout=1):
                    self.fail("unexpected readiness")
            message = str(error.exception)
            self.assertIn("did not announce readiness", message)
            self.assertIn("Last startup stage: http-binding", message)
            self.assertIn("Exit status: unavailable (running)", message)
            self.assertIn("recent marker", message)
            self.assertIn("incomplete line", message)
            self.assertNotIn("old-output", message)
            self.assertLess(len(message), 2000)

    def test_exit_before_ready_preserves_status_and_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server.py").write_text(
                "import sys\n"
                "print('STARTUP sqlite-initializing', file=sys.stderr, flush=True)\n"
                "print('cannot open fixture', file=sys.stderr, flush=True)\n"
                "raise SystemExit(17)\n"
            )
            with self.assertRaisesRegex(AssertionError, "(?s)Exit status: 17.*cannot open fixture"):
                with api.server(root, root / "inventory.sqlite3", timeout=2):
                    self.fail("unexpected readiness")
