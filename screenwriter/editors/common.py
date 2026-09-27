import re

from PySide6.QtGui import QFontDatabase, QPalette, QTextCursor
from PySide6.QtWidgets import QAbstractScrollArea

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


def paint_margins_as_page(editor: QAbstractScrollArea) -> None:
    """Viewport margins are drawn with the Window colour; make them match the text area."""
    pal = editor.palette()
    pal.setColor(QPalette.ColorRole.Window, pal.color(QPalette.ColorRole.Base))
    editor.setPalette(pal)
    editor.setAutoFillBackground(True)


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
        self.highlighter.rehighlight()

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
