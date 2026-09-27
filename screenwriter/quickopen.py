"""Go to Document: press Shift twice (or Ctrl+P), type part of a name, press Enter.

Lists every document, folder (as its corkboard) and board card in the project,
open tabs first. Letters only need to appear in order ("chk" finds "Chapter 1 —
The Keeper"); names where they start words or run together come first. With a
space, the folder or board counts too ("map lamp": a card on the Story Map).
Shift+Enter opens the pick in the other half of a split view.
"""

import time
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
)

DOUBLE_SHIFT_MS = 400
MAX_ROWS = 60


@dataclass
class Target:
    title: str
    detail: str  # where it is: "Manuscript", "Card on Story Map", "Open"
    kind: str
    node_id: str
    line: int | None = None  # a board card: its line in the board's outline
    is_open: bool = False


def score(query: str, text: str) -> int | None:
    """How well `query` matches `text` (higher is better), or None if its letters
    don't all appear in order."""
    q, t = query.lower().replace(" ", ""), text.lower()
    if not q:
        return 0
    if (at := t.find(query.lower().strip())) >= 0:  # typed as it is written
        return 1000 - at + (200 if at == 0 or not t[at - 1].isalnum() else 0)
    total, pos, prev = 0, 0, -2
    for ch in q:
        found = t.find(ch, pos)
        if found < 0:
            return None
        if found == prev + 1:
            total += 8  # runs of letters
        if found == 0 or not t[found - 1].isalnum():
            total += 12  # start of a word
        total -= min(found - pos, 10)
        prev, pos = found, found + 1
    return total


def rank(query: str, targets: list[Target]) -> list[Target]:
    """Matching targets, best first; with no query, open tabs first, then binder order."""
    if not query.strip():
        return sorted(targets, key=lambda t: not t.is_open)[:MAX_ROWS]
    scored = []
    for i, t in enumerate(targets):
        s = score(query, t.title)
        if s is None and " " in query.strip():  # "story fog": where it is, then the name
            d = score(query, f"{t.detail} {t.title}")
            s = None if d is None else d - 50  # matched only with where it is
        if s is not None:
            scored.append((-(s + (5 if t.is_open else 0) - (20 if t.line is not None else 0)), i, t))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [t for _, _, t in scored[:MAX_ROWS]]


class _Delegate(QStyledItemDelegate):
    """Title, then where it is in grey."""

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        target: Target = index.data(Qt.ItemDataRole.UserRole)
        style = option.widget.style() if option.widget else QApplication.style()
        text, option.text = option.text, ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, option.widget).adjusted(4, 0, -4, 0)
        selected = option.state & QStyle.StateFlag.State_Selected
        role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        painter.save()
        painter.setPen(option.palette.color(role))
        metrics = option.fontMetrics
        title = metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width() * 0.65))
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)
        grey = QColor(option.palette.color(role))
        grey.setAlphaF(0.55)
        painter.setPen(grey)
        left = rect.left() + metrics.horizontalAdvance(title) + 14
        detail_rect = QRect(left, rect.top(), max(0, rect.right() - left), rect.height())
        detail = metrics.elidedText(target.detail, Qt.TextElideMode.ElideLeft, detail_rect.width())
        painter.drawText(detail_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, detail)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), option.fontMetrics.height() + 10))


class QuickOpen(QDialog):
    """The popup. `chosen` (Target) and `beside` (Shift+Enter) are set when accepted."""

    def __init__(self, targets: list[Target], icons: dict[str, QIcon], parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.targets = targets
        self.icons = icons
        self.chosen: Target | None = None
        self.beside = False
        self.input = QLineEdit()
        self.input.setPlaceholderText("Go to document or card…   (Shift+Enter: open beside)")
        self.input.setClearButtonEnabled(True)
        self.list = QListWidget()
        self.list.setItemDelegate(_Delegate(self.list))
        self.list.setUniformItemSizes(True)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(lambda _item: self._accept())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.input)
        layout.addWidget(self.list)
        self.input.textChanged.connect(self._filter)
        self.input.installEventFilter(self)
        self._filter("")
        if parent is not None:
            width = min(640, max(420, parent.width() // 2))
            self.resize(width, 420)
            top = parent.mapToGlobal(parent.rect().topLeft())
            self.move(top.x() + (parent.width() - width) // 2, top.y() + 60)
        self.input.setFocus()

    def _filter(self, query: str) -> None:
        self.list.clear()
        for target in rank(query, self.targets):
            item = QListWidgetItem(self.icons.get(target.kind, QIcon()), target.title)
            item.setData(Qt.ItemDataRole.UserRole, target)
            self.list.addItem(item)
        if self.list.count():
            # with nothing typed, the first row is the tab you're in: offer the one before it
            first_open = not query.strip() and self.list.count() > 1 and self.targets and self.targets[0].is_open
            self.list.setCurrentRow(1 if first_open else 0)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            moves = {Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1, Qt.Key.Key_PageDown: 8, Qt.Key.Key_PageUp: -8}
            if key in moves and self.list.count():
                row = max(0, min(self.list.count() - 1, self.list.currentRow() + moves[key]))
                self.list.setCurrentRow(row)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.beside = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._accept()
                return True
        return super().eventFilter(obj, event)

    def _accept(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.chosen = item.data(Qt.ItemDataRole.UserRole)
            self.accept()


class DoubleShift(QObject):
    """Emits `triggered` when Shift is tapped twice quickly with nothing in between."""

    triggered = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._clean = False  # Shift is down and nothing else was pressed with it
        self._last_tap = 0.0
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.KeyPress and not event.isAutoRepeat():
            if event.key() == Qt.Key.Key_Shift and event.modifiers() in (
                Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier
            ):
                if not self._clean:
                    self._clean = True
                    if time.monotonic() - self._last_tap < DOUBLE_SHIFT_MS / 1000 and QApplication.activeWindow() is self.window:
                        self._last_tap = 0.0
                        self._clean = False
                        self.triggered.emit()
            elif event.key() != Qt.Key.Key_Shift:
                self._clean = False
                self._last_tap = 0.0
        elif kind == QEvent.Type.KeyRelease and not event.isAutoRepeat() and event.key() == Qt.Key.Key_Shift:
            if self._clean:
                self._last_tap = time.monotonic()
            self._clean = False
        elif kind == QEvent.Type.MouseButtonPress:
            self._clean = False
            self._last_tap = 0.0
        return False
