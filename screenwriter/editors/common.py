import html
import re
from contextlib import contextmanager

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QFontDatabase, QPalette, QTextCursor
from PySide6.QtWidgets import QAbstractScrollArea, QPlainTextEdit

from ..marks import strip_marks
from ..spelling import words_to_check

SPELLING_RED = "#d9534f"


def underline_misspelled(highlighter, text: str, spell) -> None:
    """Red squiggles under the words of `text` the spell checker doesn't know (keeping the
    rest of each character's format). Words not checked yet get theirs once they are."""
    if spell is None:
        return
    from PySide6.QtGui import QColor, QTextCharFormat

    for start, end, word in words_to_check(text):
        if spell.status(word) is False:
            for i in range(start, end):
                f = highlighter.format(i)
                f.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
                f.setUnderlineColor(QColor(SPELLING_RED))
                highlighter.setFormat(i, 1, f)


BIBLE_COLORS = {"character": "#c07a2c", "location": "#2f8a86"}  # match the binder icons


def tint(highlighter, start: int, end: int, kind: str, strong: bool = False) -> None:
    """A soft background in the kind's colour over [start, end) of the block, keeping the
    rest of each character's format; stronger under the mouse. (Underlines are for
    spelling mistakes only.)"""
    from PySide6.QtGui import QColor

    from .. import theme

    colour = QColor(BIBLE_COLORS.get(kind, "#888888"))
    if theme.is_dark():  # at rest a gentle cue; under the mouse clearly there
        colour.setAlphaF(0.42 if strong else 0.13)
    else:
        colour.setAlphaF(0.30 if strong else 0.08)
    for i in range(start, end):
        f = highlighter.format(i)
        f.setBackground(colour)
        highlighter.setFormat(i, 1, f)


def mark_bible_names(highlighter, text: str, index) -> None:
    """Tint every story-bible name in the block — amber for characters, teal for
    locations — so names stand out from the text around them without shouting."""
    if index:
        hover = getattr(highlighter, "hover", None)  # (block number, start, end) under the mouse
        here = highlighter.currentBlock().blockNumber()
        for m, entry in index.find(text):
            strong = hover is not None and hover[0] == here and hover[1] == m.start()
            tint(highlighter, m.start(), m.end(), entry.kind, strong)


def name_span_at(editor, pos, index):
    """(block number, start, end) of the story-bible name under a viewport point, or None.
    Only when the point is really over the name, not just nearest to it."""
    if not index or pos is None:
        return None
    cursor = editor.cursorForPosition(pos)
    block = cursor.block()
    offset = cursor.positionInBlock()
    for m, _entry in index.find(block.text()):
        if not m.start() <= offset <= m.end():
            continue
        start, end = QTextCursor(block), QTextCursor(block)
        start.setPosition(block.position() + m.start())
        end.setPosition(block.position() + m.end())
        a, b = editor.cursorRect(start), editor.cursorRect(end)
        if a.top() == b.top():  # on one line: the point must be over those characters
            if not (a.left() <= pos.x() <= b.left() and a.top() <= pos.y() <= a.bottom()):
                return None
        return block.blockNumber(), m.start(), m.end()
    return None


def update_name_hover(editor, highlighter, index, pos) -> None:
    """Deepen the tint of the name under the mouse (pos None: the mouse left)."""
    span = name_span_at(editor, pos, index)
    old = getattr(highlighter, "hover", None)
    if span == old:
        return
    highlighter.hover = span
    doc = editor.document()
    with quiet(editor):
        for s in {old, span} - {None}:
            block = doc.findBlockByNumber(s[0])
            if block.isValid():
                highlighter.rehighlightBlock(block)


COMMENT_TINT = (240, 200, 60)  # a soft yellow behind commented text


def highlight_comments(highlighter, text: str) -> None:
    """Tint the commented stretches of the block being highlighted (the selected comment more)."""
    spans = getattr(highlighter, "comment_spans", None)
    if spans is None:
        return
    from PySide6.QtGui import QColor

    block_start = highlighter.currentBlock().position()
    active = getattr(highlighter, "active_comment", lambda: None)()
    for start, end, comment_id in spans():
        lo, hi = max(start - block_start, 0), min(end - block_start, len(text))
        if lo >= hi:
            continue
        tint = QColor(*COMMENT_TINT)
        tint.setAlpha(110 if comment_id == active else 55)
        for i in range(lo, hi):
            f = highlighter.format(i)
            f.setBackground(tint)
            highlighter.setFormat(i, 1, f)


def word_at(editor, pos: int):
    """(start, end, word) of the checkable word around a document position, or None."""
    block = editor.document().findBlock(pos)
    offset = pos - block.position()
    for start, end, word in words_to_check(block.text()):
        if start <= offset <= end:
            return block.position() + start, block.position() + end, word
    return None

WORD_RE = re.compile(r"[\w'’-]+")


def word_count(text: str) -> int:
    return len(WORD_RE.findall(strip_marks(text)))  # a mark's name isn't a word you wrote


def first_available_font(*families: str) -> str:
    installed = set(QFontDatabase.families())
    return next((f for f in families if f in installed), families[-1])


def center_column(editor: QAbstractScrollArea, column_px: float, top: int = 32) -> None:
    """Keep the text in a fixed-width column centred in the editor, like a page."""
    side = max(16, int((editor.width() - column_px) / 2))
    editor.setViewportMargins(side, top, side, 0)


class _PageMargins(QObject):
    """Keeps an editor's margins the colour of its page when the app's palette changes (light/dark)."""

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Type.ApplicationPaletteChange, QEvent.Type.PaletteChange):
            pal = obj.palette()
            if pal.color(QPalette.ColorRole.Window) != pal.color(QPalette.ColorRole.Base):
                pal.setColor(QPalette.ColorRole.Window, pal.color(QPalette.ColorRole.Base))
                obj.setPalette(pal)
        return False


def paint_margins_as_page(editor: QAbstractScrollArea) -> None:
    """Viewport margins are drawn with the Window colour; make them match the text area."""
    pal = editor.palette()
    pal.setColor(QPalette.ColorRole.Window, pal.color(QPalette.ColorRole.Base))
    editor.setPalette(pal)
    editor.setAutoFillBackground(True)
    editor.installEventFilter(_PageMargins(editor))


# --- links between documents: [[Chapter 3]] ---------------------------------------------------
# A [[note]] that names a document is also a link to it: ⌘/Ctrl-click opens it. Like every
# note it's never printed, so links are for finding your way, not part of the text.

LINK_RE = re.compile(r"\[\[([^\[\]\n]+?)\]\]")


def link_spans(text: str, links: dict[str, str]) -> list[tuple[int, int, str]]:
    """(start, end, node id) of the title inside each [[link]] in a line; `links` maps
    lower-case document titles to their ids."""
    out = []
    for m in LINK_RE.finditer(text):
        if node_id := links.get(m.group(1).strip().lower()):
            out.append((m.start(1), m.end(1), node_id))
    return out


def format_links(highlighter, text: str, links: dict[str, str]) -> None:
    """Links in the accent colour, their brackets faint (no underline: that's for spelling)."""
    from PySide6.QtGui import QColor, QFont, QTextCharFormat

    from .. import theme

    for start, end, _ in link_spans(text, links):
        for i in range(start, end):
            f = highlighter.format(i)
            f.setForeground(QColor(theme.tokens()["accent"]))
            f.setFontItalic(False)
            f.setFontWeight(QFont.Weight.DemiBold)
            highlighter.setFormat(i, 1, f)


def link_at(editor, pos) -> str | None:
    """The id of the document linked at a viewport position, or None."""
    links = getattr(editor, "links", None)
    if not links:
        return None
    cursor = editor.cursorForPosition(pos)
    offset = cursor.positionInBlock()
    return next((node_id for start, end, node_id in link_spans(cursor.block().text(), links)
                 if start <= offset <= end), None)


def show_link_tip(editor, e, titles: dict[str, str]) -> bool:
    """A tooltip for the link under the mouse; whether there was one."""
    from PySide6.QtWidgets import QToolTip

    if (node_id := link_at(editor, e.pos())) is None:
        return False
    title = html.escape(titles.get(node_id, ""))
    QToolTip.showText(e.globalPos(), f"<b>Open “{title}”</b><br><i>⌘/Ctrl-click</i>", editor.viewport())
    return True


@contextmanager
def quiet(editor):
    """Re-colouring text (a highlighter pass) makes the editor say textChanged, so the
    document would look unsaved; inside this, it doesn't."""
    blocked = editor.blockSignals(True)
    try:
        yield
    finally:
        editor.blockSignals(blocked)


def quiet_rehighlight(editor) -> None:
    """Re-colour all of an editor's text (names, links, spelling, theme) without it looking like an edit."""
    with quiet(editor):
        editor.highlighter.rehighlight()


class Typewriter(QObject):
    """Typewriter scrolling: as you type, the line you're on stays in the middle of the
    editor instead of creeping to the bottom edge. Clicking elsewhere doesn't scroll;
    the next key you press brings that line to the middle."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.enabled = False
        self._before: tuple[int, int] | None = None
        editor.installEventFilter(self)

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        self._make_room()
        if on:
            QTimer.singleShot(0, self, self.center)  # (the timers go with the editor if it closes first)

    def _make_room(self) -> None:
        """Space below the last line, so even it can sit in the middle."""
        if isinstance(self.editor, QPlainTextEdit):
            self.editor.setCenterOnScroll(self.enabled)
        else:
            self.editor.set_scroll_room(self.editor.viewport().height() // 2 if self.enabled else 0)

    def _state(self) -> tuple[int, int]:
        return self.editor.textCursor().position(), self.editor.document().revision()

    def eventFilter(self, obj, e):
        if self.enabled:
            if e.type() == QEvent.Type.KeyPress:
                before = self._state()
                QTimer.singleShot(0, self, lambda: self._state() != before and self.center())
            elif e.type() == QEvent.Type.Resize and not isinstance(self.editor, QPlainTextEdit):
                QTimer.singleShot(0, self, self._make_room)
        return False

    def center(self) -> None:
        editor = self.editor
        if isinstance(editor, QPlainTextEdit):
            editor.centerCursor()
            return
        bar = editor.verticalScrollBar()
        bar.setValue(bar.value() + editor.cursorRect().center().y() - editor.viewport().height() // 2)


class TextDocumentAPI:
    """What the main window needs from an editor, beyond text()/set_text()/outline().
    The board editor implements the same methods for its canvas."""

    def search_text(self) -> str:
        return self.toPlainText()

    def reveal(self, pos: int, length: int = 0) -> None:
        goto(self, pos, length)

    def jump_to_line(self, line: int) -> None:
        goto_line(self, line)

    def current_line(self) -> int:
        return self.textCursor().blockNumber()

    def replace_all(self, text: str) -> None:
        """Replace the whole document as one undoable edit (restoring a version from History)."""
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        cursor.endEditBlock()

    def apply_remote_text(self, text: str) -> bool:
        """Take in text changed elsewhere (live editing, sync) by replacing only the part that
        differs, so your cursor and scroll position stay put. Returns whether anything changed.
        Their changes can't be undone here, so undo starts afresh."""
        old = self.toPlainText()
        if text == old:
            return False
        start = 0
        limit = min(len(old), len(text))
        while start < limit and old[start] == text[start]:
            start += 1
        end = 0
        while end < limit - start and old[len(old) - 1 - end] == text[len(text) - 1 - end]:
            end += 1
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(len(old) - end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text[start:len(text) - end])
        self.document().clearUndoRedoStacks()
        return True

    def apply_edit(self, change) -> None:
        """Run change(cursor) on the text cursor as one undoable edit (toolbar buttons)."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        change(cursor)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    # --- comments: the stretches of text they're on follow the words as they're edited ---

    def set_comment_anchors(self, found: dict, active: str | None = None) -> None:
        """{comment id: (start, end)} of the comments on this document."""
        self._comment_cursors = {}
        for comment_id, (start, end) in found.items():
            cursor = QTextCursor(self.document())
            cursor.setPosition(min(start, self.document().characterCount() - 1))
            cursor.setPosition(min(end, self.document().characterCount() - 1), QTextCursor.MoveMode.KeepAnchor)
            self._comment_cursors[comment_id] = cursor
        self._active_comment = active
        quiet_rehighlight(self)

    def comment_spans(self) -> list[tuple[int, int, str]]:
        """(start, end, comment id) where each comment's words are now (gone ones left out)."""
        out = []
        for comment_id, c in getattr(self, "_comment_cursors", {}).items():
            start, end = sorted((c.anchor(), c.position()))
            if end > start:
                out.append((start, end, comment_id))
        return out

    def active_comment(self) -> str | None:
        return getattr(self, "_active_comment", None)

    def comment_at(self, pos: int) -> str | None:
        return next((i for s, e, i in self.comment_spans() if s <= pos <= e), None)

    def selected_text(self) -> str:
        text = self.textCursor().selectedText()
        return "" if "\u2029" in text else text  # no multi-line selections


def goto(editor, pos: int, length: int = 0) -> None:
    """Select `length` characters at plain-text offset `pos` and scroll them into view."""
    size = editor.document().characterCount() - 1
    cursor = editor.textCursor()
    cursor.setPosition(min(pos + length, size))
    cursor.setPosition(min(pos, size), QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.ensureCursorVisible()
    editor.setFocus()


def goto_line(editor, line: int) -> None:
    block = editor.document().findBlockByNumber(line)
    if block.isValid():
        goto(editor, block.position())
