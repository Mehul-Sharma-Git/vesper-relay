"""Personal and project config files, precedence and `vesper config show` (P1-T7)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.config import DEFAULTS, LEVELS, load_config, parse_flag, personal_path
from builder.contracts import BuilderError

PERSONAL = """\
[brains.strong]
use = "claude-code"
model = "opus"
effort = "high"

[brains.fast]
use = "claude-code"
model = "sonnet"
effort = "medium"

[brains.reviewer]
use = "claude-code"     # the owner sets "codex" here; one AI is enough by default
model = "opus"

[roles]
planner = "strong"
designer = "strong"
technical-lead = "strong"
frontend = "fast"
backend = "fast"
qa = "strong"
reviewer = "reviewer"

[sandbox]
backend = "docker"      # docker | podman | none

[limits]
reserve_percent = 25
review_timeout = 300
review_max_turns = 30
"""

PROJECT = """\
[stack]
frontend = "vite-react"
backend = "go"

[hosting]
api = "render"

[checks]
extra = ["lint", "typecheck"]
"""


class ConfigTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.personal = self.root / "config.toml"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.project = self.repo / "vesper.toml"

    def load(self, personal=None, project=None, flags=()):
        if personal is not None:
            self.personal.write_text(personal)
        if project is not None:
            self.project.write_text(project)
        return load_config(personal=self.personal, project=self.project, flags=flags)

    def refused(self, text, **kwargs):
        with self.assertRaises(BuilderError) as caught:
            self.load(**kwargs)
        self.assertIn(text, str(caught.exception))
        return str(caught.exception)

    # Parsing

    def test_parses_the_example_personal_and_project_files(self):
        values = self.load(PERSONAL, PROJECT)["values"]
        self.assertEqual(values["brains.strong.use"], {"value": "claude-code", "source": "personal",
                                                       "file": str(self.personal)})
        self.assertEqual(values["brains.reviewer.model"]["value"], "opus")
        self.assertEqual(values["roles.technical-lead"]["value"], "strong")
        self.assertEqual(values["limits.review_timeout"]["value"], 300)
        self.assertEqual(values["stack.frontend"], {"value": "vite-react", "source": "project",
                                                    "file": str(self.project)})
        self.assertEqual(values["checks.extra"]["value"], ["lint", "typecheck"])

    def test_invalid_toml_names_the_file(self):
        message = self.refused("Invalid TOML", personal="[limits\nreview_timeout = 3\n")
        self.assertIn(str(self.personal), message)

    def test_unknown_section_is_refused(self):
        self.refused("Unknown config section [colors]", personal="[colors]\ntheme = 'dark'\n")
        self.refused("must be a [section] table", personal="sandbox = 'docker'\n")

    def test_each_section_lives_at_one_level(self):
        self.refused("[stack] belongs in the project file vesper.toml",
                     personal="[stack]\nfrontend = 'vite'\n")
        self.refused("[brains] belongs in the personal file", personal="",
                     project="[brains.strong]\nuse = 'codex'\n")
        self.assertEqual(set(LEVELS.values()), {"personal", "project"})
        for section in ("brains", "roles", "sandbox", "limits", "defaults", "tools", "paths"):
            self.assertEqual(LEVELS[section], "personal")
        for section in ("stack", "hosting", "checks"):
            self.assertEqual(LEVELS[section], "project")

    def test_known_values_are_validated(self):
        self.refused("sandbox.backend must be one of docker, podman, none",
                     personal="[sandbox]\nbackend = 'vm'\n")
        self.refused("limits.reserve_percent must be a whole number from 0 to 100",
                     personal="[limits]\nreserve_percent = 101\n")
        self.refused("Review timeout must be 1 to 1800 seconds", personal="[limits]\nreview_timeout = 0\n")
        self.refused("Review max turns must be 1 to 100", personal="[limits]\nreview_max_turns = true\n")
        self.refused("roles.qa names brain 'strong', which is not defined under [brains]",
                     personal="[roles]\nqa = 'strong'\n")
        self.refused("brains.fast.use must name an adapter", personal="[brains.fast]\nmodel = 'sonnet'\n")

    # Precedence

    def test_each_key_takes_flag_then_its_file_then_default(self):
        flags = [parse_flag("limits.review_timeout=600"), parse_flag("stack.frontend=astro")]
        values = self.load(PERSONAL, PROJECT, flags)["values"]
        self.assertEqual(values["limits.review_timeout"], {"value": 600, "source": "flag"})
        self.assertEqual(values["limits.review_max_turns"]["source"], "personal")
        self.assertEqual(values["stack.frontend"], {"value": "astro", "source": "flag"})
        self.assertEqual(values["stack.backend"]["source"], "project")
        self.assertEqual(values["sandbox.backend"]["source"], "personal")

        values = self.load("[limits]\nreview_max_turns = 40\n", "[stack]\nbackend = 'go'\n")["values"]
        self.assertEqual(values["limits.review_max_turns"]["source"], "personal")
        self.assertEqual(values["limits.review_timeout"], {"value": 180, "source": "default"})
        self.assertEqual(values["sandbox.backend"], {"value": "docker", "source": "default"})

    def test_a_flag_overrides_one_leaf_of_a_brain(self):
        values = self.load(PERSONAL, flags=[parse_flag("brains.reviewer.use=codex")])["values"]
        self.assertEqual(values["brains.reviewer.use"], {"value": "codex", "source": "flag"})
        self.assertEqual(values["brains.reviewer.model"]["source"], "personal")

    def test_flags_are_checked_like_files(self):
        self.assertEqual(parse_flag("limits.reserve_percent=30"), ("limits.reserve_percent", 30))
        self.assertEqual(parse_flag("sandbox.backend=podman"), ("sandbox.backend", "podman"))
        self.assertEqual(parse_flag("checks.extra=['lint']"), ("checks.extra", ["lint"]))
        for bad in ("limits", "=3", "limits.review_timeout", "colors.theme=dark"):
            with self.subTest(flag=bad), self.assertRaises(BuilderError):
                parse_flag(bad)
        self.refused("limits.reserve_percent must be", flags=[parse_flag("limits.reserve_percent=-1")])

    # Secrets

    def test_secret_like_keys_are_refused_everywhere(self):
        for text in ("[brains.strong]\nuse = 'codex'\napi_key = 'x'\n",
                     "[brains.strong]\nuse = 'codex'\napikey = 'x'\n",
                     "[tools]\ngithub_token = 'x'\n",
                     "[tools.gh]\nClient-Secret = 'x'\n",
                     "[paths]\npassword_file = '/tmp/p'\n",
                     "[defaults]\ncredentials = 'x'\n",
                     "[tools]\nlist = [{name = 'a', token = 'x'}]\n",
                     "[tools.keys]\nfirst = 'x'\n",
                     "[tools]\napi_key1 = 'x'\n",
                     "[paths]\nawsAccessKeyId = 'x'\n",
                     "[tools]\nAPIKEYID = 'x'\n",
                     "[tools]\nopenaikey2 = 'x'\n",
                     "[tools]\ngithubToken2 = 'x'\n",
                     "[defaults]\nDB_PASSWD = 'x'\n"):
            with self.subTest(text=text):
                message = self.refused("looks like a secret", personal=text)
                self.assertIn("Keychain", message)
                self.assertIn("secrets.env", message)
        self.refused("looks like a secret", project="[hosting]\nrender_api_key = 'x'\n")
        for flag in ("tools.npm_token=abc", 'tools.gh={token="x"}', 'tools.list=[{api_key="x"}]',
                     'tools.gh={auth={password="x"}}'):
            with self.subTest(flag=flag), self.assertRaises(BuilderError) as caught:
                parse_flag(flag)
            self.assertIn("looks like a secret", str(caught.exception))

    def test_key_names_with_dots_or_empty_are_refused(self):
        for text in ('[tools]\n"github_token.value" = "ghp_x"\n',
                     '[tools]\nlist = [{"api_key.v" = "x"}]\n',
                     '[tools]\n"a.b" = 1\n[tools.a]\nb = 2\n',
                     '[tools]\n"" = 1\n'):
            with self.subTest(text=text):
                self.refused("may not contain '.' or be empty", personal=text)
        with self.assertRaises(BuilderError) as caught:
            parse_flag('tools.gh={"token.v"="x"}')
        self.assertIn("may not contain '.' or be empty", str(caught.exception))

    def test_a_table_flag_merges_leaf_by_leaf(self):
        values = self.load(PERSONAL, flags=[parse_flag('brains.reviewer={use="codex"}')])["values"]
        self.assertEqual(values["brains.reviewer.use"], {"value": "codex", "source": "flag"})
        self.assertEqual(values["brains.reviewer.model"]["source"], "personal")
        self.assertNotIn("brains.reviewer", values)

    def test_a_flag_value_is_one_line(self):
        with self.assertRaises(BuilderError):
            parse_flag("limits.review_timeout=1\nlimits.review_max_turns=2")

    def test_ordinary_words_containing_key_letters_are_allowed(self):
        values = self.load("[defaults]\nkeyboard_layout = 'us'\nkeystrokeDelay = 5\n"
                           "[paths]\nkeystore_dir = '/k'\n")["values"]
        self.assertEqual(values["defaults.keyboard_layout"]["value"], "us")
        self.assertEqual(values["paths.keystore_dir"]["value"], "/k")

    # Defaults

    def test_defaults_when_files_are_absent(self):
        config = load_config(personal=self.root / "none.toml", project=self.root / "nope" / "vesper.toml")
        self.assertEqual(config["files"]["personal"], {"path": str(self.root / "none.toml"), "found": False})
        self.assertEqual(config["files"]["project"]["found"], False)
        self.assertEqual(config["values"], {key: {"value": value, "source": "default"}
                                            for key, value in DEFAULTS.items()})
        self.assertEqual(DEFAULTS["limits.review_timeout"], 180)
        self.assertEqual(DEFAULTS["limits.review_max_turns"], 20)
        self.assertEqual(DEFAULTS["sandbox.backend"], "docker")
        self.assertEqual(DEFAULTS["limits.reserve_percent"], 25)

    def test_personal_path_resolution(self):
        home = self.root / "home"
        self.assertEqual(personal_path(None, {"HOME": str(home)}),
                         (home / ".config" / "vesper" / "config.toml", False))
        self.assertEqual(personal_path(None, {"HOME": str(home), "VESPER_CONFIG": "/etc/v.toml"}),
                         (Path("/etc/v.toml"), True))
        self.assertEqual(personal_path(Path("/x.toml"), {"VESPER_CONFIG": "/etc/v.toml"}),
                         (Path("/x.toml"), True))

    def test_an_explicit_personal_file_must_exist(self):
        with self.assertRaises(BuilderError) as caught:
            load_config(personal=self.root / "missing.toml", project=self.project, explicit=True)
        self.assertIn("Config file not found", str(caught.exception))


class ConfigShowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items() if k != "VESPER_CONFIG"}
        self.env.update(HOME=str(self.home), VESPER_STATE_DIR=str(self.root / "state"))

    def show(self, *args, code=0, env=None):
        p = subprocess.run([sys.executable, "-B", str(ROOT / "vesper.py"), "config", "show", *args],
                           cwd=self.repo, env=env or self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, code, p.stdout + p.stderr)
        return json.loads(p.stdout) if code == 0 else p.stderr

    def test_show_with_no_files_prints_defaults(self):
        result = self.show()
        self.assertEqual(result["files"]["personal"],
                         {"path": str(self.home / ".config" / "vesper" / "config.toml"), "found": False})
        self.assertEqual(result["files"]["project"],
                         {"path": str((self.repo / "vesper.toml").resolve()), "found": False})
        self.assertEqual({v["source"] for v in result["values"].values()}, {"default"})

    def test_show_reports_where_each_value_came_from(self):
        personal = self.home / ".config" / "vesper" / "config.toml"
        personal.parent.mkdir(parents=True)
        personal.write_text(PERSONAL)
        (self.repo / "vesper.toml").write_text(PROJECT)
        result = self.show("--set", "limits.review_timeout=900")
        values = result["values"]
        self.assertEqual(values["limits.review_timeout"], {"value": 900, "source": "flag"})
        self.assertEqual(values["limits.reserve_percent"],
                         {"value": 25, "source": "personal", "file": str(personal)})
        self.assertEqual(values["stack.backend"]["source"], "project")
        self.assertTrue(result["files"]["personal"]["found"])
        self.assertTrue(result["files"]["project"]["found"])

    def test_config_flag_and_env_choose_the_personal_file(self):
        chosen = self.root / "chosen.toml"
        chosen.write_text("[sandbox]\nbackend = 'podman'\n")
        other = self.root / "other.toml"
        other.write_text("[sandbox]\nbackend = 'none'\n")
        env = dict(self.env, VESPER_CONFIG=str(other))
        self.assertEqual(self.show(env=env)["values"]["sandbox.backend"]["value"], "none")
        result = self.show("--config", chosen, env=env)
        self.assertEqual(result["values"]["sandbox.backend"],
                         {"value": "podman", "source": "personal", "file": str(chosen)})
        self.assertIn("Config file not found", self.show("--config", self.root / "missing.toml", code=2))

    def test_show_uses_repo_option_for_the_project_file(self):
        other = self.root / "other-repo"
        other.mkdir()
        (other / "vesper.toml").write_text("[hosting]\nsite = 'vercel'\n")
        result = self.show("--repo", other)
        self.assertEqual(result["values"]["hosting.site"]["source"], "project")

    def test_show_refuses_a_secret_in_the_project_file(self):
        (self.repo / "vesper.toml").write_text("[hosting]\nvercel_token = 'abc'\n")
        self.assertIn("looks like a secret", self.show(code=2))


if __name__ == "__main__":
    unittest.main()
