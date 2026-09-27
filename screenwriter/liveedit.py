"""The window side of live editing (see live.py): every second, publish what this
window shows and merge in what the others are typing; mark where they are."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QColor, QTextCursor, QTextFormat
from PySide6.QtWidgets import QLabel, QTextEdit

from . import people
from .editors.prose import ProseEditor
from .editors.screenplay import ScreenplayEditor
from .live import LiveReader, LiveState, find_line, publish, withdraw
from .merge import merge_text

HEARTBEAT = 5  # seconds between re-publishing an unchanged state, so it stays fresh


class LiveEditing(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.enabled = True
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self._reader: LiveReader | None = None
        self._published: tuple | None = None
        self._since_publish = 0
        self._base_cache: dict[tuple, str] = {}
        self._markers: dict[int, dict[str, tuple[int, QLabel, str]]] = {}  # editor id -> session -> (line, label, colour)
        self._hooked: set[int] = set()  # editors whose scrolling moves the name labels

    # --- where live editing applies ---------------------------------------------------------

    def _package(self):
        w = self.window
        target = w.sync_target
        package = getattr(target, "package", None)  # a shared folder (not Google Drive)
        if not self.enabled or not w.project or package is None or not target.available():
            return None
        return package

    def active(self) -> bool:
        return self._package() is not None and bool(self.window.others)

    @staticmethod
    def _live_editor(editor) -> bool:
        return isinstance(editor, (ProseEditor, ScreenplayEditor))

    # --- the tick ------------------------------------------------------------------------------

    def tick(self) -> None:
        package = self._package()
        if package is None or not self.window.others:
            self.clear()
            return
        if self._reader is None or self._reader.package != package:
            self._reader = LiveReader(package)
        self._publish(package)
        self._take_in(self._reader.read(self.window.session))

    def _base(self, node) -> str:
        """The document as of our last save point: what our live changes are measured against."""
        w = self.window
        head = w.history.head()
        path = f"docs/{w.project.doc_path(node).name}"
        key = (head, path)
        if key not in self._base_cache:
            data = w.history.file_at(head, path) if head else None
            self._base_cache = {key: data.decode("utf-8", "replace") if data else ""}
        return self._base_cache[key]

    def _publish(self, package) -> None:
        w = self.window
        editor = w.tabs.currentWidget()
        node = w.project.find(editor.node_id) if self._live_editor(editor) else None
        if node is None:
            state_key = None
        else:
            block = editor.textCursor().block()
            state_key = (node.id, editor.text(), block.blockNumber())
        self._since_publish += 1
        if state_key == self._published and self._since_publish < HEARTBEAT:
            return
        self._published, self._since_publish = state_key, 0
        if node is None:
            withdraw(package, w.session)
            return
        publish(package, LiveState(w.session, w.person_name(), node.id, state_key[1], self._base(node),
                                   state_key[2], editor.textCursor().block().text()))

    def _take_in(self, states: list[LiveState]) -> None:
        w = self.window
        by_doc: dict[str, list[LiveState]] = {}
        for s in states:
            by_doc.setdefault(s.doc_id, []).append(s)
        shown = set()
        for doc_id, doc_states in by_doc.items():
            editor = w.editors.get(doc_id)
            if not self._live_editor(editor):
                continue
            mine = editor.text()
            merged = mine
            for s in doc_states:
                merged, _ = merge_text(s.base, merged, s.text)  # same words changed on both: ours stays until sync
            if merged != mine and editor.apply_remote_text(merged):
                self._published = None  # tell the others we have their text now
            self._show_cursors(editor, doc_states)
            shown.add(id(editor))
        for key in list(self._markers):
            if key not in shown:
                self._clear_editor(key)

    # --- the others' cursors ------------------------------------------------------------------

    def _show_cursors(self, editor, states: list[LiveState]) -> None:
        markers = self._markers.setdefault(id(editor), {})
        if id(editor) not in self._hooked:
            self._hooked.add(id(editor))
            editor.verticalScrollBar().valueChanged.connect(lambda _=0, e=editor: self._place_labels(e))
            editor.destroyed.connect(lambda _=None, k=id(editor): (self._markers.pop(k, None), self._hooked.discard(k)))
        lines = editor.text().split("\n")
        for session in set(markers) - {s.session for s in states}:
            markers.pop(session)[1].deleteLater()
        selections = []
        for s in states:
            colour = people.colour_for(s.person)
            n = find_line(lines, s.line, s.line_text)
            if s.session not in markers:
                label = QLabel(s.person, editor.viewport())
                label.setStyleSheet(f"background: {colour}; color: white; border-radius: 3px; padding: 0 4px; font-size: 11px;")
                label.adjustSize()
                label.show()
                markers[s.session] = (n, label, colour)
            markers[s.session] = (n, markers[s.session][1], colour)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(editor.document().findBlockByNumber(n))
            selection.cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)  # the whole paragraph
            tint = QColor(colour)
            tint.setAlpha(40)
            selection.format.setBackground(tint)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selections.append(selection)
        editor.setExtraSelections(selections)
        self._place_labels(editor)

    def _place_labels(self, editor) -> None:
        for line, label, _ in self._markers.get(id(editor), {}).values():
            rect = editor.cursorRect(QTextCursor(editor.document().findBlockByNumber(line)))
            label.move(max(0, editor.viewport().width() - label.width() - 6), max(0, rect.top()))

    def _clear_editor(self, key: int) -> None:
        for _, label, _ in self._markers.pop(key, {}).values():
            label.deleteLater()
        editor = next((e for e in self.window.editors.values() if id(e) == key), None)
        if editor is not None and self._live_editor(editor):
            editor.setExtraSelections([])

    def clear(self) -> None:
        for key in list(self._markers):
            self._clear_editor(key)
        self._published = None

    def leave(self) -> None:
        """Stop publishing (the project is closing, or sync stopped)."""
        package = getattr(self.window.sync_target, "package", None)
        if package is not None:
            withdraw(package, self.window.session)
        self.clear()
        self._reader = None
