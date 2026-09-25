import re

from PySide6.QtGui import QFontDatabase, QPalette
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
