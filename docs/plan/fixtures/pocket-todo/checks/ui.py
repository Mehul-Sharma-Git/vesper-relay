"""G_UI: served page structure and assets. Usage: ui.py CANDIDATE_DIR

Rows of plan/acceptance.md checked here: R4 (labelled controls, picker, filters, status region, local
assets only, and no inline script or style, which the CSP would block)."""
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import OPENER, server

# Attributes that make the browser load something.
LOADS = {"src", "href", "srcset", "action", "formaction", "data", "poster", "background"}


class Surface(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.labels, self.refs = {}, set(), set()
        self.status = False
        self.viewport = False
        self.loads, self.inline_scripts, self.inline_styles = [], 0, []
        self.buttons, self.open_button = [], None

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
        self.loads += [(tag, name, value or "") for name, value in attrs.items() if name in LOADS]
        self.inline_scripts += tag == "script" and not attrs.get("src")
        self.inline_styles += [tag] if tag == "style" or "style" in attrs else []
        self.inline_styles += [f"{tag} {name}" for name in attrs if name.startswith("on")]
        if tag == "button":
            self.open_button = [attrs, ""]
            self.buttons.append(self.open_button)

    def handle_data(self, data):
        if self.open_button is not None:
            self.open_button[1] += data

    def handle_endtag(self, tag):
        if tag == "button":
            self.open_button = None


def local(url):
    """A same-origin path: no scheme, no host (`//`), no `data:` or `javascript:`."""
    return not re.match(r"\s*([a-zA-Z][a-zA-Z0-9+.-]*:|//|\\\\)", url)


def fetch(base, path):
    with OPENER.open(base + path, timeout=5) as response:
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
        assert "rename-list" in page.labels, "Inputs need visible labels: #rename-list (design.md)"
        toggle = page.ids["list-toggle"][1]
        assert toggle.get("aria-controls") == "list-panel" and "aria-expanded" in toggle
        assert page.status, "Missing role=status region"
        assert page.viewport, "Missing viewport meta"
        assert {"/app.js", "/styles.css"} <= page.refs
        remote = [(tag, name, value) for tag, name, value in page.loads if not local(value)]
        assert not remote, f"Only local assets: the page loads {remote}"
        assert not page.inline_scripts, "No inline script: all script in app.js (the CSP blocks inline script)"
        assert not page.inline_styles, f"No inline style or handlers: {page.inline_styles} (the CSP blocks them)"
        filters = {" ".join(text.split()): attrs for attrs, text in page.buttons}
        for name in ("All", "Active", "Done"):
            assert name in filters and filters[name].get("aria-pressed") in {"true", "false"}, \
                f"Filters need an {name} button with aria-pressed"
        assert [filters[name]["aria-pressed"] for name in ("All", "Active", "Done")].count("true") == 1, \
            "Filters need exactly one pressed button"
        js, kind = fetch(base, "/app.js")
        assert kind in {"text/javascript", "application/javascript"}
        assert "/api/lists" in js and "/api/todos" in js
        css, kind = fetch(base, "/styles.css")
        assert kind == "text/css" and "720px" in css
        assert not re.search(r"@import|url\(\s*['\"]?\s*([a-zA-Z][a-zA-Z0-9+.-]*:|//)", css), \
            "Only local assets: styles.css imports or loads a remote resource"
print("Served HTML, labelled controls, picker, filters, status region, local assets and no inline code passed.")
