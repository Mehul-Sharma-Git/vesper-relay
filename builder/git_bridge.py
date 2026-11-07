"""Materialize a Git baseline and deliver a guarded patch to its checkout."""
from hashlib import sha256
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

from .contracts import BuilderError, inventory, require, safe_path


def git(cwd, *args, data=None, valid=(0,)):
    overrides = {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT"}
    env = {key: value for key, value in os.environ.items() if key not in overrides}
    try:
        result = subprocess.run(["git", "--literal-pathspecs", "-C", str(cwd), *args],
                                input=data, capture_output=True, timeout=120, env=env)
    except FileNotFoundError as exc:
        raise BuilderError("Git is required for repository mode") from exc
    except subprocess.TimeoutExpired as exc:
        raise BuilderError("A local Git operation timed out") from exc
    if result.returncode not in valid:
        raise BuilderError(result.stderr.decode(errors="replace").strip() or "Local Git operation failed")
    return result.stdout


def repository(path):
    root = Path(git(path, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    commit = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    return {"path": str(root), "commit": commit}


def seed_repository(meta, destination):
    repo = Path(meta["path"])
    output = git(repo, "ls-tree", "-r", "-z", meta["commit"])
    entries = []
    for entry in output.split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, kind, object_id = header.decode().split()
        path = safe_path(name.decode("utf-8"))
        require(kind == "blob" and mode in {"100644", "100755"},
                f"Repository baseline has a symlink, submodule, or unsupported file: {path}")
        entries.append((path, object_id, mode))
    for path, object_id, mode in entries:
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        require(not target.exists(), f"Git path collides on the local filesystem: {path}")
        target.write_bytes(git(repo, "cat-file", "blob", object_id))
        target.chmod(0o755 if mode == "100755" else 0o644)


def file_entries(contents):
    return {path: (entry[0], bool(entry[1] & stat.S_IXUSR))
            for path, entry in contents.items() if entry[0] is not None}


def change(runner, state, meta):
    require(runner.status()["status"] == "complete", "Finish verification before reviewing a Git patch")
    before = runner.control / "snapshots" / state["approval_id"]
    after = runner.snapshot(state)
    require(inventory(before) == state["bundle"]["seed"], "Original Git baseline has changed")
    before_entries, after_entries = state["bundle"]["seed"], runner.check_snapshot(state)
    old, new = file_entries(before_entries), file_entries(after_entries)
    paths = sorted(name for name in old.keys() | new.keys() if old.get(name) != new.get(name))
    require(paths, "Verified snapshot has no Git file changes")
    with tempfile.TemporaryDirectory(prefix="vesper-patch-") as temporary:
        stage = Path(temporary)
        shutil.copytree(before, stage / "before", symlinks=True)
        shutil.copytree(after, stage / "after", symlinks=True)
        require(inventory(stage / "before") == before_entries and inventory(stage / "after") == after_entries,
                "Snapshot changed while preparing the patch")
        patch = git(stage, "diff", "--no-index", "--no-ext-diff", "--no-textconv",
                    "--no-renames", "--no-color", "--src-prefix=a/", "--dst-prefix=b/",
                    "--binary", "--", "before", "after", valid=(0, 1))
    require(patch, "Git could not produce a patch")
    return patch, {"repository": meta["path"], "base": meta["commit"], "files": paths,
                   "digest": sha256(patch).hexdigest()}


def apply_change(runner, state, meta, approved_digest):
    patch, summary = change(runner, state, meta)
    require(approved_digest == summary["digest"], "Patch digest changed. Review the patch again.")
    repo = Path(meta["path"])
    require(repository(repo) == meta, "Repository HEAD changed. Start a new run from the current baseline.")
    old = file_entries(state["bundle"]["seed"])
    require(not any(Path(name).name == ".gitattributes" for name in summary["files"]),
            "Apply a Git attributes change manually after reviewing the patch")
    paths = b"".join(name.encode() + b"\0" for name in summary["files"])
    attributes = git(repo, "check-attr", "--all", "-z", "--stdin", data=paths).split(b"\0")
    conversions = {b"filter", b"text", b"eol", b"working-tree-encoding", b"ident"}
    for index in range(0, len(attributes) - 1, 3):
        path, attribute, value = attributes[index:index + 3]
        plain = (attribute not in conversions
                 or (attribute == b"text" and value in {b"set", b"auto", b"unset"})
                 or (attribute == b"eol" and value == b"lf"))
        require(plain,
                f"Git conversion attribute {attribute.decode()} is active for {path.decode()}. "
                "Apply the reviewed patch manually.")
    staged = git(repo, "diff", "--cached", "--no-renames", "--name-only", "-z",
                 meta["commit"], "--").split(b"\0")
    for name in summary["files"]:
        target = repo / name
        encoded = name.encode()
        require(not any(encoded == path or encoded.startswith(path + b"/")
                        or path.startswith(encoded + b"/") for path in staged if path),
                f"Staged change overlaps the patch: {name}")
        require(not any((repo / parent).is_symlink() for parent in Path(name).parents),
                f"Linked parent overlaps the patch: {name}")
        if name not in old:
            require(not target.exists() and not target.is_symlink(), f"Local file overlaps the patch: {name}")
            continue
        require(target.is_file() and not target.is_symlink(), f"Local file overlaps the patch: {name}")
        entry = (sha256(target.read_bytes()).hexdigest(), bool(target.stat().st_mode & stat.S_IXUSR))
        require(entry == old[name], f"Local edit overlaps the patch: {name}")
    config = ("-c", "core.autocrlf=false", "-c", "core.eol=lf",
              "-c", "core.safecrlf=false", "-c", "apply.ignoreWhitespace=no")
    git(repo, *config, "apply", "-p2", "--whitespace=nowarn", "--check", "-", data=patch)
    require(repository(repo) == meta, "Repository HEAD changed while preparing the patch")
    git(repo, *config, "apply", "-p2", "--whitespace=nowarn", "-", data=patch)
    return {**summary, "applied": True}
