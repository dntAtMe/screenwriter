"""Snapshots window: browse a document's versions, compare, restore."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .editors.common import word_count
from .snapshots import DIFF_CSS, Snapshot, SnapshotStore, diff_html


class SnapshotsDialog(QDialog):
    def __init__(
        self,
        store: SnapshotStore,
        doc_id: str,
        title: str,
        current_text: Callable[[], str],
        take: Callable[[str], None],
        restore: Callable[[str], None],
        readable: Callable[[str], str] = lambda t: t,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Snapshots — {title}")
        self.resize(980, 640)
        self.store, self.doc_id = store, doc_id
        self.current_text, self.take, self.restore, self.readable = current_text, take, restore, readable

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._show_selected)
        take_btn = QPushButton("Take Snapshot…")
        take_btn.clicked.connect(self._take)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.list)
        row = QHBoxLayout()
        row.addWidget(take_btn)
        row.addWidget(self.delete_btn)
        left_layout.addLayout(row)

        self.changes = QTextBrowser()
        self.changes.document().setDefaultStyleSheet(DIFF_CSS)
        self.preview = QPlainTextEdit(readOnly=True)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.changes, "Changes since this version")
        self.tabs.addTab(self.preview, "This version")

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setSizes([300, 680])

        self.summary = QLabel()
        self.summary.setStyleSheet("color: gray;")
        self.restore_btn = QPushButton("Restore This Version")
        self.restore_btn.clicked.connect(self._restore)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(self.restore_btn)
        bottom.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addLayout(bottom)
        self.reload()

    def reload(self, select: str | None = None) -> None:
        self.list.clear()
        for snap in self.store.list(self.doc_id):
            item = QListWidgetItem(snap.label)
            item.setData(Qt.ItemDataRole.UserRole, snap)
            item.setToolTip(f"{word_count(self.readable(snap.text()))} words")
            self.list.addItem(item)
            if select and snap.path.name == select:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        has = self.list.count() > 0
        self.restore_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        if not has:
            self.changes.setHtml('<p class="same">No snapshots yet. Take one to keep this version.</p>')
            self.preview.clear()
            self.summary.clear()

    def selected(self) -> Snapshot | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _show_selected(self) -> None:
        snap = self.selected()
        if snap is None:
            return
        old, new = self.readable(snap.text()), self.readable(self.current_text())
        self.changes.setHtml(diff_html(old, new))
        self.preview.setPlainText(old)
        delta = word_count(new) - word_count(old)
        self.summary.setText(f"{word_count(old)} words then · {word_count(new)} now ({delta:+d})")

    def _take(self) -> None:
        name, ok = QInputDialog.getText(self, "Take Snapshot", "Name (optional):")
        if ok:
            self.take(name.strip())
            self.reload()

    def _delete(self) -> None:
        snap = self.selected()
        if snap and QMessageBox.question(self, "Delete Snapshot", f"Delete the snapshot “{snap.label}”?") == QMessageBox.StandardButton.Yes:
            self.store.delete(self.doc_id, snap)
            self.reload()

    def _restore(self) -> None:
        snap = self.selected()
        if snap is None:
            return
        answer = QMessageBox.question(
            self, "Restore Version",
            f"Replace the document with “{snap.label}”?\n\n"
            "The current text is kept as a snapshot first, and you can also undo the restore.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restore(snap.text())
            self.reload(select=snap.path.name)
