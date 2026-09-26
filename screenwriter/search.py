"""Project-wide search panel and the in-document find bar."""

import re
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

MAX_HITS = 1000
SNIPPET = 36  # characters of context on each side


@dataclass
class Hit:
    pos: int
    length: int
    line: int
    snippet: str


def find_hits(text: str, query: str, case_sensitive: bool = False) -> list[Hit]:
    if not query:
        return []
    flags = 0 if case_sensitive else re.IGNORECASE
    hits = []
    line, line_start, scanned = 0, 0, 0
    for m in re.finditer(re.escape(query), text, flags):
        # advance line bookkeeping incrementally
        line += text.count("\n", scanned, m.start())
        nl = text.rfind("\n", 0, m.start())
        line_start = nl + 1
        scanned = m.start()
        line_end = text.find("\n", m.start())
        line_end = len(text) if line_end == -1 else line_end
        start = max(line_start, m.start() - SNIPPET)
        end = min(line_end, m.end() + SNIPPET)
        snippet = ("…" if start > line_start else "") + text[start:end].strip() + ("…" if end < line_end else "")
        hits.append(Hit(m.start(), m.end() - m.start(), line, snippet))
        if len(hits) >= MAX_HITS:
            break
    return hits


# (node id, title, text) for every searchable document
Source = Callable[[], list[tuple[str, str, str]]]


class SearchPanel(QWidget):
    openRequested = Signal(str, int, int)  # node id, position, length

    def __init__(self, source: Source, parent=None):
        super().__init__(parent)
        self.source = source
        self.query = QLineEdit(placeholderText="Search project…", clearButtonEnabled=True)
        self.case = QCheckBox("Aa")
        self.case.setToolTip("Match case")
        self.summary = QLabel()
        self.summary.setStyleSheet("color: gray;")
        self.results = QTreeWidget()
        self.results.setHeaderHidden(True)
        self.results.setIndentation(12)
        self.results.itemClicked.connect(self._open)
        self.results.itemActivated.connect(self._open)

        row = QHBoxLayout()
        row.addWidget(self.query)
        row.addWidget(self.case)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(row)
        layout.addWidget(self.summary)
        layout.addWidget(self.results)

        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self.run)
        self.query.textChanged.connect(self._timer.start)
        self.query.returnPressed.connect(self.run)
        self.case.toggled.connect(self.run)

    def focus(self, text: str = "") -> None:
        if text:
            self.query.setText(text)
        self.query.setFocus()
        self.query.selectAll()

    def run(self) -> None:
        self._timer.stop()
        self.results.clear()
        q = self.query.text()
        if not q.strip():
            self.summary.clear()
            return
        bold = QFont(self.results.font())
        bold.setBold(True)
        total, docs = 0, 0
        for node_id, title, text in self.source():
            hits = find_hits(text, q, self.case.isChecked())
            title_hit = (q in title) if self.case.isChecked() else (q.lower() in title.lower())
            if not hits and not title_hit:
                continue
            docs += 1
            total += len(hits)
            top = QTreeWidgetItem([f"{title}  ({len(hits)})"])
            top.setFont(0, bold)
            top.setData(0, Qt.ItemDataRole.UserRole, (node_id, 0, 0))
            for h in hits:
                child = QTreeWidgetItem([f"{h.line + 1}: {h.snippet}"])
                child.setToolTip(0, h.snippet)
                child.setData(0, Qt.ItemDataRole.UserRole, (node_id, h.pos, h.length))
                top.addChild(child)
            self.results.addTopLevelItem(top)
            top.setExpanded(True)
        self.summary.setText(f"{total} match{'es' if total != 1 else ''} in {docs} document{'s' if docs != 1 else ''}")

    def _open(self, item: QTreeWidgetItem) -> None:
        node_id, pos, length = item.data(0, Qt.ItemDataRole.UserRole)
        self.openRequested.emit(node_id, pos, length)


class FindBar(QWidget):
    """Find within the current document (Ctrl+F)."""

    def __init__(self, current_editor: Callable, parent=None):
        super().__init__(parent)
        self.current_editor = current_editor
        self.field = QLineEdit(placeholderText="Find in document", clearButtonEnabled=True)
        self.count = QLabel()
        self.count.setStyleSheet("color: gray;")
        prev_btn, next_btn, close_btn = QToolButton(text="↑"), QToolButton(text="↓"), QToolButton(text="✕")
        prev_btn.clicked.connect(lambda: self.find(backward=True))
        next_btn.clicked.connect(lambda: self.find())
        close_btn.clicked.connect(self.close_bar)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.field, 1)
        layout.addWidget(self.count)
        layout.addWidget(prev_btn)
        layout.addWidget(next_btn)
        layout.addWidget(close_btn)

        self.field.textChanged.connect(self._on_text_changed)
        self.field.returnPressed.connect(self.find)
        QShortcut(QKeySequence("Shift+Return"), self.field, lambda: self.find(backward=True))
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close_bar)
        self.hide()

    def open_bar(self) -> None:
        editor = self.current_editor()
        if editor and editor.textCursor().hasSelection():
            self.field.setText(editor.textCursor().selectedText())
        self.show()
        self.field.setFocus()
        self.field.selectAll()
        self._update_count()

    def close_bar(self) -> None:
        self.hide()
        if editor := self.current_editor():
            editor.setFocus()

    def _on_text_changed(self) -> None:
        self._update_count()
        if editor := self.current_editor():
            # search from the start of the current selection so typing refines in place
            cursor = editor.textCursor()
            cursor.setPosition(cursor.selectionStart())
            editor.setTextCursor(cursor)
        self.find()

    def _update_count(self) -> None:
        editor = self.current_editor()
        q = self.field.text()
        if not editor or not q:
            self.count.clear()
            return
        n = len(find_hits(editor.toPlainText(), q))
        self.count.setText(f"{n}{'+' if n >= MAX_HITS else ''} found" if n else "not found")

    def find(self, backward: bool = False) -> None:
        editor = self.current_editor()
        q = self.field.text()
        if not editor or not q:
            return
        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        if not editor.find(q, flags):
            cursor = editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End if backward else cursor.MoveOperation.Start)
            editor.setTextCursor(cursor)
            editor.find(q, flags)
