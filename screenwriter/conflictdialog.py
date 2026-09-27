"""Review Conflicts: paragraphs (or board cards) two people changed differently.

The version already in the document stays until someone chooses: keep it, use the
other one, or keep both. Choices sync to everyone like any other edit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .merge import BOTH, KEEP, THEIRS, ConflictRecord


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d %b %H:%M")
    except ValueError:
        return ""


class ConflictDialog(QDialog):
    def __init__(self, records: list[ConflictRecord], title_of: Callable[[ConflictRecord], str],
                 apply: Callable[[ConflictRecord, str], bool], parent=None):
        """apply(record, choice) changes the document and forgets the record; False if the
        spot can't be found any more."""
        super().__init__(parent)
        self.setWindowTitle("Review Conflicts")
        self.resize(900, 520)
        self.title_of = title_of
        self.apply = apply

        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda *_: self._show())
        for record in records:
            item = QListWidgetItem(f"{title_of(record)}\n{record.kept_by or 'here'} · {record.other_by or 'other'}  {_when(record.time)}")
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.list.addItem(item)

        self.kept_label, self.other_label = QLabel(), QLabel()
        self.kept, self.other = QPlainTextEdit(), QPlainTextEdit()
        for box in (self.kept, self.other):
            box.setReadOnly(True)
        compare = QWidget()
        grid = QGridLayout(compare)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.kept_label, 0, 0)
        grid.addWidget(self.other_label, 0, 1)
        grid.addWidget(self.kept, 1, 0)
        grid.addWidget(self.other, 1, 1)

        self.keep_btn = QPushButton("Keep This Version")
        self.theirs_btn = QPushButton("Use Other Version")
        self.both_btn = QPushButton("Keep Both")
        self.copy_btn = QPushButton("Copy Other Version")
        self.keep_btn.clicked.connect(lambda: self._choose(KEEP))
        self.theirs_btn.clicked.connect(lambda: self._choose(THEIRS))
        self.both_btn.clicked.connect(lambda: self._choose(BOTH))
        self.copy_btn.clicked.connect(self._copy)
        actions = QHBoxLayout()
        actions.addWidget(self.copy_btn)
        actions.addStretch()
        for b in (self.keep_btn, self.theirs_btn, self.both_btn):
            actions.addWidget(b)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.hint = QLabel("Both of you changed the same paragraph. The version on the left is in the document now.")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: gray;")
        right_layout.addWidget(self.hint)
        right_layout.addWidget(compare, 1)
        right_layout.addLayout(actions)

        splitter = QSplitter()
        splitter.addWidget(self.list)
        splitter.addWidget(right)
        splitter.setSizes([260, 640])
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(close)
        if self.list.count():
            self.list.setCurrentRow(0)
        self._show()

    def current(self) -> ConflictRecord | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _show(self) -> None:
        record = self.current()
        for w in (self.keep_btn, self.theirs_btn, self.both_btn, self.copy_btn):
            w.setEnabled(record is not None)
        if record is None:
            self.kept_label.setText("")
            self.other_label.setText("")
            self.kept.clear()
            self.other.clear()
            self.hint.setText("Nothing left to review.")
            return
        thing = "card" if record.card else "paragraph"
        self.hint.setText(f"Both of you changed the same {thing} in “{self.title_of(record)}”. "
                          "The version on the left is in the document now.")
        self.kept_label.setText(f"<b>In the document</b> — {record.kept_by or 'this computer'}")
        self.other_label.setText(f"<b>Other version</b> — {record.other_by or 'other computer'}")
        self.kept.setPlainText(record.kept or "(deleted)")
        self.other.setPlainText(record.other or "(deleted)")

    def _choose(self, choice: str) -> None:
        record = self.current()
        if record is None:
            return
        if not self.apply(record, choice):
            QMessageBox.information(
                self, "Review Conflicts",
                "That part of the document has changed again since, so it can't be replaced automatically.\n\n"
                "Use “Copy Other Version” and paste what you need, then “Keep This Version” to finish.",
            )
            return
        self.list.takeItem(self.list.currentRow())
        self._show()

    def _copy(self) -> None:
        if record := self.current():
            QGuiApplication.clipboard().setText(record.other)
