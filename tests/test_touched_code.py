"""P2-T8: a candidate review also sweeps the code a change touches (P2-G finding 53)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import stand_in  # noqa: F401  (test-only environment)
import test_rc1

from builder.review_gate import prompt, touched_code, write_diff

# The P2-G run-2b seed: a reachable injection two lines above the fix.
SERVER_BEFORE = '''import re


def get_lists(conn):
    return conn.execute("SELECT id FROM lists").fetchall()


def delete_list(conn, list_id, query):
    rev = query.get("rev", [None])[0]
    if rev is None or not re.fullmatch(r"[0-9]{1,9}", rev):
        raise ValueError("rev is required")
    row = conn.execute(f"SELECT inbox, rev FROM lists WHERE id = {list_id}").fetchone()
    if row is None:
        raise LookupError("list not found")
    if row["inbox"]:
        raise ValueError("Inbox cannot be deleted")
    conn.execute(f"DELETE FROM lists WHERE id = {list_id} AND inbox = 0")


class Handler:
    @staticmethod
    def route(path):
        return path.split("/")
'''
SERVER_AFTER = SERVER_BEFORE.replace(
    '''        raise ValueError("Inbox cannot be deleted")
    conn.execute(''', '''        raise ValueError("Inbox cannot be deleted")
    if int(rev) != row["rev"]:
        raise ValueError("the list changed")
    conn.execute(''')

APP_BEFORE = '''// Pocket Todo UI
const api = "/api";

function render(items) {
  const label = "a } brace in a string";
  return items.map((item) => `<li>${item.title} {}</li>`).join("");
}

const save = async (todo) => {
  /* a { brace in a comment */
  const response = await fetch(`${api}/todos/${todo.id}`, {method: "PATCH"});
  if (!response.ok) {
    throw new Error("save failed");
  }
  return response.json();
};

class Store {
  constructor() {
    this.items = [];
  }
  add(item) {
    this.items.push(item);
  }
}
'''
APP_AFTER = APP_BEFORE.replace('throw new Error("save failed");', 'throw new Error("could not save");')


class TouchedCodeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base, self.candidate = Path(temp.name) / "base", Path(temp.name) / "candidate"
        self.base.mkdir()
        self.candidate.mkdir()

    def write(self, name, before, after):
        if before is not None:
            (self.base / name).write_text(before)
        if after is not None:
            (self.candidate / name).write_text(after)

    def test_lists_the_enclosing_python_function(self):
        self.write("server.py", SERVER_BEFORE, SERVER_AFTER)
        [entry] = touched_code(self.base, self.candidate, ["server.py"])
        self.assertEqual(entry["path"], "server.py")
        start = SERVER_AFTER.splitlines().index("def delete_list(conn, list_id, query):") + 1
        end = SERVER_AFTER.splitlines().index('    conn.execute(f"DELETE FROM lists WHERE id = {list_id} AND inbox = 0")') + 1
        self.assertEqual(entry["definitions"], [{"name": "delete_list", "kind": "function", "start": start,
                                                 "end": end}])

    def test_a_python_method_is_named_with_its_class_and_decorator(self):
        after = SERVER_BEFORE.replace('return path.split("/")', 'return path.strip("/").split("/")')
        self.write("server.py", SERVER_BEFORE, after)
        [entry] = touched_code(self.base, self.candidate, ["server.py"])
        [definition] = entry["definitions"]
        self.assertEqual((definition["name"], definition["kind"]), ("Handler.route", "method"))
        self.assertEqual(after.splitlines()[definition["start"] - 1].strip(), "@staticmethod")

    def test_lists_the_enclosing_javascript_function(self):
        self.write("app.js", APP_BEFORE, APP_AFTER)
        [entry] = touched_code(self.base, self.candidate, ["app.js"])
        lines = APP_AFTER.splitlines()
        self.assertEqual(entry["definitions"], [{"name": "save", "kind": "function",
                                                 "start": lines.index("const save = async (todo) => {") + 1,
                                                 "end": lines.index("};") + 1}])

    def test_a_javascript_method_and_braces_in_strings(self):
        after = APP_BEFORE.replace("this.items.push(item);", "this.items.push({...item});")
        self.write("app.js", APP_BEFORE, after)
        [entry] = touched_code(self.base, self.candidate, ["app.js"])
        lines = after.splitlines()
        self.assertEqual(entry["definitions"], [{"name": "add", "kind": "method",
                                                 "start": lines.index("  add(item) {") + 1,
                                                 "end": lines.index("  add(item) {") + 3}])
        render = APP_BEFORE.replace('"a } brace in a string"', '"a } brace, still a string"')
        self.write("app.js", APP_BEFORE, render)
        [entry] = touched_code(self.base, self.candidate, ["app.js"])
        self.assertEqual([item["name"] for item in entry["definitions"]], ["render"])
        self.assertEqual(entry["definitions"][0]["end"], render.splitlines().index("}") + 1)

    def test_callbacks_loops_and_closures_come_with_the_whole_function(self):
        # Review round 1 of PR 49: the innermost "definition" hid the injection around it.
        loop = ('async function deleteList(req, db) {\n  const id = req.params.id;\n'
                '  await db.query("DELETE FROM lists WHERE id = " + id);\n  const rows = await db.all();\n'
                '  for await (const row of rows) {\n    console.log(row);\n  }\n}\n')
        callback = ('function handle(req, db) {\n  const id = req.params.id;\n'
                    '  db.query("DELETE FROM lists WHERE id = " + id);\n'
                    '  items.forEach(function (row) {\n    log(row);\n  });\n}\n')
        closure = ('def outer(conn, list_id):\n    sql = f"DELETE FROM lists WHERE id = {list_id}"\n\n'
                   '    def run():\n        return conn.execute(sql)\n    return run()\n')
        self.write("loop.js", loop, loop.replace("console.log(row)", "console.info(row)"))
        self.write("callback.js", callback, callback.replace("log(row)", "info(row)"))
        self.write("closure.py", closure, closure.replace("return conn.execute(sql)", "return conn.execute(sql) or 0"))
        entries = {item["path"]: item["definitions"] for item in touched_code(
            self.base, self.candidate, ["loop.js", "callback.js", "closure.py"])}
        self.assertEqual(entries["loop.js"], [{"name": "deleteList", "kind": "function", "start": 1, "end": 8}])
        self.assertEqual(entries["callback.js"], [{"name": "handle", "kind": "function", "start": 1, "end": 7}])
        self.assertEqual(entries["closure.py"], [{"name": "outer", "kind": "function", "start": 1, "end": 6}])

    def test_an_anonymous_function_on_its_own_is_a_function(self):
        source = 'const api = 1;\nexport default function (row) {\n  return row;\n}\n'
        self.write("anon.js", source, source.replace("return row;", "return row.id;"))
        [entry] = touched_code(self.base, self.candidate, ["anon.js"])
        self.assertEqual(entry["definitions"], [{"name": "(anonymous)", "kind": "function", "start": 2, "end": 4}])

    def test_top_level_code_or_an_unparsed_language_means_the_whole_file(self):
        self.write("server.py", SERVER_BEFORE, SERVER_BEFORE.replace("import re\n", "import re\nimport json\n"))
        self.write("app.js", APP_BEFORE, APP_BEFORE.replace('"/api"', '"/api/v1"'))
        self.write("styles.css", "body { margin: 0 }\n", "body { margin: 1px }\n")
        self.write("broken.py", "def f(:\n", "def f(:\n  pass\n")
        entries = {item["path"]: item for item in touched_code(
            self.base, self.candidate, ["server.py", "app.js", "styles.css", "broken.py"])}
        for name in ("server.py", "app.js", "styles.css", "broken.py"):
            self.assertTrue(entries[name]["whole_file"], name)
            self.assertNotIn("definitions", entries[name])

    def test_a_deleted_file_has_no_touched_code(self):
        self.write("gone.py", "def f():\n    return 1\n", None)
        self.assertEqual(touched_code(self.base, self.candidate, ["gone.py"]), [])

    def test_the_diff_shows_a_touched_function_in_full(self):
        self.write("server.py", SERVER_BEFORE, SERVER_AFTER)
        touched = touched_code(self.base, self.candidate, ["server.py"])
        diff = Path(self.base.parent / "diff.patch")
        write_diff(diff, self.base, self.candidate, ["server.py"], touched)
        text = diff.read_text()
        # Beyond the three lines of diff context: the injection the reviewer missed at P2-G.
        self.assertIn('row = conn.execute(f"SELECT inbox, rev FROM lists WHERE id = {list_id}").fetchone()', text)
        self.assertIn('rev = query.get("rev", [None])[0]', text)
        self.assertIn("Touched code in full: server.py, delete_list (lines", text)
        self.assertNotIn("def get_lists", text)
        # Whole-file entries show the whole file.
        self.write("styles.css", "body { margin: 0 }\n", "body { margin: 1px }\nmain { padding: 0 }\n")
        write_diff(diff, self.base, self.candidate, ["styles.css"],
                   touched_code(self.base, self.candidate, ["styles.css"]))
        self.assertIn("Touched code in full: styles.css, whole file", diff.read_text())


class PromptTests(unittest.TestCase):
    PACKET = {"attempt_id": "a", "base_digest": "b", "candidate_digest": "c",
              "touched": [{"path": "server.py", "definitions": [
                  {"name": "delete_list", "kind": "function", "start": 8, "end": 18}]}]}

    def text(self, packet):
        role = {"name": "reviewer", "revision": "r", "instructions": "Review.", "skills": []}
        with mock.patch("builder.team.render", return_value="Review."):
            return prompt(role, packet)

    def test_the_prompt_asks_for_a_sweep_of_touched_code_with_its_rule(self):
        text = self.text(self.PACKET)
        for phrase in ("review.json lists touched", "whether or not this candidate introduced it",
                       "inside the job's writable paths", "a threat inside the owner's threat model can reach",
                       "otherwise it is advisory", "plan/planning.json", "threat_model",
                       "at skip depth", "plan/decisions.md", "the threats its decisions defend against"):
            self.assertIn(phrase, text)
        self.assertNotIn("review.json lists touched", self.text({k: v for k, v in self.PACKET.items()
                                                                 if k != "touched"}))


class ReviewPacketTests(unittest.TestCase):
    """Through the `vesper` door: the staged review copy carries `touched`."""
    Base = test_rc1.TeamTests
    setUp, cli, git, plan, approve, submit = (Base.setUp, Base.cli, Base.git, Base.plan, Base.approve,
                                               Base.submit)

    def test_review_json_and_diff_carry_the_touched_code(self):
        _, command = self.plan()
        self.approve(command)
        _, preview = self.submit(command)
        review = Path(preview["review"]["workspace"])
        packet = json.loads((review / "review.json").read_text())
        self.assertEqual(packet["touched"], [{"path": "app.js", "whole_file": True}])
        self.assertIn("Touched code in full: app.js, whole file", (review / "diff.patch").read_text())
        self.assertIn("review.json lists touched", (review / "review.md").read_text())


if __name__ == "__main__":
    unittest.main()
