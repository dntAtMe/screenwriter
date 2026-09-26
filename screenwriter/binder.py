"""The binder: a drag-and-drop tree of folders and documents."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QMenu, QMessageBox, QStyle, QTreeWidget, QTreeWidgetItem

from .editors.board import NODE_MIME
from .project import BOARD, DOCUMENT_KINDS, FOLDER, NOTE, PROSE, SCREENPLAY, TRASH, Node, Project, walk

ID_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1

KIND_LABELS = {PROSE: "Prose Document", SCREENPLAY: "Screenplay", NOTE: "Note", BOARD: "Board", FOLDER: "Folder"}
DEFAULT_TITLES = {PROSE: "Untitled Chapter", SCREENPLAY: "Untitled Screenplay", NOTE: "Untitled Note", BOARD: "Untitled Board", FOLDER: "New Folder"}


def _letter_icon(letter: str, color: str) -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(3, 3, 26, 26, 6, 6)
    font = QFont()
    font.setPixelSize(17)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, letter)
    p.end()
    return QIcon(pm)


class Binder(QTreeWidget):
    openRequested = Signal(str)       # node id
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

        style = self.style()
        self.icons = {
            FOLDER: style.standardIcon(QStyle.StandardPixmap.SP_DirIcon),
            TRASH: style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon),
            PROSE: _letter_icon("P", "#4f7cac"),
            SCREENPLAY: _letter_icon("S", "#b5563c"),
            NOTE: _letter_icon("N", "#6b8f4e"),
            BOARD: _letter_icon("B", "#8a63b8"),
        }

        self.itemClicked.connect(self._on_open)
        self.itemActivated.connect(self._on_open)
        self.itemChanged.connect(self._on_item_changed)
        self.itemExpanded.connect(lambda _: self.structureChanged.emit())
        self.itemCollapsed.connect(lambda _: self.structureChanged.emit())
        self.customContextMenuRequested.connect(self._context_menu)

    # --- model <-> tree ---------------------------------------------------------

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
        def convert(item: QTreeWidgetItem) -> Node:
            return Node(
                id=item.data(0, ID_ROLE),
                title=item.text(0),
                kind=item.data(0, KIND_ROLE),
                children=[convert(item.child(i)) for i in range(item.childCount())],
                expanded=item.isExpanded(),
            )

        root = self.invisibleRootItem()
        return [convert(root.child(i)) for i in range(root.childCount())]

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

    def add(self, kind: str) -> str | None:
        if self.project is None:
            return None
        node = self.project.new_node(kind, DEFAULT_TITLES[kind])
        item = self._make_item(node)
        current = self.currentItem()
        if current is None or self._in_trash(current):
            root = self.invisibleRootItem()
            root.insertChild(root.indexOfChild(self._trash_item()), item)
        elif current.data(0, KIND_ROLE) == FOLDER:
            current.addChild(item)
            current.setExpanded(True)
        else:
            parent = current.parent() or self.invisibleRootItem()
            parent.insertChild(parent.indexOfChild(current) + 1, item)
        self.setCurrentItem(item)
        self.structureChanged.emit()
        if kind in DOCUMENT_KINDS:
            self.openRequested.emit(node.id)
        self.editItem(item)
        return node.id

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
            parent.removeChild(item)
            self._trash_item().addChild(item)
            self.structureChanged.emit()
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
        )

    # --- events -----------------------------------------------------------------

    def _on_open(self, item: QTreeWidgetItem) -> None:
        if item.data(0, KIND_ROLE) in DOCUMENT_KINDS:
            self.openRequested.emit(item.data(0, ID_ROLE))

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
        for kind in (PROSE, SCREENPLAY, NOTE, BOARD, FOLDER):
            action = QAction(self.icons[kind], f"New {KIND_LABELS[kind]}", menu)
            action.triggered.connect(lambda _=False, k=kind: self.add(k))
            menu.addAction(action)
        if item and item.data(0, KIND_ROLE) != TRASH:
            menu.addSeparator()
            menu.addAction("Rename", self.rename_current)
            label = "Delete Permanently…" if self._in_trash(item) else "Move to Trash"
            menu.addAction(label, self.delete_current)
        menu.exec(self.viewport().mapToGlobal(pos))

