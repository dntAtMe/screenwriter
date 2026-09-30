"""Markdown editor for prose and notes.

Story bible names are underlined as you write: hover for the entry's summary,
Ctrl/⌘-click to open it, and names are offered for completion.
"""

import html
import re

from PySide6.QtCore import QEvent, QStringListModel, Qt, Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QCompleter, QFrame, QPlainTextEdit, QToolTip

from ..bible import CHARACTER, BibleIndex
from .. import fonts
from ..fountain import OutlineItem
from ..marks import MARK_RE
from .biblemenu import add_bible_menu, add_mark_menu
from .spellmenu import add_comment_action, add_spelling_menu
from .common import (
    TextDocumentAPI,
    format_links,
    link_at,
    mark_bible_names,
    quiet_rehighlight,
    show_link_tip,
    update_name_hover,
    center_column,
    paint_margins_as_page,
    highlight_comments,
    underline_misspelled,
    word_count,
)

COLUMN_CHARS = 70
WORD_BEFORE_RE = re.compile(r"[\w'’-]+$")


def _fmt(*, bold=False, italic=False, color=None, scale=None, base: QFont | None = None) -> QTextCharFormat:
    f = QTextCharFormat()
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    if color:
        f.setForeground(QColor(color))
    if scale and base:
        f.setFontPointSize(base.pointSizeF() * scale)
    return f


class MarkdownHighlighter(QSyntaxHighlighter):
    INLINE = [
        (re.compile(r"\*\*[^*]+\*\*|__[^_]+__"), "bold"),
        (re.compile(r"(?<![*\w])\*[^*\s][^*]*\*(?!\*)|(?<![_\w])_[^_\s][^_]*_(?!_)"), "italic"),
        (re.compile(r"\[\[.*?\]\]"), "note"),
    ]

    def __init__(self, doc, base_font: QFont):
        super().__init__(doc)
        self.base_font = base_font
        self.formats = {
            "bold": _fmt(bold=True),
            "italic": _fmt(italic=True),
            "note": _fmt(italic=True, color="#8a8f98"),
            "quote": _fmt(italic=True, color="#7a7f88"),
            "marker": _fmt(color="#9aa0a8"),
        }
        self.bible = BibleIndex()
        self.links: dict[str, str] = {}  # lower-case document title → id, for [[links]]
        self.spell = None  # the SpellService, set by the window

    def highlightBlock(self, text: str) -> None:
        heading = re.match(r"^(#{1,6})\s", text)
        if heading:
            level = len(heading.group(1))
            scale = {1: 1.6, 2: 1.35, 3: 1.15}.get(level, 1.0)
            self.setFormat(0, len(text), _fmt(bold=True, scale=scale, base=self.base_font))
            self.setFormat(0, level, self.formats["marker"])
            underline_misspelled(self, text, self.spell)
            highlight_comments(self, text)
            return
        if text.startswith(">"):
            self.setFormat(0, len(text), self.formats["quote"])
        for regex, name in self.INLINE:
            for m in regex.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), self.formats[name])
        format_links(self, text, self.links)
        tag = _fmt(color="#a0a4ab", scale=0.72, base=self.base_font)  # (follows zoom)
        for m in MARK_RE.finditer(text):  # {the hooded figure|Xardas}: the tag faint, the phrase as written
            self.setFormat(m.start(), 1, tag)
            self.setFormat(m.end(1), m.end() - m.end(1), tag)
        mark_bible_names(self, text, self.bible)
        underline_misspelled(self, text, self.spell)
        highlight_comments(self, text)


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


def markdown_outline(text: str) -> list[OutlineItem]:
    items = []
    for i, line in enumerate(text.split("\n")):
        if m := HEADING_RE.match(line):
            items.append(OutlineItem(len(m.group(1)) - 1, m.group(2).strip() or "(heading)", i, "heading"))
    return items


class ProseEditor(TextDocumentAPI, QPlainTextEdit):
    statsChanged = Signal()
    bibleOpenRequested = Signal(str)  # entry node id
    bibleAddRequested = Signal(str, str)  # kind, name
    bibleAliasRequested = Signal(str, str)  # entry node id, another name for it
    linkOpenRequested = Signal(str)  # node id of a [[linked]] document
    addWordRequested = Signal(str)  # to the project dictionary
    commentRequested = Signal()  # on the selected text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        font = fonts.font("prose", 17)
        self.setFont(font)
        self.highlighter = MarkdownHighlighter(self.document(), font)
        self.highlighter.comment_spans = self.comment_spans
        self.highlighter.active_comment = self.active_comment
        paint_margins_as_page(self)
        self.textChanged.connect(self.statsChanged)
        self.selectionChanged.connect(self.statsChanged)
        self.viewport().setMouseTracking(True)

        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setModel(QStringListModel(self.completer))
        self.completer.activated[str].connect(self._insert_completion)

        self.link_titles: dict[str, str] = {}  # node id → title
        self.link_completer = QCompleter(self)  # after [[: document titles
        self.link_completer.setWidget(self)
        self.link_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.link_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.link_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.link_completer.setModel(QStringListModel(self.link_completer))
        self.link_completer.activated[str].connect(self._insert_link)

    # --- story bible ------------------------------------------------------------------

    @property
    def bible(self) -> BibleIndex:
        return self.highlighter.bible

    def refresh_theme(self) -> None:
        quiet_rehighlight(self)  # name tints are lighter or deeper in dark mode

    def set_bible(self, index: BibleIndex) -> None:
        """Use these names for underlining, hover cards and completion."""
        signature = lambda idx: [(e.node_id, e.names, e.summary) for e in idx.entries]
        if signature(index) == signature(self.bible):
            return
        self.highlighter.bible = index
        quiet_rehighlight(self)
        self.completer.model().setStringList([n for n in index.completions() if n[:1].isupper()])

    # --- links between documents ----------------------------------------------------------

    @property
    def links(self) -> dict[str, str]:
        return self.highlighter.links

    def set_links(self, titles: dict[str, str]) -> None:
        """Documents that [[Title]] can link to: {node id: title}."""
        if titles == self.link_titles:
            return
        self.link_titles = dict(titles)
        links: dict[str, str] = {}
        for node_id, title in titles.items():
            links.setdefault(title.strip().lower(), node_id)  # the first of two with one name
        self.highlighter.links = links
        quiet_rehighlight(self)
        self.link_completer.model().setStringList(sorted(set(titles.values()), key=str.lower))

    def _update_link_completion(self) -> bool:
        """After "[[", offer document titles; whether the popup is up."""
        popup = self.link_completer.popup()
        cursor = self.textCursor()
        before = cursor.block().text()[: cursor.positionInBlock()]
        m = re.search(r"\[\[([^\[\]]*)$", before)
        if not m or not self.link_titles:
            popup.hide()
            return False
        self.link_completer.setCompletionPrefix(m.group(1))
        if self.link_completer.completionCount() == 0:
            popup.hide()
            return False
        popup.setCurrentIndex(self.link_completer.completionModel().index(0, 0))
        rect = self.cursorRect().translated(self.viewport().pos())
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 16)
        self.link_completer.complete(rect)
        return True

    def _insert_link(self, title: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(
            QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(self.link_completer.completionPrefix())
        )
        closed = cursor.block().text()[cursor.positionInBlock() + len(cursor.selectedText()):].startswith("]]")
        cursor.insertText(title if closed else title + "]]")
        if closed:
            cursor.movePosition(QTextCursor.MoveOperation.Right, n=2)
        self.setTextCursor(cursor)

    def bible_at(self, pos):
        """The bible entry named at a viewport position, or None."""
        cursor = self.cursorForPosition(pos)
        offset = cursor.positionInBlock()
        for m, entry in self.bible.find(cursor.block().text()):
            if m.start() <= offset <= m.end():
                return entry
        return None

    def viewportEvent(self, e):
        if e.type() == QEvent.Type.ToolTip:
            if entry := self.bible_at(e.pos()):
                kind = "Character" if entry.kind == CHARACTER else "Location"
                summary = f"<br>{html.escape(entry.summary)}" if entry.summary else ""
                QToolTip.showText(
                    e.globalPos(),
                    f"<b>{html.escape(entry.name)}</b> · {kind}{summary}<br><i>⌘/Ctrl-click to open</i>",
                    self.viewport(),
                )
            elif not show_link_tip(self, e, self.link_titles):
                QToolTip.hideText()
            return True
        return super().viewportEvent(e)

    def mousePressEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier and e.button() == Qt.MouseButton.LeftButton:
            if entry := self.bible_at(e.position().toPoint()):
                self.bibleOpenRequested.emit(entry.node_id)
                return
            if node_id := link_at(self, e.position().toPoint()):
                self.linkOpenRequested.emit(node_id)
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        over = e.modifiers() & Qt.KeyboardModifier.ControlModifier and (self.bible_at(pos) or link_at(self, pos))
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.IBeamCursor)
        update_name_hover(self, self.highlighter, self.bible, pos)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        update_name_hover(self, self.highlighter, self.bible, None)
        super().leaveEvent(e)

    def contextMenuEvent(self, e):
        menu = self.createStandardContextMenu()
        entry = self.bible_at(e.pos())
        name = self._name_under(e.pos())
        # a selection that isn't exactly a known name can still be added (e.g. "Kacprowi")
        if name and (entry is None or self.textCursor().hasSelection()):
            add_bible_menu(menu, name, self.bible, self.bibleAddRequested.emit, self.bibleAliasRequested.emit)
        add_mark_menu(menu, self, self.bible, self.cursorForPosition(e.pos()).position())
        add_spelling_menu(menu, self, self.highlighter.spell, self.cursorForPosition(e.pos()).position(),
                          self.addWordRequested.emit)
        add_comment_action(menu, self, self.commentRequested.emit)
        if entry:
            first = menu.actions()[0]
            action = menu.addAction(f"Open “{entry.name}” in Story Bible")
            action.triggered.connect(lambda: self.bibleOpenRequested.emit(entry.node_id))
            menu.insertAction(first, action)
        menu.exec(e.globalPos())

    def _name_under(self, pos) -> str:
        """The selection (one short line), or the capitalised word under the mouse."""
        selected = self.textCursor().selectedText().strip()
        if selected and "\u2029" not in selected and len(selected) <= 60:
            return selected
        cursor = self.cursorForPosition(pos)
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText().strip()
        return word if word[:1].isupper() else ""

    # --- completion ---------------------------------------------------------------------

    def keyPressEvent(self, e):
        popup = self.completer.popup()
        if (popup.isVisible() or self.link_completer.popup().isVisible()) and e.key() in (
            Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
        ):
            e.ignore()  # the completer handles these
            return
        super().keyPressEvent(e)
        if e.text() and (e.text().isprintable() or e.key() == Qt.Key.Key_Backspace) and self._update_link_completion():
            popup.hide()
            return
        if self.bible and e.text() and (e.text().isprintable() or e.key() == Qt.Key.Key_Backspace):
            self._update_completion()
        else:
            popup.hide()

    def _update_completion(self) -> None:
        popup = self.completer.popup()
        cursor = self.textCursor()
        text = cursor.block().text()
        pos = cursor.positionInBlock()
        m = WORD_BEFORE_RE.search(text[:pos])
        after = text[pos : pos + 1]
        prefix = m.group(0) if m else ""
        if len(prefix) < 3 or not prefix[0].isupper() or (after and (after.isalnum() or after == "_")):
            popup.hide()
            return
        self.completer.setCompletionPrefix(prefix)
        count = self.completer.completionCount()
        if count == 0 or (count == 1 and self.completer.currentCompletion().lower() == prefix.lower()):
            popup.hide()
            return
        popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect().translated(self.viewport().pos())
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 16)
        self.completer.complete(rect)

    def _insert_completion(self, completion: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(
            QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(self.completer.completionPrefix())
        )
        cursor.insertText(completion)
        self.setTextCursor(cursor)

    def set_text(self, text: str) -> None:
        self.setPlainText(text)
        self.document().setModified(False)

    def text(self) -> str:
        return self.toPlainText()

    def outline(self) -> list[OutlineItem]:
        return markdown_outline(self.toPlainText())

    def is_modified(self) -> bool:
        return self.document().isModified()

    def mark_saved(self) -> None:
        self.document().setModified(False)

    def stats(self) -> str:
        cursor = self.textCursor()
        words = word_count(self.toPlainText())
        if cursor.hasSelection():
            return f"{word_count(cursor.selectedText())} of {words} words"
        return f"{words} words"

    def zoom(self, steps: int) -> None:
        font = self.font()
        font.setPointSizeF(max(9, font.pointSizeF() + steps))
        self._set_base_font(font)

    def apply_font(self) -> None:
        """Use the chosen prose font (View → Fonts), at the current size."""
        self._set_base_font(fonts.font("prose", self.font().pointSizeF()))

    def _set_base_font(self, font) -> None:
        self.setFont(font)
        self.highlighter.base_font = font
        quiet_rehighlight(self)
        self._recenter()

    def _recenter(self) -> None:
        cw = self.fontMetrics().averageCharWidth()
        center_column(self, COLUMN_CHARS * cw + 2 * self.document().documentMargin())

    def resizeEvent(self, e):
        self._recenter()  # before super(), which re-wraps text to the new viewport width
        super().resizeEvent(e)
