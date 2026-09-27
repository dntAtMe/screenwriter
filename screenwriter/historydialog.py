"""History window: the project's save points, what changed, compare and restore."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from .projecthistory import Change, ProjectHistory, SavePoint, machine_name
from .diff import DIFF_CSS, diff_html

ROLE = Qt.ItemDataRole.UserRole
BINDER = "project.json"
CONFLICTS = "conflicts.json"
PROJECT_FILES = {BINDER: "Binder (order, titles, synopses)", CONFLICTS: "Conflicts to review",
                 "dictionary.txt": "Project dictionary (spelling)"}
SYMBOLS = {"added": "＋", "modified": "✎", "deleted": "－"}


def when_label(moment: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now().astimezone()
    if moment.date() == now.date():
        day = "Today"
    elif moment.date() == (now - timedelta(days=1)).date():
        day = "Yesterday"
    else:
        day = moment.strftime("%d %b %Y")
    return f"{day}, {moment.strftime('%H:%M')}"


class HistoryDialog(QDialog):
    def __init__(
        self,
        history: ProjectHistory,
        current_text: Callable[[str], str | None],  # doc path → current text (None if it no longer exists)
        readable: Callable[[str, str], str],  # (doc path, raw text) → text to compare (boards: card text)
        restore_document: Callable[[str, str], None],  # (save point id, doc path)
        restore_project: Callable[[str], None],  # save point id
        save_version: Callable[[str], None],  # name
        focus_path: str | None = None,
        focus_title: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("History")
        self.resize(1100, 680)
        self.history = history
        self.current_text, self.readable = current_text, readable
        self.restore_document_cb, self.restore_project_cb, self.save_version_cb = restore_document, restore_project, save_version
        self.focus_path = focus_path

        self.scope = QComboBox()
        self.scope.addItem("Whole project", None)
        if focus_path:
            self.scope.addItem(f"Only “{focus_title}”", focus_path)
            self.scope.setCurrentIndex(1)
        self.scope.currentIndexChanged.connect(self.reload)
        self.show_auto = QCheckBox("Automatic save points")
        self.show_auto.setChecked(True)
        self.show_auto.toggled.connect(self.reload)
        save_btn = QPushButton("Save Version…")
        save_btn.clicked.connect(self._save_version)
        top = QHBoxLayout()
        top.addWidget(QLabel("Show:"))
        top.addWidget(self.scope)
        top.addWidget(self.show_auto)
        top.addStretch()
        top.addWidget(save_btn)

        self.timeline = QListWidget()
        self.timeline.currentItemChanged.connect(self._show_save_point)
        self.documents = QListWidget()
        self.documents.currentItemChanged.connect(self._show_document)
        self.changed_here = QTextBrowser()
        self.changed_here.document().setDefaultStyleSheet(DIFF_CSS)
        self.changes = QTextBrowser()
        self.changes.document().setDefaultStyleSheet(DIFF_CSS)
        self.preview = QPlainTextEdit(readOnly=True)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.changed_here, "What changed here")
        self.tabs.addTab(self.changes, "Changes since, up to now")
        self.tabs.addTab(self.preview, "This version")

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.addWidget(QLabel("Changed in this save point"))
        middle_layout.addWidget(self.documents)
        splitter = QSplitter()
        splitter.addWidget(self.timeline)
        splitter.addWidget(middle)
        splitter.addWidget(self.tabs)
        splitter.setSizes([280, 240, 580])

        self.summary = QLabel()
        self.summary.setStyleSheet("color: gray;")
        self.restore_doc_btn = QPushButton("Restore This Document")
        self.restore_doc_btn.clicked.connect(self._restore_document)
        self.restore_project_btn = QPushButton("Restore Whole Project…")
        self.restore_project_btn.clicked.connect(self._restore_project)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(self.restore_doc_btn)
        bottom.addWidget(self.restore_project_btn)
        bottom.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        layout.addLayout(bottom)
        self.reload()

    # --- timeline -----------------------------------------------------------------------

    def reload(self) -> None:
        path = self.scope.currentData()
        selected = self.selected_point().id if self.selected_point() else None
        self.timeline.clear()
        here = machine_name()
        bold = QFont(self.timeline.font())
        bold.setBold(True)
        for point in self.history.log(path):
            if point.auto and not self.show_auto.isChecked():
                continue
            label = f"{when_label(point.time)} — {point.title}"
            if point.person != point.machine:  # a named writer
                label += f"   · {point.person}" + (f" on {point.machine}" if point.machine != here else "")
            elif point.machine != here:
                label += f"   · on {point.machine}"
            item = QListWidgetItem(label)
            item.setData(ROLE, point)
            item.setToolTip(f"{point.title}\n{point.time:%A %d %B %Y, %H:%M:%S}\n{point.person} on {point.machine}")
            if not point.auto:
                item.setFont(bold)
            else:
                item.setForeground(Qt.GlobalColor.gray)
            self.timeline.addItem(item)
            if point.id == selected:
                self.timeline.setCurrentItem(item)
        if self.timeline.currentItem() is None and self.timeline.count():
            self.timeline.setCurrentRow(0)
        if not self.timeline.count():
            self.documents.clear()
            self.changes.setHtml('<p class="same">No save points yet. They\'re made automatically while you write, or with “Save Version…”.</p>')
            self.preview.clear()
        self._update_buttons()

    def selected_point(self) -> SavePoint | None:
        item = self.timeline.currentItem()
        return item.data(ROLE) if item else None

    def selected_path(self) -> str | None:
        item = self.documents.currentItem()
        return item.data(ROLE).path if item else None

    def _show_save_point(self) -> None:
        point = self.selected_point()
        self.documents.clear()
        if point is None:
            return
        titles = self.history.titles_at(point.id)
        parent_titles = self.history.titles_at(point.parents[0]) if point.parents else {}
        changes = self.history.changes(point.id)
        if not point.parents:  # the first save point: list everything it holds
            changes = [Change(p, "added") for p in self.history.files_at(point.id)]
        focus = self.scope.currentData()
        for change in sorted(changes, key=lambda c: (c.path in PROJECT_FILES, titles.get(c.path, parent_titles.get(c.path, ("", "")))[0].lower())):
            if change.path in PROJECT_FILES:
                label = PROJECT_FILES[change.path]
            else:
                title = (titles.get(change.path) or parent_titles.get(change.path) or (change.path, ""))[0]
                label = f"{SYMBOLS[change.kind]} {title}" + ("  (deleted)" if change.kind == "deleted" else "")
            item = QListWidgetItem(label)
            item.setData(ROLE, change)
            self.documents.addItem(item)
            if change.path == focus:
                self.documents.setCurrentItem(item)
        if self.documents.currentItem() is None and self.documents.count():
            self.documents.setCurrentRow(0)
        self._update_buttons()

    def _show_document(self) -> None:
        point, path = self.selected_point(), self.selected_path()
        if point is None or path is None:
            self.changed_here.clear()
            self.changes.clear()
            self.preview.clear()
            return
        data = self.history.file_at(point.id, path)
        before = self.history.file_at(point.parents[0], path) if point.parents else None
        if data is None:  # deleted in this save point: show the last version before it
            data = before or b""
            self.changed_here.setHtml('<p class="same">Deleted in this save point.</p>')
        else:
            earlier = self.readable(path, before.decode("utf-8", "replace")) if before is not None else ""
            self.changed_here.setHtml(diff_html(earlier, self.readable(path, data.decode("utf-8", "replace"))))
        then = self.readable(path, data.decode("utf-8", "replace"))
        current = self.current_text(path)
        now = self.readable(path, current) if current is not None else ""
        self.changes.setHtml(diff_html(then, now) if current is not None else
                             '<p class="same">This document has been deleted since. Restore it to bring it back.</p>')
        self.preview.setPlainText(then)
        if current is None:
            self.summary.setText(f"{word_count(then)} words in this version · deleted now")
        else:
            delta = word_count(now) - word_count(then)
            self.summary.setText(f"{word_count(then)} words then · {word_count(now)} now ({delta:+d})")
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_point = self.selected_point() is not None
        path = self.selected_path()
        self.restore_project_btn.setEnabled(has_point)
        self.restore_doc_btn.setEnabled(has_point and path is not None and path not in PROJECT_FILES)

    # --- actions ------------------------------------------------------------------------

    def _save_version(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Version", "Name this version (e.g. “Before Act 2 rewrite”):")
        if ok and name.strip():
            self.save_version_cb(name.strip())
            self.reload()
            self.timeline.setCurrentRow(0)

    def _restore_document(self) -> None:
        point, path = self.selected_point(), self.selected_path()
        if point is None or path is None:
            return
        title = self.documents.currentItem().text().lstrip("＋✎－ ").removesuffix("  (deleted)")
        answer = QMessageBox.question(
            self, "Restore Document",
            f"Put “{title}” back the way it was on {when_label(point.time)}?\n\n"
            "The current project is saved as a version first, so you can always come back.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restore_document_cb(point.id, path)
            self.reload()

    def _restore_project(self) -> None:
        point = self.selected_point()
        if point is None:
            return
        answer = QMessageBox.question(
            self, "Restore Whole Project",
            f"Put the whole project back the way it was on {when_label(point.time)} ({point.title})?\n\n"
            "Every document goes back to that version. The current project is saved as a version "
            "first, so you can always come back.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restore_project_cb(point.id)
            self.reload()
