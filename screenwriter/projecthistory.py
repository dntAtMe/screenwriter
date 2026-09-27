"""Project history: save points of the whole project, without the writer ever seeing git.

Each save point records project.json and every document under docs/. History is
stored in the project's `.history/` folder in git's object format (via dulwich),
so it's compact, proven, and readable by git tools if anyone ever needs to.
Nothing here touches the working files except restore_files().
"""

from __future__ import annotations

import getpass
import json
import platform
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dulwich.diff_tree import tree_changes
from dulwich.object_store import iter_tree_contents, tree_lookup_path
from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

HISTORY_DIR = ".history"
BRANCH = b"refs/heads/main"
AUTO_MESSAGE = "Automatic save point"
TRACKED_FILES = ("project.json", "conflicts.json", "dictionary.txt", "comments.json")
TRACKED_DIRS = ("docs",)
FILE_MODE, DIR_MODE = 0o100644, 0o040000


def machine_name() -> str:
    """A friendly name for this computer: "Kacpers-MacBook-Air"."""
    return platform.node().removesuffix(".local") or "this computer"


@dataclass
class SavePoint:
    id: str
    message: str
    machine: str  # the computer
    time: datetime
    parents: list[str]
    person: str = ""  # who wrote it (older save points only know the computer)

    def __post_init__(self):
        self.person = self.person or self.machine

    @property
    def auto(self) -> bool:
        return self.message == AUTO_MESSAGE

    @property
    def title(self) -> str:
        return "Automatic save point" if self.auto else self.message


@dataclass
class Change:
    path: str  # "docs/abc123.md"
    kind: str  # "added" | "modified" | "deleted"


def read_tracked_files(project_path: Path) -> dict[str, bytes]:
    """The files a save point records, keyed by POSIX path relative to the project."""
    files = {}
    for name in TRACKED_FILES:
        path = project_path / name
        if path.is_file():
            files[name] = path.read_bytes()
    for folder in TRACKED_DIRS:
        root = project_path / folder
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and not path.name.endswith(".tmp") and not path.name.startswith("."):
                    files[path.relative_to(project_path).as_posix()] = path.read_bytes()
    return files


class ProjectHistory:
    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.machine = machine_name()  # recorded on save points; sync shows where changes came from
        self.person = ""  # the writer's name, recorded with the computer ("" = just the computer)
        path = self.project_path / HISTORY_DIR
        self.repo = Repo(str(path)) if (path / "objects").is_dir() else Repo.init_bare(str(path), mkdir=True)

    def close(self) -> None:
        self.repo.close()

    # --- writing ----------------------------------------------------------------

    def head(self) -> bytes | None:
        try:
            return self.repo.refs[BRANCH]
        except KeyError:
            return None

    def _build_tree(self, files: dict[str, bytes]) -> bytes:
        """Store the files and return the root tree id."""
        store = self.repo.object_store
        nested: dict = {}
        for path, data in files.items():
            *folders, name = path.split("/")
            node = nested
            for folder in folders:
                node = node.setdefault(folder, {})
            blob = Blob.from_string(data)
            store.add_object(blob)
            node[name] = blob.id

        def write(node: dict) -> bytes:
            tree = Tree()
            for name, value in node.items():
                if isinstance(value, dict):
                    tree.add(name.encode(), DIR_MODE, write(value))
                else:
                    tree.add(name.encode(), FILE_MODE, value)
            store.add_object(tree)
            return tree.id

        return write(nested)

    def commit_files(self, files: dict[str, bytes], message: str, parents: list[bytes],
                     when: float | None = None, machine: str | None = None) -> bytes:
        """Record `files` as a save point with the given parents; moves nothing."""
        who = self.person if machine is None else machine
        machine = machine or self.machine
        commit = Commit()
        commit.tree = self._build_tree(files)
        commit.parents = parents
        identity = f"{who or machine} <{getpass.getuser()}@{machine}>".encode()
        commit.author = commit.committer = identity
        commit.author_time = commit.commit_time = int(when if when is not None else time.time())
        offset = int(datetime.now().astimezone().utcoffset().total_seconds())
        commit.author_timezone = commit.commit_timezone = offset
        commit.encoding = b"UTF-8"
        commit.message = message.encode("utf-8")
        self.repo.object_store.add_object(commit)
        return commit.id

    def save_point(self, message: str = "", when: float | None = None) -> SavePoint | None:
        """Record the project as it is on disk now. Returns None if nothing changed
        since the last save point (unless a name is given, which always records)."""
        files = read_tracked_files(self.project_path)
        head = self.head()
        auto = not message.strip()
        if head is not None and auto and self.repo[head].tree == self._build_tree(files):
            return None
        commit_id = self.commit_files(files, message.strip() or AUTO_MESSAGE, [head] if head else [], when)
        self.repo.refs[BRANCH] = commit_id
        return self.get(commit_id)

    def set_head(self, commit_id: bytes) -> None:
        self.repo.refs[BRANCH] = commit_id

    # --- reading ----------------------------------------------------------------

    def get(self, commit_id: bytes | str) -> SavePoint:
        commit = self.repo[_id(commit_id)]
        author = commit.author.decode("utf-8", "replace")
        person, _, email = author.partition(" <")
        machine = email.rstrip(">").partition("@")[2] or person
        return SavePoint(
            id=commit.id.decode(),
            message=commit.message.decode("utf-8", "replace").strip(),
            machine=machine,
            person=person,
            time=datetime.fromtimestamp(commit.author_time, timezone.utc).astimezone(),
            parents=[p.decode() for p in commit.parents],
        )

    def log(self, path: str | None = None, include: list[bytes] | None = None) -> list[SavePoint]:
        """Save points, newest first; only those that changed `path` when given."""
        heads = include or ([self.head()] if self.head() else [])
        if not heads:
            return []
        walker = self.repo.get_walker(include=heads, paths=[path.encode()] if path else None)
        return [self.get(entry.commit.id) for entry in walker]

    def files_at(self, commit_id: bytes | str) -> dict[str, bytes]:
        tree = self.repo[_id(commit_id)].tree
        return {
            entry.path.decode(): self.repo[entry.sha].data
            for entry in iter_tree_contents(self.repo.object_store, tree)
        }

    def file_at(self, commit_id: bytes | str, path: str) -> bytes | None:
        try:
            _, sha = tree_lookup_path(self.repo.__getitem__, self.repo[_id(commit_id)].tree, path.encode())
        except KeyError:
            return None
        return self.repo[sha].data

    def changes(self, commit_id: bytes | str, against: bytes | str | None = None) -> list[Change]:
        """What a save point changed compared with `against` (default: its parent)."""
        commit = self.repo[_id(commit_id)]
        if against is None:
            old_tree = self.repo[commit.parents[0]].tree if commit.parents else None
        else:
            old_tree = self.repo[_id(against)].tree
        kinds = {"add": "added", "delete": "deleted", "modify": "modified"}
        out = []
        for change in tree_changes(self.repo.object_store, old_tree, commit.tree):
            if change.type in kinds:
                entry = change.new if change.new is not None and change.new.path else change.old
                path = entry.path.decode()
                out.append(Change(path, kinds[change.type]))
        return out

    def titles_at(self, commit_id: bytes | str) -> dict[str, tuple[str, str]]:
        """{doc path: (title, kind)} from the binder as it was at that save point."""
        from .project import EXTENSIONS, Node, walk

        data = self.file_at(commit_id, "project.json")
        if not data:
            return {}
        nodes = [Node.from_dict(d) for d in json.loads(data).get("binder", [])]
        return {
            f"docs/{n.id}{EXTENSIONS[n.kind]}": (n.title, n.kind)
            for n in walk(nodes)
            if n.kind in EXTENSIONS
        }

    def node_at(self, commit_id: bytes | str, node_id: str):
        """The binder node (and its parent's id) as it was at that save point."""
        from .project import Node

        data = self.file_at(commit_id, "project.json")
        if not data:
            return None, None

        def find(nodes, parent):
            for n in nodes:
                if n.id == node_id:
                    return n, parent
                found = find(n.children, n.id)
                if found[0]:
                    return found
            return None, None

        return find([Node.from_dict(d) for d in json.loads(data).get("binder", [])], None)

    # --- restoring --------------------------------------------------------------

    def restore_files(self, commit_id: bytes | str, paths: list[str] | None = None) -> list[str]:
        """Write files from a save point into the project folder. With no paths, the
        whole project is put back as it was (tracked files not in it are removed)."""
        files = self.files_at(commit_id)
        wanted = files if paths is None else {p: files[p] for p in paths if p in files}
        for path, data in wanted.items():
            target = self.project_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(target)
        if paths is None:
            for path in set(read_tracked_files(self.project_path)) - set(files):
                (self.project_path / path).unlink(missing_ok=True)
        return list(wanted)

    def pack(self) -> None:
        """Pack loose objects into one file (keeps the history folder small)."""
        self.repo.object_store.pack_loose_objects()


def _id(commit_id: bytes | str) -> bytes:
    return commit_id.encode() if isinstance(commit_id, str) else commit_id
