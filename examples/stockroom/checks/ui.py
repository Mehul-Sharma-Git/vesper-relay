from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import server


class Surface(HTMLParser):
    def __init__(self):
        super().__init__()
        self.controls = set()
        self.references = set()
        self.labels = set()
        self.status = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"input", "select"}:
            self.controls.add(attrs.get("id"))
        if tag == "label":
            self.labels.add(attrs.get("for"))
        if tag == "script":
            self.references.add(attrs.get("src"))
        if tag == "link":
            self.references.add(attrs.get("href"))
        self.status |= attrs.get("role") == "status"


def fetch(base, path):
    with urlopen(base + path, timeout=4) as response:
        return response.read().decode(), response.headers.get_content_type()


root = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as directory:
    with server(root, Path(directory) / "test.sqlite3") as base:
        html, content_type = fetch(base, "/")
        assert content_type == "text/html"
        surface = Surface()
        surface.feed(html)
        expected = {"name", "room", "quantity", "room-filter", "status-filter"}
        assert expected <= surface.controls and expected <= surface.labels
        assert surface.status
        assert {"/app.js", "/styles.css"} <= surface.references
        javascript, content_type = fetch(base, "/app.js")
        assert content_type in {"text/javascript", "application/javascript"} and "/api/items" in javascript
        css, content_type = fetch(base, "/styles.css")
        assert content_type == "text/css" and css.strip()
print("Loopback HTML, form labels, status region, script, and stylesheet passed.")
