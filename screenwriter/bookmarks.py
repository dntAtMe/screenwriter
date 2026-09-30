"""Bookmarks: mark a line, come back to it later.

Toggle one on the cursor's line (Ctrl+Shift+K); a ribbon in the margin shows it. F2 /
Shift+F2 go to the next / previous bookmark across the project, and every bookmark is
listed in Go to Document. Bookmarks follow their line as the text around them is edited,
and are kept per project on this computer (they're yours, not part of the story).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from PySide6.QtCore import QEvent, QPointF, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette, QTextCursor
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QWidget

from .live import find_line

GUTTER = 18  # px of the left margin the ribbons use


@dataclass
class Bookmark:
    doc: str  # node id
    line: int  # block number in the document's text (a bible entry: in its notes)
    text: str  # the line's text when last seen, to find it again after edits elsewhere


def load(settings, project_id: str) -> list[Bookmark]:
    try:
        return [Bookmark(**b) for b in json.loads(settings.value(f"bookmarks/{project_id}", "[]") or "[]")]
    except (TypeError, ValueError):
        return []


def save(settings, project_id: str, bookmarks: list[Bookmark]) -> None:
    settings.setValue(f"bookmarks/{project_id}", json.dumps([asdict(b) for b in bookmarks], ensure_ascii=False))


def label(text: str) -> str:
    """How a bookmarked line is shown in lists: its text, or "(empty line)"."""
    text = text.strip().lstrip("#").strip()
    return text[:80] or "(empty line)"


# --- in an editor ---------------------------------------------------------------------------


def attach(box, marks: list[tuple[int, str]]) -> None:
    """Give a text box its bookmarks, (line, text) as saved; each is found again by its text."""
    doc = box.document()
    lines = box.toPlainText().split("\n")
    box.bookmark_cursors = []
    for line, text in marks:
        n = find_line(lines, line, text)
        box.bookmark_cursors.append(QTextCursor(doc.findBlockByNumber(n)))
    if not hasattr(box, "bookmark_gutter"):
        box.bookmark_gutter = Gutter(box)
    box.bookmark_gutter.refresh()


def lines(box) -> list[tuple[int, str]]:
    """(line, text) of a box's bookmarks now, in order, one per line."""
    found = {}
    for cursor in getattr(box, "bookmark_cursors", []):
        block = cursor.block()
        if block.isValid():
            found[block.blockNumber()] = block.text()
    return sorted(found.items())


def toggle(box) -> bool:
    """Bookmark the cursor's line, or remove its bookmark; whether it's bookmarked now."""
    if not hasattr(box, "bookmark_cursors"):
        attach(box, [])
    line = box.textCursor().blockNumber()
    if any(n == line for n, _ in lines(box)):
        box.bookmark_cursors = [c for c in box.bookmark_cursors if c.block().blockNumber() != line]
        on = False
    else:
        box.bookmark_cursors.append(QTextCursor(box.textCursor().block()))
        on = True
    box.bookmark_gutter.refresh()
    return on


class Gutter(QWidget):
    """Ribbons in the editor's left margin beside bookmarked lines."""

    def __init__(self, box):
        super().__init__(box)
        self.box = box
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        box.verticalScrollBar().valueChanged.connect(self.update)
        box.document().contentsChange.connect(lambda *_: self.update())
        box.installEventFilter(self)  # follows the editor's size (the gutter itself: it lives as long as the box)
        self.refresh()

    def refresh(self) -> None:
        viewport = self.box.viewport().geometry()
        width = min(GUTTER, max(0, viewport.left()))
        self.setGeometry(viewport.left() - width, viewport.top(), width, viewport.height())
        self.setVisible(bool(lines(self.box)) and width > 6)
        self.update()

    def eventFilter(self, obj, e):
        if obj is self.box and e.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest):
            QTimer.singleShot(0, self, self.refresh)  # after the editor has set its margins (not if it's gone)
        return False

    def paintEvent(self, _event) -> None:
        from . import theme

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.tokens()["accent"]))
        height = self.box.fontMetrics().height()
        w = min(10.0, self.width() - 4.0)
        for n, _ in lines(self.box):
            rect = self.box.cursorRect(QTextCursor(self.box.document().findBlockByNumber(n)))
            if rect.bottom() < 0 or rect.top() > self.height():
                continue
            top = rect.top() + max(0, (rect.height() - height) / 2)
            x = self.width() - w - 4
            h = min(height, 14.0)
            ribbon = [QPointF(x, top), QPointF(x + w, top), QPointF(x + w, top + h),
                      QPointF(x + w / 2, top + h - w / 2.5), QPointF(x, top + h)]
            painter.drawPolygon(ribbon)
        painter.end()


class Delegate(QStyledItemDelegate):
    """A bookmark in the sidebar list: the line, and the document it's in below it in grey."""

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        target = index.data(Qt.ItemDataRole.UserRole)
        style = option.widget.style() if option.widget else QApplication.style()
        text, option.text = option.text, ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        if target is None:  # the hint when there are none
            painter.save()
            grey = QColor(option.palette.color(QPalette.ColorRole.Text))
            grey.setAlphaF(0.5)
            painter.setPen(grey)
            painter.drawText(option.rect.adjusted(8, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, text)
            painter.restore()
            return
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, option.widget).adjusted(2, 0, -4, 0)
        metrics = option.fontMetrics
        half = rect.height() // 2
        painter.save()
        painter.setPen(option.palette.color(QPalette.ColorRole.Text))
        top = QRect(rect.left(), rect.top(), rect.width(), half)
        painter.drawText(top, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                         metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.width()))
        small = option.font
        small.setPointSizeF(small.pointSizeF() * 0.85)
        painter.setFont(small)
        grey = QColor(option.palette.color(QPalette.ColorRole.Text))
        grey.setAlphaF(0.55)
        painter.setPen(grey)
        bottom = QRect(rect.left(), rect.top() + half, rect.width(), rect.height() - half)
        painter.drawText(bottom, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(target.detail, Qt.TextElideMode.ElideRight, rect.width()))
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        lines = 1 if index.data(Qt.ItemDataRole.UserRole) is None else 2
        return QSize(size.width(), option.fontMetrics.height() * lines + 10)
