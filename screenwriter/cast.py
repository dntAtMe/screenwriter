"""Cast panel: story bible entries mentioned in the current document."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from .bible import CHARACTER, LOCATION, IndexEntry

ID_ROLE = Qt.ItemDataRole.UserRole


class CastPanel(QTreeWidget):
    openRequested = Signal(str)  # entry node id

    def __init__(self, icons: dict, parent=None):
        super().__init__(parent)
        self.icons = icons
        self.setHeaderHidden(True)
        self.setIndentation(12)
        self.setRootIsDecorated(False)
        self.itemClicked.connect(self._open)
        self.itemActivated.connect(self._open)
        self._last: list = []

    def set_cast(self, cast: list[tuple[IndexEntry, int]], has_bible: bool = True) -> None:
        key = [(e.node_id, e.name, n) for e, n in cast]
        if key == self._last and self.topLevelItemCount():
            return
        self._last = key
        self.clear()
        if not cast:
            hint = "No story bible names here yet." if has_bible else "Add characters and locations to the Story Bible to see them here."
            item = QTreeWidgetItem([hint])
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.addTopLevelItem(item)
            return
        bold = QFont(self.font())
        bold.setBold(True)
        for kind, label in ((CHARACTER, "Characters"), (LOCATION, "Locations")):
            entries = [(e, n) for e, n in cast if e.kind == kind]
            if not entries:
                continue
            header = QTreeWidgetItem([label])
            header.setFont(0, bold)
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.addTopLevelItem(header)
            for entry, count in entries:
                item = QTreeWidgetItem([f"{entry.name}   ·  {count}"])
                item.setIcon(0, self.icons[kind])
                item.setToolTip(0, entry.summary)
                item.setData(0, ID_ROLE, entry.node_id)
                header.addChild(item)
            header.setExpanded(True)

    def _open(self, item: QTreeWidgetItem) -> None:
        if node_id := item.data(0, ID_ROLE):
            self.openRequested.emit(node_id)
