"""Corkboard: a folder's contents as index cards.

Cards show the title, synopsis, colour label and word count. Drag cards to
reorder the binder; click a selected card (or press F2) to edit its synopsis,
double-click to open it.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QStyle,
    QStyledItemDelegate,
)

from .bible import entry_summary
from .editors.common import word_count
from .fountain import OutlineItem
from .bible import LABELS as BIBLE_LABELS
from .project import BIBLE_KINDS, BOARD, FOLDER, NOTE, PROSE, SCREENPLAY, Node

LABELS = {
    "red": "#d9534f",
    "orange": "#e8913a",
    "yellow": "#d9b52c",
    "green": "#4fa35a",
    "blue": "#4a86d4",
    "purple": "#9467cc",
}
ID_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1
SYNOPSIS_ROLE = Qt.ItemDataRole.UserRole + 2
LABEL_ROLE = Qt.ItemDataRole.UserRole + 3
FOOTER_ROLE = Qt.ItemDataRole.UserRole + 4
PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 5  # summary shown when there's no synopsis

CARD = QSize(232, 156)
PAD = 12


class CardDelegate(QStyledItemDelegate):
    def __init__(self, view: "CorkboardView"):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index) -> QSize:
        return self.view.card_size()

    def _rects(self, rect: QRect) -> tuple[QRect, QRect, QRect, QRect]:
        card = rect.adjusted(6, 6, -6, -6)
        title = QRect(card.left() + PAD, card.top() + 10, card.width() - 2 * PAD, 22)
        footer = QRect(card.left() + PAD, card.bottom() - 22, card.width() - 2 * PAD, 16)
        synopsis = QRect(card.left() + PAD, title.bottom() + 8, card.width() - 2 * PAD, footer.top() - title.bottom() - 12)
        return card, title, synopsis, footer

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card, title_rect, synopsis_rect, footer_rect = self._rects(option.rect)
        dark = self.view.palette().color(QPalette.ColorRole.Base).lightness() < 128
        paper = QColor("#34322e") if dark else QColor("#fffdf6")
        ink = QColor("#ece8df") if dark else QColor("#2b2a28")
        faint = QColor(ink)
        faint.setAlpha(130)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60 if dark else 35))
        painter.drawRoundedRect(card.translated(1, 2), 6, 6)
        painter.setBrush(paper)
        selected = option.state & QStyle.StateFlag.State_Selected
        painter.setPen(QPen(QColor("#3d7eff"), 2.5) if selected else QPen(QColor(0, 0, 0, 40), 1))
        painter.drawRoundedRect(card, 6, 6)

        if label := index.data(LABEL_ROLE):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(LABELS.get(label, "#888")))
            painter.drawRoundedRect(QRect(card.left() + 1, card.top() + 1, card.width() - 2, 6), 3, 3)

        # title, with the binder icon
        icon = self.view.icons.get(index.data(KIND_ROLE))
        if icon:
            icon.paint(painter, QRect(title_rect.left(), title_rect.top() + 3, 16, 16))
        bold = QFont(self.view.font())
        bold.setBold(True)
        bold.setPointSizeF(bold.pointSizeF() + 1)
        painter.setFont(bold)
        painter.setPen(ink)
        text_rect = title_rect.adjusted(22, 0, 0, 0)
        title = painter.fontMetrics().elidedText(index.data(Qt.ItemDataRole.DisplayRole), Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)

        # index-card rule under the title
        rule = QColor("#d9534f")
        rule.setAlpha(110)
        painter.setPen(QPen(rule, 1))
        painter.drawLine(card.left() + 6, title_rect.bottom() + 4, card.right() - 6, title_rect.bottom() + 4)

        # synopsis, or a hint
        synopsis = index.data(SYNOPSIS_ROLE) or ""
        body = QFont(self.view.font())
        painter.setFont(body)
        if synopsis:
            painter.setPen(ink)
            text = synopsis
        else:
            body.setItalic(True)
            painter.setFont(body)
            painter.setPen(faint)
            text = index.data(PLACEHOLDER_ROLE) or "Click to add a synopsis"
        painter.setClipRect(synopsis_rect)
        painter.drawText(synopsis_rect, Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop, text)
        painter.setClipping(False)

        small = QFont(self.view.font())
        small.setPointSizeF(small.pointSizeF() - 1.5)
        painter.setFont(small)
        painter.setPen(faint)
        painter.drawText(footer_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, index.data(FOOTER_ROLE) or "")
        painter.restore()

    # synopsis editing
    def createEditor(self, parent, option, index):
        editor = QPlainTextEdit(parent)
        editor.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        editor.setPlaceholderText("Synopsis (Enter to save, Shift+Enter for a new line)")
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index) -> None:
        editor.setPlainText(index.data(SYNOPSIS_ROLE) or "")
        editor.selectAll()

    def setModelData(self, editor, model, index) -> None:
        model.setData(index, editor.toPlainText().strip(), SYNOPSIS_ROLE)

    def updateEditorGeometry(self, editor, option, index) -> None:
        _, _, synopsis, footer = self._rects(option.rect)
        editor.setGeometry(synopsis.adjusted(-4, -4, 4, footer.height()))

    def eventFilter(self, editor, event):
        if (
            event.type() == event.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)
            return True
        return super().eventFilter(editor, event)


class CorkboardView(QListWidget):
    textChanged = Signal()
    statsChanged = Signal()
    cursorPositionChanged = Signal()
    openRequested = Signal(str)

    def __init__(self, binder, folder_id: str, text_of: Callable[[Node], str], parent=None):
        super().__init__(parent)
        self.binder = binder
        self.node_id = folder_id
        self.text_of = text_of
        self.setObjectName("Corkboard")
        self.icons = binder.icons
        self._scale = 1.0
        self._updating = False
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSpacing(6)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setItemDelegate(CardDelegate(self))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.itemDoubleClicked.connect(lambda item: self._open(item))
        self.itemChanged.connect(self._on_item_changed)
        self.itemSelectionChanged.connect(self.cursorPositionChanged)
        self.model().rowsMoved.connect(self._apply_order)
        self.refresh()

    # --- cards ------------------------------------------------------------------------

    def card_size(self) -> QSize:
        return QSize(int(CARD.width() * self._scale), int(CARD.height() * self._scale))

    def refresh(self) -> None:
        if self._updating:
            return
        self._updating = True
        selected = {i.data(ID_ROLE) for i in self.selectedItems()}
        current = self.currentItem().data(ID_ROLE) if self.currentItem() else None
        self.blockSignals(True)
        self.clear()
        for node in self.binder.children_of(self.node_id):
            item = QListWidgetItem(node.title)
            item.setData(ID_ROLE, node.id)
            item.setData(KIND_ROLE, node.kind)
            item.setData(SYNOPSIS_ROLE, node.synopsis)
            item.setData(LABEL_ROLE, node.label)
            item.setData(FOOTER_ROLE, self._footer(node))
            if node.kind in BIBLE_KINDS and not node.synopsis:
                item.setData(PLACEHOLDER_ROLE, entry_summary(self.text_of(node)))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsDragEnabled)
            self.addItem(item)
            item.setSelected(node.id in selected)
            if node.id == current:
                self.setCurrentItem(item, self.selectionModel().SelectionFlag.NoUpdate)
        self.blockSignals(False)
        self._updating = False
        self.statsChanged.emit()

    def _footer(self, node: Node) -> str:
        if node.kind == FOLDER:
            n = len(node.children)
            return f"{n} item{'s' if n != 1 else ''}"
        if node.kind in (PROSE, NOTE, SCREENPLAY):
            n = word_count(self.text_of(node))
            return f"{n:,} word{'s' if n != 1 else ''}"
        return {BOARD: "Board", **BIBLE_LABELS}.get(node.kind, "")

    def ids(self) -> list[str]:
        return [self.item(i).data(ID_ROLE) for i in range(self.count())]

    def _apply_order(self, *_) -> None:
        if not self._updating:
            self._updating = True
            self.binder.reorder(self.node_id, self.ids())
            self._updating = False

    def dropEvent(self, event):
        super().dropEvent(event)
        self._apply_order()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating:
            return
        self._updating = True
        self.binder.set_synopsis(item.data(ID_ROLE), item.data(SYNOPSIS_ROLE) or "")
        self._updating = False

    def _open(self, item: QListWidgetItem) -> None:
        if item.data(KIND_ROLE) == FOLDER:
            self.binder.corkboardRequested.emit(item.data(ID_ROLE))
        else:
            self.openRequested.emit(item.data(ID_ROLE))

    def keyPressEvent(self, e):
        items = self.selectedItems()
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.state() != QAbstractItemView.State.EditingState:
            if self.currentItem():
                self._open(self.currentItem())
            return
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and items and self.state() != QAbstractItemView.State.EditingState:
            for item in items:
                self.binder.trash(item.data(ID_ROLE))
            return
        super().keyPressEvent(e)

    def _context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        menu = QMenu(self)
        if item:
            if not item.isSelected():
                self.clearSelection()
                item.setSelected(True)
            self.setCurrentItem(item)
            menu.addAction("Open", lambda: self._open(item))
            menu.addAction("Edit Synopsis", lambda: self.editItem(item))
            menu.addAction("Rename…", lambda: self._rename(item))
            labels = menu.addMenu("Label")
            for name in [""] + list(LABELS):
                action = QAction(name.title() or "None", labels)
                action.triggered.connect(lambda _=False, n=name: self._set_label(n))
                labels.addAction(action)
            menu.addSeparator()
        new = menu.addMenu("New")
        for kind, label in ((PROSE, "Prose Document"), (SCREENPLAY, "Screenplay"), (NOTE, "Note"),
                            *BIBLE_LABELS.items(), (FOLDER, "Folder")):
            action = QAction(self.icons[kind], label, new)
            action.triggered.connect(lambda _=False, k=kind: self.add_card(k))
            new.addAction(action)
        if item:
            menu.addSeparator()
            menu.addAction("Move to Trash", lambda: [self.binder.trash(i.data(ID_ROLE)) for i in self.selectedItems()])
        menu.exec(self.viewport().mapToGlobal(pos))

    def _rename(self, item: QListWidgetItem) -> None:
        title, ok = QInputDialog.getText(self, "Rename", "Title:", text=item.text())
        if ok and title.strip():
            self.binder.find_item(item.data(ID_ROLE)).setText(0, title.strip())  # goes through binder rename

    def _set_label(self, label: str) -> None:
        for item in self.selectedItems():
            self.binder.set_label(item.data(ID_ROLE), label)

    def add_card(self, kind: str, title: str | None = None) -> str | None:
        """Add a document or folder to this folder; asks for a title unless given."""
        if title is None:
            title, ok = QInputDialog.getText(self, "New Card", "Title:")
            if not ok:
                return None
        folder = self.binder.find_item(self.node_id)
        node_id = self.binder.add(kind, title.strip() or None, parent=folder, edit=False, open_it=False)
        if node_id in self.ids():
            self.setCurrentRow(self.ids().index(node_id))
        return node_id

    # --- document API (a view, nothing to save) ----------------------------------------------

    def text(self) -> str:
        return ""

    def is_modified(self) -> bool:
        return False

    def mark_saved(self) -> None:
        pass

    def stats(self) -> str:
        n = self.count()
        return f"Corkboard · {n} card{'s' if n != 1 else ''}"

    def outline(self) -> list[OutlineItem]:
        return [OutlineItem(0, self.item(i).text(), i, "card") for i in range(self.count())]

    def jump_to_line(self, line: int) -> None:
        if 0 <= line < self.count():
            self.setCurrentRow(line)
            self.scrollToItem(self.item(line))

    def current_line(self) -> int:
        return self.currentRow()

    def search_text(self) -> str:
        return ""

    def reveal(self, pos: int, length: int = 0) -> None:
        pass

    def selected_text(self) -> str:
        return ""

    def replace_all(self, text: str) -> None:
        pass

    def undo(self) -> None:
        pass

    def redo(self) -> None:
        pass

    def zoom(self, steps: int) -> None:
        self._scale = max(0.7, min(1.8, self._scale * (1.1 ** steps)))
        self.scheduleDelayedItemsLayout()
        self.viewport().update()
