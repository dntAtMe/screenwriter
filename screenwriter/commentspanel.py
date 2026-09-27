"""The Comments tab of the side panel: a card per comment, with its replies."""

from __future__ import annotations

import html
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import people
from .comments import Comment


def _when(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso).astimezone()
    except ValueError:
        return ""
    return f"{t:%H:%M}" if t.date() == datetime.now().astimezone().date() else f"{t:%d %b %H:%M}"


class CommentCard(QFrame):
    clicked = Signal(str)

    def __init__(self, comment: Comment, title: str, found: bool, active: bool, panel: "CommentsPanel"):
        super().__init__()
        self.comment_id = comment.id
        self.setObjectName("comment_card")
        border = "palette(highlight)" if active else "rgba(128,128,128,0.35)"
        faded = "opacity: 0.6;" if comment.resolved else ""
        self.setStyleSheet(f"#comment_card {{ border: 1px solid {border}; border-radius: 6px; {faded} }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        def line(author: str, time: str, text: str) -> QLabel:
            colour = people.colour_for(author)
            label = QLabel(f'<span style="color:{colour}"><b>{html.escape(author)}</b></span> '
                           f'<span style="color:gray">{_when(time)}</span><br>{html.escape(text).replace(chr(10), "<br>")}')
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return label

        where = f"{html.escape(title)} · " if title else ""
        quote = html.escape(comment.quote if len(comment.quote) <= 90 else comment.quote[:87] + "…")
        missing = "" if found else ' <span style="color:#b5563c">(text no longer found)</span>'
        head = QLabel(f'<span style="color:gray">{where}<i>“{quote}”</i>{missing}</span>')
        head.setWordWrap(True)
        layout.addWidget(head)
        layout.addWidget(line(comment.author, comment.time, comment.text))
        for reply in comment.replies:
            r = line(reply.author, reply.time, reply.text)
            r.setContentsMargins(12, 0, 0, 0)
            layout.addWidget(r)
        if comment.resolved:
            done = QLabel(f'<span style="color:gray">Resolved{" by " + html.escape(comment.resolved_by) if comment.resolved_by else ""}</span>')
            layout.addWidget(done)

        self.reply = QLineEdit()
        self.reply.setPlaceholderText("Reply…")
        self.reply.returnPressed.connect(lambda: self._reply(panel))
        buttons = QHBoxLayout()
        resolve = QPushButton("Reopen" if comment.resolved else "Resolve")
        resolve.clicked.connect(lambda: panel.resolveRequested.emit(comment.id, not comment.resolved))
        delete = QPushButton("Delete")
        delete.clicked.connect(lambda: panel.deleteRequested.emit(comment.id))
        for b in (resolve, delete):
            b.setFlat(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        buttons.addWidget(self.reply, 1)
        buttons.addWidget(resolve)
        buttons.addWidget(delete)
        layout.addLayout(buttons)

    def _reply(self, panel: "CommentsPanel") -> None:
        text = self.reply.text().strip()
        if text:
            panel.replyRequested.emit(self.comment_id, text)

    def mousePressEvent(self, e):
        self.clicked.emit(self.comment_id)
        super().mousePressEvent(e)


class CommentsPanel(QWidget):
    jumpRequested = Signal(str)  # comment id
    replyRequested = Signal(str, str)  # comment id, text
    resolveRequested = Signal(str, bool)
    deleteRequested = Signal(str)
    addRequested = Signal()

    THIS, ALL = 0, 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scope = QComboBox()
        self.scope.addItems(["This document", "All documents"])
        self.show_resolved = QCheckBox("Resolved")
        self.add = QPushButton("Add Comment…")
        self.add.setToolTip("Select some text, then add a comment on it (Ctrl+Shift+M)")
        self.add.clicked.connect(self.addRequested)
        top = QHBoxLayout()
        top.addWidget(self.scope, 1)
        top.addWidget(self.show_resolved)
        self.list = QWidget()
        self.cards = QVBoxLayout(self.list)
        self.cards.setContentsMargins(0, 0, 0, 0)
        self.cards.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.list)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: gray;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self.add)
        layout.addWidget(self.hint)
        layout.addWidget(scroll, 1)
        self.scope.currentIndexChanged.connect(lambda _: self.changed())
        self.show_resolved.toggled.connect(lambda _: self.changed())
        self._refresh = lambda: None

    def changed(self) -> None:
        self._refresh()

    def set_comments(self, comments: list[tuple[Comment, str, bool]], active: str | None = None) -> None:
        """(comment, document title, found in its text) — already filtered to what's wanted."""
        while self.cards.count():
            item = self.cards.takeAt(0)
            if (old := item.widget()) is not None:  # gone now, not whenever Qt gets round to it
                old.hide()
                old.setParent(None)
                old.deleteLater()
        for comment, title, found in comments:
            card = CommentCard(comment, title if self.scope.currentIndex() == self.ALL else "", found,
                               comment.id == active, self)
            card.clicked.connect(self.jumpRequested)
            self.cards.addWidget(card)
        self.cards.addStretch()
        self.hint.setText("" if comments else "No comments here. Select some text and add one — "
                          "everyone the project syncs with sees it.")
        self.hint.setVisible(not comments)

    def focus_reply(self, comment_id: str) -> None:
        for i in range(self.cards.count()):
            w = self.cards.itemAt(i).widget()
            if isinstance(w, CommentCard) and w.comment_id == comment_id:
                w.reply.setFocus()
