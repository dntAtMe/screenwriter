"""On-disk project format.

A project is a plain folder, readable and git-friendly without the app:

    My Story/
      project.json          binder tree + metadata
      docs/<id>.md          prose and notes (Markdown)
      docs/<id>.fountain    screenplays (Fountain)
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

FORMAT_VERSION = 1
PROJECT_FILE = "project.json"
DOCS_DIR = "docs"

FOLDER, PROSE, SCREENPLAY, NOTE, TRASH = "folder", "prose", "screenplay", "note", "trash"
DOCUMENT_KINDS = (PROSE, SCREENPLAY, NOTE)
EXTENSIONS = {PROSE: ".md", NOTE: ".md", SCREENPLAY: ".fountain"}


@dataclass
class Node:
    id: str
    title: str
    kind: str
    children: list[Node] = field(default_factory=list)
    expanded: bool = True

    @property
    def is_document(self) -> bool:
        return self.kind in DOCUMENT_KINDS

    def to_dict(self) -> dict:
        d = {"id": self.id, "title": self.title, "kind": self.kind}
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
            d["expanded"] = self.expanded
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Node:
        return cls(
            id=d["id"],
            title=d.get("title", "Untitled"),
            kind=d.get("kind", PROSE),
            children=[cls.from_dict(c) for c in d.get("children", [])],
            expanded=d.get("expanded", True),
        )


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Project:
    def __init__(self, path: Path, name: str, root: list[Node], inbox_id: str | None = None):
        self.path = path
        self.name = name
        self.root = root
        self.inbox_id = inbox_id
        self._ensure_trash()

    @classmethod
    def create(cls, path: Path, name: str) -> Project:
        path.mkdir(parents=True, exist_ok=False)
        (path / DOCS_DIR).mkdir()
        project = cls(path, name, [])
        project.save()
        return project

    @classmethod
    def open(cls, path: Path) -> Project:
        data = json.loads((path / PROJECT_FILE).read_text(encoding="utf-8"))
        (path / DOCS_DIR).mkdir(exist_ok=True)
        root = [Node.from_dict(d) for d in data.get("binder", [])]
        return cls(path, data.get("name", path.name), root, data.get("inbox"))

    @staticmethod
    def is_project(path: Path) -> bool:
        return (path / PROJECT_FILE).is_file()

    def save(self) -> None:
        data = {
            "format": FORMAT_VERSION,
            "name": self.name,
            "binder": [n.to_dict() for n in self.root],
        }
        if self.inbox_id:
            data["inbox"] = self.inbox_id
        _write_atomic(self.path / PROJECT_FILE, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def _ensure_trash(self) -> None:
        if not any(n.kind == TRASH for n in self.root):
            self.root.append(Node(id="trash", title="Trash", kind=TRASH))

    # --- documents -------------------------------------------------------

    def new_node(self, kind: str, title: str) -> Node:
        node = Node(id=uuid.uuid4().hex[:12], title=title, kind=kind)
        if node.is_document:
            self.doc_path(node).touch()
        return node

    def doc_path(self, node: Node) -> Path:
        return self.path / DOCS_DIR / f"{node.id}{EXTENSIONS[node.kind]}"

    def read_text(self, node: Node) -> str:
        path = self.doc_path(node)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write_text(self, node: Node, text: str) -> None:
        _write_atomic(self.doc_path(node), text)

    def delete_files(self, node: Node) -> None:
        for n in walk([node]):
            if n.is_document:
                self.doc_path(n).unlink(missing_ok=True)

    def ensure_inbox(self) -> tuple[Node, bool]:
        """The note that quick-captured ideas go to; (node, created)."""
        node = self.find(self.inbox_id) if self.inbox_id else None
        if node is not None and not self.in_trash(node):
            return node, False
        node = self.new_node(NOTE, "Idea Inbox")
        self.write_text(node, "# Idea Inbox\n\n")
        trash_index = next(i for i, n in enumerate(self.root) if n.kind == TRASH)
        self.root.insert(trash_index, node)
        self.inbox_id = node.id
        self.save()
        return node, True

    def in_trash(self, node: Node) -> bool:
        trash = next(n for n in self.root if n.kind == TRASH)
        return any(n.id == node.id for n in walk(trash.children))

    def find(self, node_id: str) -> Node | None:
        return next((n for n in walk(self.root) if n.id == node_id), None)


def walk(nodes: list[Node]):
    for n in nodes:
        yield n
        yield from walk(n.children)
