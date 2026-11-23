"""Knowledge packs (P3-T2): checklists, failure catalogues and guides a role reads beyond its
short role and skill files, in ``team/knowledge/<role>/*.md``.

Each file starts with front matter (``title``, ``tags``, ``last_checked``, ``sources``,
``licence``). A pack is part of its role's frozen revision (``team.profile``), so a run's
approval binds the exact knowledge it used. Search is a standard-library BM25 index over the
pack's paragraphs; a worker's brief gets the top passages for its job goal, and the pack is
mounted read-only at /knowledge in the sandbox."""
from datetime import date, timedelta
import math
from pathlib import Path
import re

from .contracts import require

FIELDS = ("title", "tags", "last_checked", "sources", "licence")
STALE_DAYS = 180          # older facts should be rechecked (a test warns; P5-T3 refreshes them)
# Clocks differ by up to 26 hours across time zones: a file checked "today" by its author can be
# dated tomorrow, or the day after, on the runner (review of PR #57).
FUTURE_SLACK_DAYS = 2
PROMPT_PASSAGES = 5       # passages appended to a worker's brief
FILE_LIMIT = 200_000      # bytes in one pack file
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
URL = re.compile(r"https?://[^\s<>\"']+")
MOUNT = "/knowledge"
# BM25 parameters (Robertson and Zaragoza's usual defaults).
K1, B = 1.5, 0.75
TOKEN = re.compile(r"[a-z0-9]+(?:\+[a-z0-9]+)*")
STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how if in into is it its no not of on or "
    "so than that the their then there these they this to was we what when which who why will with you "
    "your".split())


def default_root():
    from . import team
    return team.ROOT / "knowledge"


def scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def front_matter(text, name):
    """The (fields, body) of one pack file. Lists are inline (``[a, b]``) or ``- item`` lines."""
    lines = text.replace("\r\n", "\n").split("\n")
    require(lines and lines[0].strip() == "---" and "---" in (line.strip() for line in lines[1:]),
            f"Knowledge file {name}: starts without front matter between '---' lines")
    end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    meta = check_fields(read_fields(lines[1:end], name), name)
    return meta, "\n".join(lines[end + 1:]).strip() + "\n"


def read_fields(lines, name):
    meta, key = {}, None
    for line in lines:
        if not line.strip():
            continue
        item = re.match(r"\s+-\s*(.*)", line)
        if item and key and isinstance(meta[key], list):
            meta[key].append(scalar(item.group(1)))
            continue
        found = re.match(r"([a-z_]+):(.*)", line)
        require(found, f"Knowledge file {name}: cannot read front matter line {line.strip()!r}")
        key, value = found.group(1), found.group(2).strip()
        require(key in FIELDS, f"Knowledge file {name}: unknown front matter field {key}")
        require(key not in meta, f"Knowledge file {name}: repeats {key}")
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [scalar(part) for part in value[1:-1].split(",") if part.strip()]
        else:
            meta[key] = scalar(value) if value else []
    return meta


def check_fields(meta, name):
    def check(ok, problem):
        require(ok, f"Knowledge file {name}: {problem}")

    for field in FIELDS:
        check(field in meta, f"has no {field}")
    for field in ("title", "licence"):
        check(isinstance(meta[field], str) and meta[field].strip(), f"{field} must be a non-empty line of text")
    for field in ("tags", "sources"):
        if isinstance(meta[field], str):
            meta[field] = [meta[field]]
        check(meta[field] and all(item.strip() for item in meta[field]), f"{field} must list at least one item")
    for source in meta["sources"]:
        check(URL.fullmatch(source), f"sources must be http(s) URLs, not {source!r}")
    checked = meta["last_checked"]
    check(isinstance(checked, str) and DATE.fullmatch(checked), "last_checked must be a date like 2026-11-21")
    try:
        meta["last_checked"] = date.fromisoformat(checked)
    except ValueError:
        check(False, f"last_checked is not a real date: {checked}")
    check(meta["last_checked"] <= date.today() + timedelta(days=FUTURE_SLACK_DAYS),
          f"last_checked {checked} is in the future")
    return meta


def pack(role, root=None):
    """The role's pack files as {name: text}, sorted by name and each validated; {} when the role
    has none. Links, special files and odd names are refused, so the pack is what the files say."""
    root = Path(root) if root is not None else default_root()
    folder = root / role
    if not folder.exists() and not folder.is_symlink():
        return {}
    require(folder.is_dir() and not folder.is_symlink(), f"Knowledge pack {role} must be a plain folder")
    files = {}
    for path in sorted(folder.iterdir(), key=lambda item: item.name):
        if not path.name.endswith(".md"):
            continue
        require(NAME.fullmatch(path.name), f"Knowledge file {role}/{path.name}: rename it to letters, digits, "
                                           "dots, dashes or underscores")
        require(path.is_file() and not path.is_symlink(), f"Knowledge file {role}/{path.name} must be a plain file")
        require(path.stat().st_size <= FILE_LIMIT, f"Knowledge file {role}/{path.name} exceeds {FILE_LIMIT} bytes")
        text = path.read_text(encoding="utf-8")
        front_matter(text, f"{role}/{path.name}")
        files[path.name] = text
    return files


def stale(root=None, today=None):
    """Every pack file whose last_checked is more than STALE_DAYS old, as ("role/name", date)."""
    root = Path(root) if root is not None else default_root()
    today = today or date.today()
    found = []
    for folder in sorted(root.iterdir(), key=lambda item: item.name) if root.is_dir() else ():
        if folder.is_dir():
            for name, text in pack(folder.name, root).items():
                checked = front_matter(text, f"{folder.name}/{name}")[0]["last_checked"]
                if (today - checked).days > STALE_DAYS:
                    found.append((f"{folder.name}/{name}", checked.isoformat()))
    return found


def passages(files):
    """The pack's paragraphs in order, each with its file and the nearest heading above it (the
    file's title before the first heading). Headings themselves are not passages."""
    found = []
    for name in sorted(files):
        meta, body = front_matter(files[name], name)
        heading = meta["title"]
        for block in re.split(r"\n[ \t]*\n", body):
            lines = block.strip("\n").split("\n")
            while lines and re.match(r"^#{1,6}\s", lines[0]):
                heading = lines.pop(0).lstrip("#").strip()
            text = "\n".join(lines).strip()
            if text:
                found.append({"file": name, "heading": heading, "text": text})
    return found


def stem(word):
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(text):
    return [stem(word) for word in TOKEN.findall(text.lower()) if word not in STOPWORDS]


def search(files, query, limit=PROMPT_PASSAGES):
    """The ``limit`` best passages for ``query`` by BM25, best first; only passages that share a
    term with the query. Ties keep file and paragraph order."""
    terms = list(dict.fromkeys(tokens(query)))
    items = passages(files)
    if not terms or not items:
        return []
    documents = [tokens(item["heading"] + "\n" + item["text"]) for item in items]
    average = sum(map(len, documents)) / len(documents) or 1
    frequency = {term: sum(term in document for document in documents) for term in terms}
    scored = []
    for index, (item, document) in enumerate(zip(items, documents)):
        score = 0.0
        for term in terms:
            count = document.count(term)
            if count:
                idf = math.log(1 + (len(documents) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += idf * count * (K1 + 1) / (count + K1 * (1 - B + B * len(document) / average))
        if score > 0:
            scored.append((-round(score, 6), index, {**item, "score": round(score, 4)}))
    return [item for _, _, item in sorted(scored, key=lambda entry: entry[:2])[:limit]]


def prompt_section(files, goal, role):
    """The brief's knowledge section: the top passages for the job goal from the role's pack, or
    None when nothing in the pack matches."""
    hits = search(files, goal)
    if not hits:
        return None
    lines = [f"Knowledge passages for this job from the {role} knowledge pack (approved reference, best "
             "match first)."]
    for hit in hits:
        body = "\n".join("  " + line for line in hit["text"].split("\n"))
        lines.append(f"- {hit['file']} > {hit['heading']}\n{body}")
    return "\n".join(lines)


def where(path):
    """The line that tells an agent where the approved knowledge packs are readable."""
    return (f"Knowledge packs for every role, as approved for this run, are read-only in {path}/ (one folder "
            "per role, Markdown files with front matter); search them with grep when you need a checklist or "
            "failure catalogue.")


def tree(root=None):
    """Every role's pack as {role: {name: text}}: the team/knowledge/ tree that an approval freezes
    and the sandbox mounts at /knowledge."""
    root = Path(root) if root is not None else default_root()
    if not root.is_dir():
        return {}
    found = {}
    for folder in sorted(root.iterdir(), key=lambda item: item.name):
        if folder.is_dir() or folder.is_symlink():
            require(NAME.fullmatch(folder.name + ".md"), f"Bad knowledge folder name {folder.name!r}")
            files = pack(folder.name, root)
            if files:
                found[folder.name] = files
    return found


def write_tree(packs, directory):
    """Write frozen packs ({role: files}) into ``directory`` with read-only files; returns it."""
    Path(directory).mkdir(parents=True)
    for role, files in packs.items():
        write_pack(files, role, directory)
    return Path(directory)


def write_pack(files, role, directory):
    """Write a frozen pack into ``directory/<role>/`` with read-only files, for the worker to read
    (mounted at /knowledge in the sandbox). Returns ``directory``."""
    require(isinstance(role, str) and NAME.fullmatch(role + ".md"), f"Bad knowledge role {role!r}")
    folder = Path(directory) / role
    folder.mkdir(parents=True)
    require(isinstance(files, dict), f"Bad frozen knowledge pack {role!r}")
    for name, text in files.items():
        require(isinstance(name, str) and NAME.fullmatch(name) and isinstance(text, str),
                f"Bad frozen knowledge file {name!r}")
        target = folder / name
        target.write_text(text, encoding="utf-8")
        target.chmod(0o444)
    return Path(directory)
