"""Story bible entry editor: a form, free notes, and where the entry appears."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..bible import CHARACTER, FIELDS, Report, character_report, format_entry, location_report, parse_entry, script_names
from ..fountain import OutlineItem
from .common import word_count
from .prose import ProseEditor

APPEARANCE_ROLE = Qt.ItemDataRole.UserRole


class BibleEditor(QWidget):
    textChanged = Signal()
    statsChanged = Signal()
    cursorPositionChanged = Signal()
    nameChanged = Signal(str)
    openRequested = Signal(str, int, int)  # doc id, position, length

    def __init__(self, kind: str, documents: Callable[[], list] = list, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.documents = documents  # () -> [(doc id, title, kind, text)] to scan for appearances
        self._extra: dict[str, str] = {}  # header keys the form doesn't show
        self._saved = ""

        self.inputs: dict[str, QLineEdit] = {}
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for key, label in FIELDS[kind]:
            edit = QLineEdit()
            if key == "aliases":
                edit.setPlaceholderText(
                    "Other names, comma-separated: MARA, the keeper" if kind == CHARACTER
                    else "Other names, comma-separated: LAMP ROOM, the tower"
                )
            edit.textEdited.connect(self._on_field_edited)
            self.inputs[key] = edit
            form.addRow(label, edit)
        name_font = QFont(self.inputs["name"].font())
        name_font.setPointSizeF(name_font.pointSizeF() * 1.4)
        name_font.setBold(True)
        self.inputs["name"].setFont(name_font)
        self.inputs["name"].textEdited.connect(self.nameChanged)

        self.notes = ProseEditor()
        self.notes.setPlaceholderText("Notes: backstory, appearance, voice, what they want…")
        self.notes.textChanged.connect(self._on_changed)
        self.notes.cursorPositionChanged.connect(self.cursorPositionChanged)

        self.summary = QLabel()
        self.summary.setStyleSheet("color: gray;")
        self.summary.setWordWrap(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_appearances)
        self.appearances = QTreeWidget()
        self.appearances.setHeaderHidden(True)
        self.appearances.setIndentation(12)
        self.appearances.itemActivated.connect(self._open_appearance)
        self.appearances.itemClicked.connect(self._open_appearance)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(8, 0, 0, 0)
        title = QLabel("Appears in" if kind == CHARACTER else "Scenes set here")
        title.setStyleSheet("font-weight: 600;")
        side_layout.addWidget(title)
        side_layout.addWidget(self.summary)
        side_layout.addWidget(self.appearances, 1)
        side_layout.addWidget(refresh, 0, Qt.AlignmentFlag.AlignRight)

        splitter = QSplitter()
        splitter.addWidget(self.notes)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        header = QFrame()
        header.setLayout(form)
        form.setContentsMargins(24, 16, 24, 8)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header)
        layout.addWidget(splitter, 1)

        self._refresh_timer = QTimer(self, singleShot=True, interval=800)
        self._refresh_timer.timeout.connect(self.refresh_appearances)

    # --- document API -------------------------------------------------------------

    def set_text(self, text: str) -> None:
        fields, notes = parse_entry(text)
        self._fill(fields)
        self.notes.set_text(notes)
        self._saved = self.text()
        self.refresh_appearances()

    def _fill(self, fields: dict[str, str]) -> None:
        shown = {key for key, _ in FIELDS[self.kind]}
        self._extra = {k: v for k, v in fields.items() if k not in shown}
        for key, edit in self.inputs.items():
            edit.setText(fields.get(key, ""))

    def fields(self) -> dict[str, str]:
        out = {key: edit.text().strip() for key, edit in self.inputs.items()}
        out.update(self._extra)
        return out

    def text(self) -> str:
        return format_entry(self.fields(), self.notes.toPlainText())

    def is_modified(self) -> bool:
        return self.text() != self._saved

    def mark_saved(self) -> None:
        self._saved = self.text()

    def replace_all(self, text: str) -> None:
        fields, notes = parse_entry(text)
        self._fill(fields)
        self.notes.replace_all(notes)
        self._on_changed()

    def set_name(self, name: str) -> None:
        """Follow a rename in the binder."""
        if self.inputs["name"].text() != name:
            self.inputs["name"].setText(name)
            self._on_changed()

    def stats(self) -> str:
        label = "Character" if self.kind == CHARACTER else "Location"
        return f"{label} · {word_count(self.notes.toPlainText())} words of notes"

    def outline(self) -> list[OutlineItem]:
        return self.notes.outline()

    def search_text(self) -> str:
        return self.text()

    def reveal(self, pos: int, length: int = 0) -> None:
        header = self.text()[: len(self.text()) - len(self.notes.toPlainText())]
        if pos >= len(header):
            self.notes.reveal(pos - len(header), length)
            return
        line = header[:pos].count("\n") - 1  # skip the opening ---
        keys = list(self.fields())
        if 0 <= line < len(keys) and keys[line] in self.inputs:
            edit = self.inputs[keys[line]]
            edit.setFocus()
            edit.selectAll()

    def jump_to_line(self, line: int) -> None:
        self.notes.jump_to_line(line)

    def current_line(self) -> int:
        return self.notes.current_line()

    def selected_text(self) -> str:
        return self.notes.selected_text()

    def zoom(self, steps: int) -> None:
        self.notes.zoom(steps)

    def undo(self) -> None:
        focused = self.focusWidget()
        (focused if isinstance(focused, QLineEdit) else self.notes).undo()

    def redo(self) -> None:
        focused = self.focusWidget()
        (focused if isinstance(focused, QLineEdit) else self.notes).redo()

    def setFocus(self) -> None:
        (self.inputs["name"] if not self.inputs["name"].text() else self.notes).setFocus()

    # --- appearances ----------------------------------------------------------------

    def _on_field_edited(self) -> None:
        self._on_changed()
        self._refresh_timer.start()

    def _on_changed(self) -> None:
        self.textChanged.emit()
        self.statsChanged.emit()

    def names(self) -> list[str]:
        return script_names(self.fields(), self.kind)

    def report(self) -> Report:
        docs = self.documents()
        if self.kind == CHARACTER:
            return character_report(self.names(), docs)
        return location_report(self.names(), docs)

    def refresh_appearances(self) -> None:
        self.appearances.clear()
        names = self.names()
        if not names:
            self.summary.setText("Give the entry a name to find it in your writing.")
            return
        report = self.report()
        bold = QFont(self.appearances.font())
        bold.setBold(True)
        for (doc_id, title), hits in report.by_document().items():
            top = QTreeWidgetItem([f"{title}  ({len(hits)})"])
            top.setFont(0, bold)
            top.setData(0, APPEARANCE_ROLE, (doc_id, 0, 0))
            for a in hits:
                label = f"🗣 {a.label}" if a.speaks else a.label
                child = QTreeWidgetItem([label])
                child.setToolTip(0, a.label)
                child.setData(0, APPEARANCE_ROLE, (a.doc_id, a.pos, a.length))
                top.addChild(child)
            self.appearances.addTopLevelItem(top)
            top.setExpanded(True)
        looked_for = ", ".join(names)
        scenes = len(report.scenes)
        if self.kind == CHARACTER:
            self.summary.setText(
                f"{report.speeches} speech{'es' if report.speeches != 1 else ''} · {report.words} words spoken · "
                f"{scenes} scene{'s' if scenes != 1 else ''}\nLooking for: {looked_for}"
            )
        else:
            self.summary.setText(f"{scenes} scene{'s' if scenes != 1 else ''}\nLooking for: {looked_for}")

    def _open_appearance(self, item: QTreeWidgetItem) -> None:
        doc_id, pos, length = item.data(0, APPEARANCE_ROLE)
        self.openRequested.emit(doc_id, pos, length)
