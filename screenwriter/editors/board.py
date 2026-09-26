"""Board editor: a canvas of cards for mind maps and corkboards.

Mouse:
  double-click empty space   new card
  double-click a card        edit its text (opens the document, for linked cards)
  drag                       move cards / rubber-band select
  Alt+drag card → card       connect them
  Space+drag, middle-drag    pan
  Ctrl+wheel, pinch          zoom
  drop from binder           card linked to that document

Keys (with a card selected):
  Tab          new child card, connected, to the right (mind-map style)
  Enter        new sibling card below
  F2           edit text  (Enter finishes, Shift+Enter new line, Esc stops)
  Delete       delete selected cards and links
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPalette,
    QPen,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QMenu,
)

from ..board import COLORS, DEFAULT_WIDTH, Board, Card, Link, new_id
from ..fountain import OutlineItem

NODE_MIME = "application/x-screenwriter-node"
ACCENT = QColor("#3d7eff")
TEXT_COLOR = QColor("#222222")
HISTORY_LIMIT = 200


class CardText(QGraphicsTextItem):
    def __init__(self, card: "CardItem"):
        super().__init__(card)
        self.card_item = card
        self.setDefaultTextColor(TEXT_COLOR)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)  # clicks go to the card until editing

    def keyPressEvent(self, e):
        key, shift = e.key(), e.modifiers() & Qt.KeyboardModifier.ShiftModifier
        if key == Qt.Key.Key_Escape or (key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not shift):
            self.card_item.stop_editing()
            return
        if key == Qt.Key.Key_Tab:
            self.card_item.stop_editing()
            self.card_item.editor.add_child(self.card_item)
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.card_item.stop_editing()


class CardItem(QGraphicsObject):
    PAD = 10
    MIN_H = 44

    def __init__(self, card: Card, editor: "BoardEditor"):
        super().__init__()
        self.card = card
        self.editor = editor
        self.links: list[LinkItem] = []
        self.editing = False
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPos(card.x, card.y)
        self.text_item = CardText(self)
        font = QFont()
        font.setPixelSize(14)
        self.text_item.setFont(font)
        self.text_item.setTextWidth(card.w - 2 * self.PAD)
        self.text_item.setPos(self.PAD, self.PAD - 2)
        self.text_item.setPlainText(card.text)
        self._h = self._content_height()
        self.text_item.document().contentsChanged.connect(self._on_text_changed)

    # geometry
    def _content_height(self) -> float:
        return max(self.MIN_H, self.text_item.boundingRect().height() + 2 * self.PAD - 4)

    def rect(self) -> QRectF:
        return QRectF(0, 0, self.card.w, self._h)

    def scene_rect(self) -> QRectF:
        return self.rect().translated(self.pos())

    def boundingRect(self) -> QRectF:
        return self.rect().adjusted(-3, -3, 5, 6)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 40))
        painter.drawRoundedRect(r.translated(1.5, 2.5), 8, 8)
        painter.setBrush(QColor(COLORS[self.card.color]))
        painter.setPen(QPen(ACCENT, 2.5) if self.isSelected() else QPen(QColor(0, 0, 0, 50), 1))
        painter.drawRoundedRect(r, 8, 8)
        if self.card.doc:
            painter.setPen(QColor(0, 0, 0, 120))
            font = QFont()
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(r.adjusted(0, 3, -7, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, "↗")

    def _on_text_changed(self) -> None:
        self.card.text = self.text_item.toPlainText()
        h = self._content_height()
        if h != self._h:
            self.prepareGeometryChange()
            self._h = h
            for link in self.links:
                link.update_path()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.card.x, self.card.y = self.pos().x(), self.pos().y()
            for link in self.links:
                link.update_path()
        return super().itemChange(change, value)

    # editing
    def start_editing(self) -> None:
        self.editing = True
        self.text_item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.text_item.setFocus()
        cursor = self.text_item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.text_item.setTextCursor(cursor)

    def stop_editing(self) -> None:
        if not self.editing:
            return
        self.editing = False
        self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.text_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        cursor = self.text_item.textCursor()
        cursor.clearSelection()
        self.text_item.setTextCursor(cursor)
        self.setSelected(True)
        self.editor.setFocus()
        self.editor.commit()

    def mouseDoubleClickEvent(self, e):
        if self.card.doc:
            self.editor.openRequested.emit(self.card.doc)
        else:
            self.start_editing()


class LinkItem(QGraphicsPathItem):
    def __init__(self, a: CardItem, b: CardItem):
        super().__init__()
        self.a, self.b = a, b
        a.links.append(self)
        b.links.append(self)
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.update_path()

    def detach(self) -> None:
        for card in (self.a, self.b):
            if self in card.links:
                card.links.remove(self)

    def update_path(self) -> None:
        ra, rb = self.a.scene_rect(), self.b.scene_rect()
        path = QPainterPath()
        if rb.left() > ra.right() or rb.right() < ra.left():  # side by side: horizontal curve
            right = rb.left() > ra.right()
            p1 = QPointF(ra.right() if right else ra.left(), ra.center().y())
            p2 = QPointF(rb.left() if right else rb.right(), rb.center().y())
            dx = (p2.x() - p1.x()) / 2
            path.moveTo(p1)
            path.cubicTo(QPointF(p1.x() + dx, p1.y()), QPointF(p2.x() - dx, p2.y()), p2)
        else:  # stacked: vertical curve
            down = rb.top() > ra.bottom()
            p1 = QPointF(ra.center().x(), ra.bottom() if down else ra.top())
            p2 = QPointF(rb.center().x(), rb.top() if down else rb.bottom())
            dy = (p2.y() - p1.y()) / 2
            path.moveTo(p1)
            path.cubicTo(QPointF(p1.x(), p1.y() + dy), QPointF(p2.x(), p2.y() - dy), p2)
        self.setPath(path)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = ACCENT if self.isSelected() else QColor(140, 140, 150)
        painter.setPen(QPen(color, 2.5 if self.isSelected() else 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())


class BoardScene(QGraphicsScene):
    GRID = 24
    plain_background = False  # exports: white, no grid

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        if self.plain_background:
            painter.fillRect(rect, Qt.GlobalColor.white)
            return
        pal = self.palette()
        painter.fillRect(rect, pal.color(QPalette.ColorRole.Base))
        dot = QColor(pal.color(QPalette.ColorRole.Text))
        dot.setAlpha(45)
        painter.setPen(QPen(dot, 1.5))
        g = self.GRID
        x0 = int(rect.left()) - int(rect.left()) % g
        y0 = int(rect.top()) - int(rect.top()) % g
        points = [QPointF(x, y) for x in range(x0, int(rect.right()) + g, g) for y in range(y0, int(rect.bottom()) + g, g)]
        if len(points) < 20000:
            painter.drawPoints(points)


class BoardEditor(QGraphicsView):
    textChanged = Signal()
    statsChanged = Signal()
    cursorPositionChanged = Signal()
    openRequested = Signal(str)  # binder node id

    def __init__(self, title_for=lambda node_id: "", parent=None):
        super().__init__(parent)
        self.title_for = title_for
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setScene(BoardScene(self))
        self.scene().setSceneRect(-4000, -4000, 8000, 8000)
        self.scene().selectionChanged.connect(self.cursorPositionChanged)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setAcceptDrops(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # pan instead
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards: dict[str, CardItem] = {}
        self.link_items: list[LinkItem] = []
        self._history: list[str] = []
        self._index = -1
        self._saved = ""
        self._linking: tuple[CardItem, QGraphicsPathItem] | None = None
        self._pan_from = None
        self._space = False
        self._needs_centering = False

    # --- document API ---------------------------------------------------------------

    def board(self) -> Board:
        return Board(
            [item.card for item in self.cards.values()],
            [Link(l.a.card.id, l.b.card.id) for l in self.link_items],
        )

    def set_text(self, text: str) -> None:
        self._load(Board.from_json(text))
        normalized = self.text()
        self._history, self._index, self._saved = [normalized], 0, normalized
        self._needs_centering = True
        self._center_content()

    def _center_content(self) -> None:
        """Show the whole board: centred, zoomed out if it doesn't fit (never zoomed in)."""
        self.resetTransform()
        if not self.cards:
            self.centerOn(0, 0)
            return
        rect = self.scene().itemsBoundingRect().adjusted(-40, -40, 40, 40)
        view = self.viewport().rect()
        if rect.width() > view.width() or rect.height() > view.height():
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(rect.center())

    def showEvent(self, e):
        super().showEvent(e)
        if self._needs_centering:  # the view only has its real size once shown
            self._needs_centering = False
            QTimer.singleShot(0, self._center_content)

    def text(self) -> str:
        return self.board().to_json()

    def is_modified(self) -> bool:
        return self.text() != self._saved

    def mark_saved(self) -> None:
        self._saved = self.text()

    def stats(self) -> str:
        n, m = len(self.cards), len(self.link_items)
        return f"{n} card{'s' if n != 1 else ''} · {m} link{'s' if m != 1 else ''}"

    def outline(self) -> list[OutlineItem]:
        return [
            OutlineItem(depth, (c.text.strip().splitlines() or ["(empty card)"])[0], i, "card")
            for i, (depth, c) in enumerate(self.board().tree_order())
        ]

    def search_text(self) -> str:
        return self.board().search_text()

    def current_line(self) -> int:
        selected = [i.card.id for i in self.scene().selectedItems() if isinstance(i, CardItem)]
        order = [c.id for _, c in self.board().tree_order()]
        return order.index(selected[0]) if len(selected) == 1 else -1

    def jump_to_line(self, line: int) -> None:
        order = self.board().tree_order()
        if 0 <= line < len(order):
            item = self.cards[order[line][1].id]
            self.scene().clearSelection()
            item.setSelected(True)
            self.centerOn(item)
            self.setFocus()

    def reveal(self, pos: int, length: int = 0) -> None:
        self.jump_to_line(self.search_text()[:pos].count("\n"))

    def selected_text(self) -> str:
        return ""

    def zoom(self, steps: int) -> None:
        factor = 1.15 ** steps
        scale = self.transform().m11() * factor
        if 0.2 <= scale <= 4:
            self.scale(factor, factor)

    def export_image(self, path: str) -> None:
        """PNG or PDF of the whole board on a plain white background."""
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPdfWriter

        self._finish_editing()
        selected = self.scene().selectedItems()
        self.scene().clearSelection()
        rect = self.scene().itemsBoundingRect().adjusted(-32, -32, 32, 32)
        scene = self.scene()
        scene.plain_background = True
        try:
            if path.lower().endswith(".pdf"):
                writer = QPdfWriter(path)
                writer.setResolution(72)
                writer.setPageLayout(QPageLayout(QPageSize(rect.size(), QPageSize.Unit.Point),
                                                 QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))
                painter = QPainter(writer)
                scene.render(painter, QRectF(0, 0, rect.width(), rect.height()), rect)
                painter.end()
            else:
                image = QImage((rect.size() * 2).toSize(), QImage.Format.Format_ARGB32)
                image.fill(Qt.GlobalColor.white)
                painter = QPainter(image)
                painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
                scene.render(painter, QRectF(image.rect()), rect)
                painter.end()
                image.save(path)
        finally:
            scene.plain_background = False
            for item in selected:
                item.setSelected(True)

    # --- undo (whole-board snapshots; boards are small) ------------------------------

    def commit(self) -> None:
        """Record the board as an undo step after a change completes."""
        state = self.text()
        if self._history and state == self._history[self._index]:
            return
        del self._history[self._index + 1 :]
        self._history.append(state)
        del self._history[:-HISTORY_LIMIT]
        self._index = len(self._history) - 1
        self.textChanged.emit()
        self.statsChanged.emit()

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._history) - 1

    def undo(self) -> None:
        self._finish_editing()
        if self.can_undo():
            self._index -= 1
            self._restore()

    def redo(self) -> None:
        if self.can_redo():
            self._index += 1
            self._restore()

    def _restore(self) -> None:
        selected = {i.card.id for i in self.scene().selectedItems() if isinstance(i, CardItem)}
        self._load(Board.from_json(self._history[self._index]))
        for card_id in selected & self.cards.keys():
            self.cards[card_id].setSelected(True)
        self.textChanged.emit()
        self.statsChanged.emit()

    # --- building -------------------------------------------------------------------

    def _load(self, board: Board) -> None:
        self.scene().clear()
        self.cards, self.link_items = {}, []
        for card in board.cards:
            self._add_card_item(card)
        for link in board.links:
            self._add_link_item(self.cards[link.a], self.cards[link.b])

    def _add_card_item(self, card: Card) -> CardItem:
        item = CardItem(card, self)
        self.scene().addItem(item)
        self.cards[card.id] = item
        return item

    def _add_link_item(self, a: CardItem, b: CardItem) -> LinkItem | None:
        if a is b or any({l.a, l.b} == {a, b} for l in self.link_items):
            return None
        link = LinkItem(a, b)
        self.scene().addItem(link)
        self.link_items.append(link)
        return link

    def add_card(self, x: float, y: float, text: str = "", doc: str | None = None, color: str = "yellow",
                 edit: bool = True) -> CardItem:
        self._finish_editing()
        item = self._add_card_item(Card(new_id(), x, y, text, color, DEFAULT_WIDTH, doc))
        self.scene().clearSelection()
        item.setSelected(True)
        self.ensureVisible(item.scene_rect(), 40, 40)
        if edit:
            item.start_editing()
        else:
            self.commit()
        return item

    def connect_cards(self, a: CardItem, b: CardItem) -> None:
        if self._add_link_item(a, b):
            self.commit()

    def _children(self, item: CardItem) -> list[CardItem]:
        return [l.b for l in item.links if l.a is item]

    def _parent(self, item: CardItem) -> CardItem | None:
        return next((l.a for l in item.links if l.b is item), None)

    def add_child(self, item: CardItem) -> CardItem:
        """Mind-map step: a new card to the right, connected, below existing children."""
        kids = [k for k in self._children(item) if k.pos().x() > item.pos().x()]
        x = item.pos().x() + item.card.w + 70
        y = max((k.scene_rect().bottom() + 18 for k in kids), default=item.pos().y())
        child = self.add_card(x, y, color=item.card.color)
        self._add_link_item(item, child)
        return child

    def add_sibling(self, item: CardItem) -> CardItem:
        parent = self._parent(item)
        group = self._children(parent) if parent else [item]
        y = max(k.scene_rect().bottom() for k in group) + 18
        sibling = self.add_card(item.pos().x(), y, color=item.card.color)
        if parent:
            self._add_link_item(parent, sibling)
        return sibling

    def delete_selected(self) -> None:
        self._finish_editing()
        selected = self.scene().selectedItems()
        doomed_cards = [i for i in selected if isinstance(i, CardItem)]
        doomed_links = {i for i in selected if isinstance(i, LinkItem)}
        for card in doomed_cards:
            doomed_links.update(card.links)
        for link in doomed_links:
            link.detach()
            self.scene().removeItem(link)
            self.link_items.remove(link)
        for card in doomed_cards:
            self.scene().removeItem(card)
            del self.cards[card.card.id]
        if selected:
            self.commit()

    def set_color(self, color: str) -> None:
        for item in self.scene().selectedItems():
            if isinstance(item, CardItem):
                item.card.color = color
                item.update()
        self.commit()

    def _selected_cards(self) -> list[CardItem]:
        return [i for i in self.scene().selectedItems() if isinstance(i, CardItem)]

    def _editing_card(self) -> CardItem | None:
        return next((c for c in self.cards.values() if c.editing), None)

    def _finish_editing(self) -> None:
        if card := self._editing_card():
            card.stop_editing()

    def _card_at(self, view_pos) -> CardItem | None:
        for item in self.items(view_pos):
            while item is not None and not isinstance(item, CardItem):
                item = item.parentItem()
            if item is not None:
                return item
        return None

    # --- mouse ------------------------------------------------------------------------

    def mouseDoubleClickEvent(self, e):
        if self._card_at(e.position().toPoint()) is None and e.button() == Qt.MouseButton.LeftButton:
            p = self.mapToScene(e.position().toPoint())
            self.add_card(p.x() - DEFAULT_WIDTH / 2, p.y() - 22)
            return
        super().mouseDoubleClickEvent(e)

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        if e.button() == Qt.MouseButton.MiddleButton or (self._space and e.button() == Qt.MouseButton.LeftButton):
            self._pan_from = pos
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        card = self._card_at(pos)
        if card and e.button() == Qt.MouseButton.LeftButton and e.modifiers() & Qt.KeyboardModifier.AltModifier:
            line = QGraphicsPathItem()
            line.setPen(QPen(ACCENT, 2, Qt.PenStyle.DashLine))
            self.scene().addItem(line)
            self._linking = (card, line)
            return
        if card is None or not card.editing:
            self._finish_editing()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._pan_from is not None:
            delta = pos - self._pan_from
            self._pan_from = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        if self._linking:
            card, line = self._linking
            path = QPainterPath(card.scene_rect().center())
            path.lineTo(self.mapToScene(pos))
            line.setPath(path)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan_from is not None:
            self._pan_from = None
            self.viewport().unsetCursor()
            return
        if self._linking:
            card, line = self._linking
            self.scene().removeItem(line)
            self._linking = None
            target = self._card_at(e.position().toPoint())
            if target and target is not card:
                self.connect_cards(card, target)
            return
        super().mouseReleaseEvent(e)
        self.commit()  # a finished move

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1 if e.angleDelta().y() > 0 else -1)
            return
        super().wheelEvent(e)

    def viewportEvent(self, e):
        if e.type() == e.Type.NativeGesture and e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            factor = 1 + e.value()
            scale = self.transform().m11() * factor
            if 0.2 <= scale <= 4:
                self.scale(factor, factor)
            return True
        return super().viewportEvent(e)

    def contextMenuEvent(self, e):
        card = self._card_at(e.pos())
        if card and not card.isSelected():
            self.scene().clearSelection()
            card.setSelected(True)
        menu = QMenu(self)
        if card:
            if card.card.doc:
                menu.addAction("Open Linked Document", lambda: self.openRequested.emit(card.card.doc))
            menu.addAction("Edit Text", card.start_editing)
            menu.addAction("New Child Card", lambda: self.add_child(card))
            colors = menu.addMenu("Color")
            for name in COLORS:
                action = QAction(name.title(), colors)
                action.triggered.connect(lambda _=False, n=name: self.set_color(n))
                colors.addAction(action)
        else:
            p = self.mapToScene(e.pos())
            menu.addAction("New Card", lambda: self.add_card(p.x() - DEFAULT_WIDTH / 2, p.y() - 22))
        selected = self._selected_cards()
        if len(selected) == 2:
            menu.addAction("Connect Cards", lambda: self.connect_cards(*selected))
        if self.scene().selectedItems():
            menu.addSeparator()
            menu.addAction("Delete", self.delete_selected)
        menu.exec(e.globalPos())

    # --- keys -------------------------------------------------------------------------

    def event(self, e):
        # Tab would otherwise move widget focus; on a board it makes a child card.
        if e.type() == e.Type.KeyPress and e.key() == Qt.Key.Key_Tab and not self._editing_card():
            self.keyPressEvent(e)
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if self._editing_card():
            return super().keyPressEvent(e)
        key = e.key()
        selected = self._selected_cards()
        if key == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if key == Qt.Key.Key_Tab and len(selected) == 1:
            self.add_child(selected[0])
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and len(selected) == 1:
            self.add_sibling(selected[0])
            return
        if key == Qt.Key.Key_F2 and len(selected) == 1:
            return selected[0].start_editing()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            return self.delete_selected()
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = False
            self.viewport().unsetCursor()
            return
        super().keyReleaseEvent(e)

    # --- drops from the binder ------------------------------------------------------------

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(NODE_MIME):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(NODE_MIME):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(NODE_MIME):
            return super().dropEvent(e)
        p = self.mapToScene(e.position().toPoint())
        ids = bytes(e.mimeData().data(NODE_MIME)).decode().split(",")
        for i, node_id in enumerate(filter(None, ids)):
            self.add_card(p.x() - DEFAULT_WIDTH / 2, p.y() - 22 + i * 64, self.title_for(node_id), doc=node_id,
                          color="blue", edit=False)
        e.acceptProposedAction()
