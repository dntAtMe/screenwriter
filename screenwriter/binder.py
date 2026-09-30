"""The binder: a drag-and-drop tree of folders and documents."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QMenu,
    QMessageBox,
    QStyle,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
)

from .editors.board import NODE_MIME
from . import icons
from .bible import COLORS as BIBLE_COLORS, LABELS as BIBLE_LABELS
from .project import BIBLE_KINDS, BOARD, DOCUMENT_KINDS, FOLDER, NOTE, PROSE, SCREENPLAY, TRASH, Node, Project, walk

ID_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1
SYNOPSIS_ROLE = Qt.ItemDataRole.UserRole + 2
LABEL_ROLE = Qt.ItemDataRole.UserRole + 3

KIND_LABELS = {
    PROSE: "Prose Document", SCREENPLAY: "Screenplay", NOTE: "Note", BOARD: "Board",
    **BIBLE_LABELS, FOLDER: "Folder",
}
class PresenceDelegate(QStyledItemDelegate):
    """Draws a coloured initial at the right of documents other people have open."""

    def __init__(self, binder: "Binder"):
        super().__init__(binder)
        self.binder = binder

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(ID_ROLE) in self.binder.unread:  # changed by someone else since you last looked
            option.font.setBold(True)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        badges = self.binder.presence.get(index.data(ID_ROLE))
        if not badges:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(option.rect.height() - 4, 16)
        font = QFont(option.font)
        font.setPixelSize(int(size * 0.62))
        font.setBold(True)
        painter.setFont(font)
        x = option.rect.right() - 4
        for name, colour in reversed(badges):
            x -= size
            circle = QRectF(x, option.rect.center().y() - size / 2, size, size)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colour))
            painter.drawEllipse(circle)
            painter.setPen(QColor("white"))
            painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, name[:1].upper())
            x -= 2
        painter.restore()


DEFAULT_TITLES = {PROSE: "Untitled Chapter", SCREENPLAY: "Untitled Screenplay", NOTE: "Untitled Note", BOARD: "Untitled Board", **{k: f"New {label}" for k, label in BIBLE_LABELS.items()}, FOLDER: "New Folder"}


KIND_COLORS = {  # each kind of document has its own colour; folders and the Trash follow the theme
    PROSE: "#4f7cac",
    SCREENPLAY: "#c0563c",
    NOTE: "#5f9150",
    BOARD: "#8a63b8",
    **BIBLE_COLORS,
}


def kind_icons() -> dict:
    return {kind: icons.icon(kind, KIND_COLORS.get(kind)) for kind in (*KIND_COLORS, FOLDER, TRASH)}


class Binder(QTreeWidget):
    openRequested = Signal(str)       # node id
    corkboardRequested = Signal(str)  # folder id
    structureChanged = Signal()
    renamed = Signal(str, str)        # node id, new title
    deletedPermanently = Signal(list)  # node ids

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.setHeaderHidden(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setAnimated(True)
        self.setIndentation(16)
        self.setExpandsOnDoubleClick(False)  # double-clicking a folder opens its corkboard

        self.setObjectName("Binder")
        self.presence: dict[str, list[tuple[str, str]]] = {}  # node id -> [(name, colour)] of people there
        self.unread: set[str] = set()  # documents others changed that you haven't opened since
        self.setItemDelegate(PresenceDelegate(self))
        self.icons = kind_icons()  # shared with the corkboard, cast list and Go to Document

        self.itemClicked.connect(self._on_open)
        self.itemActivated.connect(self._on_open)
        self.itemChanged.connect(self._on_item_changed)
        self.itemExpanded.connect(lambda _: self.structureChanged.emit())
        self.itemCollapsed.connect(lambda _: self.structureChanged.emit())
        self.customContextMenuRequested.connect(self._context_menu)

    def refresh_icons(self) -> None:
        """Redraw icons in the theme's colours (called when the appearance changes)."""
        self.icons.update(kind_icons())
        root = self.invisibleRootItem()
        stack = [root.child(i) for i in range(root.childCount())]
        while stack:
            item = stack.pop()
            if item.data(0, KIND_ROLE) in self.icons:
                item.setIcon(0, self.icons[item.data(0, KIND_ROLE)])
            stack += [item.child(i) for i in range(item.childCount())]

    # --- model <-> tree ---------------------------------------------------------

    def set_presence(self, presence: dict[str, list[tuple[str, str]]]) -> None:
        """Who else has which document open: {node id: [(name, colour)]}."""
        if presence != self.presence:
            self.presence = presence
            self.viewport().update()

    def set_unread(self, unread: set[str]) -> None:
        if unread != self.unread:
            self.unread = set(unread)
            self.viewport().update()

    def load(self, project: Project) -> None:
        self.project = project
        self.blockSignals(True)
        self.clear()
        for node in project.root:
            self.addTopLevelItem(self._make_item(node))
        self._restore_expanded(self.invisibleRootItem(), project.root)
        self.blockSignals(False)

    def _make_item(self, node: Node) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.title])
        item.setData(0, ID_ROLE, node.id)
        item.setData(0, KIND_ROLE, node.kind)
        item.setIcon(0, self.icons[node.kind])
        item.setData(0, SYNOPSIS_ROLE, node.synopsis)
        item.setData(0, LABEL_ROLE, node.label)
        item.setToolTip(0, node.synopsis)
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled
        if node.kind != TRASH:
            flags |= Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsDragEnabled
        item.setFlags(flags)
        for child in node.children:
            item.addChild(self._make_item(child))
        return item

    def _restore_expanded(self, parent: QTreeWidgetItem, nodes: list[Node]) -> None:
        for i, node in enumerate(nodes):
            item = parent.child(i)
            item.setExpanded(node.expanded)
            self._restore_expanded(item, node.children)

    def to_nodes(self) -> list[Node]:
        root = self.invisibleRootItem()
        return [self._item_to_node(root.child(i)) for i in range(root.childCount())]

    def children_of(self, folder_id: str) -> list[Node]:
        folder = self.find_item(folder_id)
        return [self._item_to_node(folder.child(i)) for i in range(folder.childCount())] if folder else []

    def set_synopsis(self, node_id: str, text: str) -> None:
        if item := self.find_item(node_id):
            self.blockSignals(True)
            item.setData(0, SYNOPSIS_ROLE, text)
            item.setToolTip(0, text)
            self.blockSignals(False)
            self.structureChanged.emit()

    def set_label(self, node_id: str, label: str) -> None:
        if item := self.find_item(node_id):
            self.blockSignals(True)
            item.setData(0, LABEL_ROLE, label)
            self.blockSignals(False)
            self.structureChanged.emit()

    def reorder(self, folder_id: str, ids: list[str]) -> None:
        """Put a folder's children in the given order (corkboard drags)."""
        folder = self.find_item(folder_id)
        if folder is None:
            return
        current = [folder.child(i).data(0, ID_ROLE) for i in range(folder.childCount())]
        order = [i for i in ids if i in current] + [i for i in current if i not in ids]
        if order == current:
            return
        self.blockSignals(True)
        expanded = {}
        items = {}
        while folder.childCount():
            item = folder.takeChild(0)
            items[item.data(0, ID_ROLE)] = item
            expanded[item.data(0, ID_ROLE)] = item.isExpanded()
        for node_id in order:
            folder.addChild(items[node_id])
            items[node_id].setExpanded(expanded[node_id])
        self.blockSignals(False)
        self.structureChanged.emit()

    def trash(self, node_id: str) -> None:
        item = self.find_item(node_id)
        if item is None or item.data(0, KIND_ROLE) == TRASH or self._in_trash(item):
            return
        (item.parent() or self.invisibleRootItem()).removeChild(item)
        self._trash_item().addChild(item)
        self.structureChanged.emit()

    def find_item(self, node_id: str) -> QTreeWidgetItem | None:
        def search(item):
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, ID_ROLE) == node_id:
                    return child
                found = search(child)
                if found:
                    return found
            return None

        return search(self.invisibleRootItem())

    def _trash_item(self) -> QTreeWidgetItem:
        root = self.invisibleRootItem()
        return next(root.child(i) for i in range(root.childCount()) if root.child(i).data(0, KIND_ROLE) == TRASH)

    def _in_trash(self, item: QTreeWidgetItem) -> bool:
        while item is not None:
            if item.data(0, KIND_ROLE) == TRASH:
                return True
            item = item.parent()
        return False

    # --- actions --------------------------------------------------------------

    def add(self, kind: str, title: str | None = None, parent: QTreeWidgetItem | None = None,
            edit: bool = True, open_it: bool = True) -> str | None:
        """Add a node after the current item (or into it, for a folder), or into `parent`."""
        if self.project is None:
            return None
        node = self.project.new_node(kind, title or DEFAULT_TITLES[kind])
        item = self._make_item(node)
        current = self.currentItem()
        if parent is not None:
            parent.addChild(item)
            parent.setExpanded(True)
        elif current is None or self._in_trash(current):
            root = self.invisibleRootItem()
            root.insertChild(root.indexOfChild(self._trash_item()), item)
        elif current.data(0, KIND_ROLE) == FOLDER:
            current.addChild(item)
            current.setExpanded(True)
        else:
            owner = current.parent() or self.invisibleRootItem()
            owner.insertChild(owner.indexOfChild(current) + 1, item)
        self.setCurrentItem(item)
        self.structureChanged.emit()
        if kind in DOCUMENT_KINDS and open_it:
            self.openRequested.emit(node.id)
        if edit:
            self.editItem(item)
        return node.id

    def insert_node(self, node: Node, parent: QTreeWidgetItem | None = None) -> None:
        """Put an existing node (e.g. one restored from history) into the binder."""
        item = self._make_item(node)
        if parent is not None and not self._in_trash(parent):
            parent.addChild(item)
            parent.setExpanded(True)
        else:
            root = self.invisibleRootItem()
            root.insertChild(root.indexOfChild(self._trash_item()), item)
        self.setCurrentItem(item)
        self.structureChanged.emit()

    def folder(self, title: str) -> QTreeWidgetItem:
        """The top-level folder with this title, created (above the Trash) if missing."""
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.data(0, KIND_ROLE) == FOLDER and item.text(0) == title:
                return item
        node = self.project.new_node(FOLDER, title)
        item = self._make_item(node)
        root.insertChild(root.indexOfChild(self._trash_item()), item)
        return item

    def rename(self, node_id: str, title: str) -> None:
        """Rename without going through the inline editor (no renamed signal)."""
        if (item := self.find_item(node_id)) and item.text(0) != title:
            self.blockSignals(True)
            item.setText(0, title)
            self.blockSignals(False)
            self.structureChanged.emit()

    def rename_current(self) -> None:
        item = self.currentItem()
        if item and item.data(0, KIND_ROLE) != TRASH:
            self.editItem(item)

    def delete_current(self) -> None:
        item = self.currentItem()
        if item is None or item.data(0, KIND_ROLE) == TRASH:
            return
        parent = item.parent() or self.invisibleRootItem()
        if not self._in_trash(item):
            self.trash(item.data(0, ID_ROLE))
            return
        answer = QMessageBox.question(
            self, "Delete permanently",
            f"Permanently delete “{item.text(0)}” and everything inside it?\nThis cannot be undone.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        node = self._item_to_node(item)
        parent.removeChild(item)
        self.project.delete_files(node)
        self.deletedPermanently.emit([n.id for n in walk([node])])
        self.structureChanged.emit()

    def _item_to_node(self, item) -> Node:
        return Node(
            id=item.data(0, ID_ROLE), title=item.text(0), kind=item.data(0, KIND_ROLE),
            children=[self._item_to_node(item.child(i)) for i in range(item.childCount())],
            expanded=item.isExpanded(),
            synopsis=item.data(0, SYNOPSIS_ROLE) or "",
            label=item.data(0, LABEL_ROLE) or "",
        )

    # --- events -----------------------------------------------------------------

    def _on_open(self, item: QTreeWidgetItem) -> None:
        if item.data(0, KIND_ROLE) in DOCUMENT_KINDS:
            self.openRequested.emit(item.data(0, ID_ROLE))

    def mouseDoubleClickEvent(self, e):
        item = self.itemAt(e.position().toPoint())
        if item is not None and item.data(0, KIND_ROLE) == FOLDER:
            self.corkboardRequested.emit(item.data(0, ID_ROLE))
            return
        super().mouseDoubleClickEvent(e)

    def _on_item_changed(self, item: QTreeWidgetItem) -> None:
        if not item.text(0).strip():
            self.blockSignals(True)
            item.setText(0, "Untitled")
            self.blockSignals(False)
        self.renamed.emit(item.data(0, ID_ROLE), item.text(0))
        self.structureChanged.emit()

    def mimeData(self, items):
        """Binder drags also carry node ids, so boards can accept them."""
        data = super().mimeData(items)
        data.setData(NODE_MIME, ",".join(i.data(0, ID_ROLE) for i in items).encode())
        return data

    def dropEvent(self, event):
        super().dropEvent(event)
        # The trash always stays at the bottom of the top level.
        root = self.invisibleRootItem()
        trash = self._trash_item()
        if root.indexOfChild(trash) != root.childCount() - 1:
            expanded = trash.isExpanded()
            root.removeChild(trash)
            root.addChild(trash)
            trash.setExpanded(expanded)
        self.structureChanged.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.state() != QAbstractItemView.State.EditingState:
            self.delete_current()
            return
        super().keyPressEvent(e)

    def _context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item:
            self.setCurrentItem(item)
        menu = QMenu(self)
        for kind in (PROSE, SCREENPLAY, NOTE, BOARD, *BIBLE_KINDS, FOLDER):
            action = QAction(self.icons[kind], f"New {KIND_LABELS[kind]}", menu)
            action.triggered.connect(lambda _=False, k=kind: self.add(k))
            menu.addAction(action)
        if item and item.data(0, KIND_ROLE) == FOLDER:
            menu.addSeparator()
            menu.addAction("Open as Corkboard", lambda: self.corkboardRequested.emit(item.data(0, ID_ROLE)))
        if item and item.data(0, KIND_ROLE) != TRASH:
            menu.addSeparator()
            menu.addAction("Rename", self.rename_current)
            label = "Delete Permanently…" if self._in_trash(item) else "Move to Trash"
            menu.addAction(label, self.delete_current)
        menu.exec(self.viewport().mapToGlobal(pos))

