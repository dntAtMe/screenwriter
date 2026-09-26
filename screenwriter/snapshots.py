"""Document snapshots (version history) and a readable word-level diff.

Snapshots are plain copies of a document, kept in the project folder:

    snapshots/<doc id>/20260926-141503.md
    snapshots/<doc id>/index.json      names: {"20260926-141503.md": "Before rewrite"}
"""

from __future__ import annotations

import difflib
import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

SNAPSHOTS_DIR = "snapshots"
AUTO_NAME = "Automatic (daily)"
STAMP = "%Y%m%d-%H%M%S"


@dataclass
class Snapshot:
    path: Path
    name: str
    created: datetime

    @property
    def label(self) -> str:
        when = self.created.strftime("%d %b %Y, %H:%M")
        return f"{self.name} — {when}" if self.name else when

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")


def _order(snapshot: Snapshot) -> tuple[str, int]:
    """Timestamp, then the -1, -2… counter of snapshots taken in the same second."""
    stem = snapshot.path.name.split(".")[0]
    counter = stem[16:]
    return stem[:15], int(counter) if counter.isdigit() else 0


class SnapshotStore:
    def __init__(self, project_path: Path):
        self.root = project_path / SNAPSHOTS_DIR

    def _dir(self, doc_id: str) -> Path:
        return self.root / doc_id

    def _names(self, doc_id: str) -> dict[str, str]:
        index = self._dir(doc_id) / "index.json"
        return json.loads(index.read_text(encoding="utf-8")) if index.exists() else {}

    def _save_names(self, doc_id: str, names: dict[str, str]) -> None:
        (self._dir(doc_id) / "index.json").write_text(json.dumps(names, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def list(self, doc_id: str) -> list[Snapshot]:
        """Newest first."""
        folder = self._dir(doc_id)
        if not folder.is_dir():
            return []
        names = self._names(doc_id)
        out = []
        for path in folder.iterdir():
            if path.name == "index.json" or path.name.startswith("."):
                continue
            try:
                created = datetime.strptime(path.name.split(".")[0][:15], STAMP)
            except ValueError:
                continue
            out.append(Snapshot(path, names.get(path.name, ""), created))
        return sorted(out, key=_order, reverse=True)

    def take(self, doc_id: str, text: str, extension: str, name: str = "", when: datetime | None = None) -> Snapshot:
        when = when or datetime.now()
        folder = self._dir(doc_id)
        folder.mkdir(parents=True, exist_ok=True)
        base = when.strftime(STAMP)
        path = folder / f"{base}{extension}"
        n = 1
        while path.exists():  # two snapshots in the same second
            path = folder / f"{base}-{n}{extension}"
            n += 1
        path.write_text(text, encoding="utf-8")
        if name:
            names = self._names(doc_id)
            names[path.name] = name
            self._save_names(doc_id, names)
        return Snapshot(path, name, when)

    def delete(self, doc_id: str, snapshot: Snapshot) -> None:
        snapshot.path.unlink(missing_ok=True)
        names = self._names(doc_id)
        if names.pop(snapshot.path.name, None) is not None:
            self._save_names(doc_id, names)

    def delete_all(self, doc_id: str) -> None:
        folder = self._dir(doc_id)
        if folder.is_dir():
            for path in folder.iterdir():
                path.unlink()
            folder.rmdir()

    def has_snapshot_on(self, doc_id: str, day: date) -> bool:
        prefix = day.strftime("%Y%m%d")
        return any(s.path.name.startswith(prefix) for s in self.list(doc_id))


# --- diff ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]")


def _words(old: str, new: str) -> str:
    a, b = TOKEN_RE.findall(old), TOKEN_RE.findall(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(html.escape("".join(a[i1:i2])))
        if op in ("delete", "replace"):
            out.append(f'<span class="del">{html.escape("".join(a[i1:i2]))}</span>')
        if op in ("insert", "replace"):
            out.append(f'<span class="ins">{html.escape("".join(b[j1:j2]))}</span>')
    return "".join(out)


def diff_html(old: str, new: str, context: int = 2) -> str:
    """Changes from old to new as HTML: changed lines with word-level
    <span class="del">/<span class="ins">,
    a little unchanged context around them, and '⋯' for skipped stretches."""
    if old == new:
        return '<p class="same">No changes.</p>'
    a, b = old.splitlines(), new.splitlines()
    rows: list[str] = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for group in matcher.get_grouped_opcodes(context):
        if rows:
            rows.append('<p class="gap">⋯</p>')
        for op, i1, i2, j1, j2 in group:
            if op == "equal":
                rows += [f'<p class="same">{html.escape(line) or "&nbsp;"}</p>' for line in a[i1:i2]]
            elif op == "replace" and i2 - i1 == j2 - j1:
                rows += [f'<p class="changed">{_words(x, y) or "&nbsp;"}</p>' for x, y in zip(a[i1:i2], b[j1:j2])]
            elif op == "replace":
                rows.append(f'<p class="changed">{_words(chr(10).join(a[i1:i2]), chr(10).join(b[j1:j2])).replace(chr(10), "<br>")}</p>')
            elif op == "delete":
                rows += [f'<p class="changed"><span class="del">{html.escape(line) or "&nbsp;"}</span></p>' for line in a[i1:i2]]
            elif op == "insert":
                rows += [f'<p class="changed"><span class="ins">{html.escape(line) or "&nbsp;"}</span></p>' for line in b[j1:j2]]
    return "\n".join(rows)


DIFF_CSS = """
p { margin: 0 0 6px 0; }
p.same { color: gray; }
p.gap { color: gray; text-align: center; }
.del { background-color: #f6c9c9; color: #7a1c1c; text-decoration: line-through; }
.ins { background-color: #c9ecc9; color: #1b5a1b; }
"""
