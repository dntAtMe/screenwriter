"""Outline panel: scenes and sections of a script, or headings of prose."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from .fountain import OutlineItem

LINE_ROLE = Qt.ItemDataRole.UserRole


class OutlinePanel(QTreeWidget):
    jumpRequested = Signal(int)  # line number

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setUniformRowHeights(True)
        self.itemClicked.connect(lambda item: self.jumpRequested.emit(item.data(0, LINE_ROLE)))
        self.itemActivated.connect(lambda item: self.jumpRequested.emit(item.data(0, LINE_ROLE)))
        self._items: list[OutlineItem] = []
        self._tree_items: list[QTreeWidgetItem] = []

    def set_items(self, items: list[OutlineItem]) -> None:
        if [(i.level, i.title, i.line) for i in items] == [(i.level, i.title, i.line) for i in self._items]:
            return
        self._items = items
        self.clear()
        self._tree_items = []
        bold = QFont(self.font())
        bold.setBold(True)
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for it in items:
            while stack and stack[-1][0] >= it.level:
                stack.pop()
            label = f"{it.number}. {it.title}" if it.kind == "scene" else it.title
            item = QTreeWidgetItem([label])
            item.setData(0, LINE_ROLE, it.line)
            item.setToolTip(0, label)
            if it.kind in ("section", "heading") and it.level == 0:
                item.setFont(0, bold)
            (stack[-1][1] if stack else self.invisibleRootItem()).addChild(item)
            if it.kind != "scene":
                stack.append((it.level, item))
            self._tree_items.append(item)
        self.expandAll()

    def highlight_line(self, line: int) -> None:
        """Select the entry the cursor is in, without jumping."""
        current = None
        for it, item in zip(self._items, self._tree_items):
            if it.line > line:
                break
            current = item
        self.blockSignals(True)
        if current:
            self.setCurrentItem(current)
            self.scrollToItem(current)
        else:
            self.clearSelection()
        self.blockSignals(False)
