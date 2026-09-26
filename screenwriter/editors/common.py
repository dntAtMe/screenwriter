import re

from PySide6.QtGui import QFontDatabase, QPalette, QTextCursor
from PySide6.QtWidgets import QAbstractScrollArea

WORD_RE = re.compile(r"[\w'’-]+")


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


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
