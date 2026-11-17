"""G_UI: served page structure and assets. Usage: ui.py CANDIDATE_DIR"""
from html.parser import HTMLParser
from pathlib import Path
import sys
import tempfile
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import server


class Surface(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.labels, self.refs = {}, set(), set()
        self.status = False
        self.viewport = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids[attrs["id"]] = (tag, attrs)
        if tag == "label" and attrs.get("for"):
            self.labels.add(attrs["for"])
        if tag == "script" and attrs.get("src"):
            self.refs.add(attrs["src"])
        if tag == "link" and attrs.get("href"):
            self.refs.add(attrs["href"])
        if tag == "meta" and attrs.get("name") == "viewport":
            self.viewport = True
        self.status |= attrs.get("role") == "status"


def fetch(base, path):
    with urlopen(base + path, timeout=5) as response:
        return response.read().decode(), response.headers.get_content_type()


root = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as directory:
    with server(root, Path(directory) / "ui.sqlite3") as base:
        html, kind = fetch(base, "/")
        assert kind == "text/html"
        page = Surface()
        page.feed(html)
        for required in ("list-toggle", "list-panel", "new-list", "new-todo"):
            assert required in page.ids, f"Missing #{required}"
        assert {"new-list", "new-todo"} <= page.labels, "Inputs need visible labels"
        toggle = page.ids["list-toggle"][1]
        assert toggle.get("aria-controls") == "list-panel" and "aria-expanded" in toggle
        assert page.status, "Missing role=status region"
        assert page.viewport, "Missing viewport meta"
        assert {"/app.js", "/styles.css"} <= page.refs
        js, kind = fetch(base, "/app.js")
        assert kind in {"text/javascript", "application/javascript"}
        assert "/api/lists" in js and "/api/todos" in js
        css, kind = fetch(base, "/styles.css")
        assert kind == "text/css" and "720px" in css
print("Served HTML, labelled controls, picker, status region and assets passed.")
