"""Updates: what other people (and your other computers) changed, newest first.

Read from the project history, so it shows everything that has arrived by sync,
whenever it arrived. Entries since you last looked are bold, and the side panel's
tab counts them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from . import people
from .editors.common import word_count
from .projecthistory import ProjectHistory

MERGE_PREFIX = "Merged changes from"
PROJECT_FILES = ("project.json", "conflicts.json")


@dataclass
class DocChange:
    path: str
    title: str
    kind: str  # "added" | "modified" | "deleted"
    words: int  # words added (+) or removed (-)


@dataclass
class Update:
    point: str
    person: str
    machine: str
    time: datetime
    docs: list[DocChange] = field(default_factory=list)


def _words(data: bytes | None, path: str) -> int:
    if not data:
        return 0
    text = data.decode("utf-8", "replace")
    if path.endswith(".board.json"):
        from .board import search_text

        text = search_text(text)
    return word_count(text)


def recent_updates(history: ProjectHistory, me: str, machine: str, limit: int = 40) -> list[Update]:
    """Save points made by anyone but you on this computer, with the documents they changed."""
    out = []
    for point in history.log():
        if len(out) >= limit:
            break
        if not point.parents or point.message.startswith(MERGE_PREFIX):
            continue  # the project's first save point, or a sync merging (its changes are listed on their own)
        if point.person == me and point.machine == machine:
            continue
        titles = history.titles_at(point.id)
        parent_titles = history.titles_at(point.parents[0]) if point.parents else {}
        docs = []
        for change in history.changes(point.id):
            if change.path in PROJECT_FILES:
                continue
            title = (titles.get(change.path) or parent_titles.get(change.path) or (change.path, ""))[0]
            before = history.file_at(point.parents[0], change.path) if point.parents else None
            after = history.file_at(point.id, change.path)
            docs.append(DocChange(change.path, title, change.kind, _words(after, change.path) - _words(before, change.path)))
        if docs:
            out.append(Update(point.id, point.person, point.machine, point.time, docs))
    return out


def arrived(history: ProjectHistory, before: bytes | None) -> list[str]:
    """Who made the save points that are new since `before` (the head before a sync), in order."""
    if before is None:
        return []
    seen = {e.commit.id for e in history.repo.get_walker(include=[before])}
    names: list[str] = []
    for entry in history.repo.get_walker(include=[history.head()], exclude=[before]):
        if entry.commit.id in seen or not entry.commit.parents:
            continue
        point = history.get(entry.commit.id)
        if not point.message.startswith(MERGE_PREFIX) and point.person not in names:
            names.append(point.person)
    return names


def _delta(words: int) -> str:
    return f"+{words} words" if words > 0 else f"{words} words" if words < 0 else "edited"


class UpdatesPanel(QWidget):
    openRequested = Signal(str)  # node id
    historyRequested = Signal(str)  # doc path

    PATH_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: gray;")
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.itemActivated.connect(self._open)
        self.tree.currentItemChanged.connect(lambda *_: self.changes_btn.setEnabled(self._path() is not None))
        self.changes_btn = QPushButton("Show Changes…")
        self.changes_btn.setEnabled(False)
        self.changes_btn.clicked.connect(lambda: self._path() and self.historyRequested.emit(self._path()))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.hint)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.changes_btn)

    def set_updates(self, updates: list[Update], me: str, seen: datetime | None) -> int:
        """Show the updates; returns how many are new since `seen`."""
        self.tree.clear()
        new = 0
        for u in updates:
            is_new = seen is None or u.time > seen
            new += is_new
            who = f"{u.person} on {u.machine}" if u.person == me else u.person
            top = QTreeWidgetItem([f"{who} · {u.time:%d %b %H:%M}"])
            top.setForeground(0, QColor(people.colour_for(u.person)))
            font = QFont(self.font())
            font.setBold(is_new)
            top.setFont(0, font)
            for d in u.docs:
                suffix = " (new)" if d.kind == "added" else " (deleted)" if d.kind == "deleted" else ""
                child = QTreeWidgetItem([f"{d.title}{suffix} — {_delta(d.words)}"])
                child.setData(0, self.PATH_ROLE, d.path)
                child.setToolTip(0, "Double-click to open; Show Changes… for what changed")
                top.addChild(child)
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)
        self.hint.setText("Changes from other people and your other computers arrive here when the project syncs."
                          if not updates else f"{new} new since you last looked." if new else "")
        self.hint.setVisible(bool(self.hint.text()))
        return new

    def _path(self) -> str | None:
        item = self.tree.currentItem()
        return item.data(0, self.PATH_ROLE) if item else None

    def _open(self, item: QTreeWidgetItem) -> None:
        path = item.data(0, self.PATH_ROLE)
        if path:
            self.openRequested.emit(path.split("/")[-1].split(".")[0])
