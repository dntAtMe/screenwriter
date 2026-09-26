"""Markdown editor for prose and notes."""

import re

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QFrame, QPlainTextEdit

from ..fountain import OutlineItem
from .common import center_column, first_available_font, paint_margins_as_page, word_count

COLUMN_CHARS = 70


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

    def highlightBlock(self, text: str) -> None:
        heading = re.match(r"^(#{1,6})\s", text)
        if heading:
            level = len(heading.group(1))
            scale = {1: 1.6, 2: 1.35, 3: 1.15}.get(level, 1.0)
            self.setFormat(0, len(text), _fmt(bold=True, scale=scale, base=self.base_font))
            self.setFormat(0, level, self.formats["marker"])
            return
        if text.startswith(">"):
            self.setFormat(0, len(text), self.formats["quote"])
        for regex, name in self.INLINE:
            for m in regex.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), self.formats[name])


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


def markdown_outline(text: str) -> list[OutlineItem]:
    items = []
    for i, line in enumerate(text.split("\n")):
        if m := HEADING_RE.match(line):
            items.append(OutlineItem(len(m.group(1)) - 1, m.group(2).strip() or "(heading)", i, "heading"))
    return items


class ProseEditor(QPlainTextEdit):
    statsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        font = QFont(first_available_font("Iowan Old Style", "Charter", "Georgia", "Serif"))
        font.setPointSizeF(17)
        self.setFont(font)
        self.highlighter = MarkdownHighlighter(self.document(), font)
        paint_margins_as_page(self)
        self.textChanged.connect(self.statsChanged)
        self.selectionChanged.connect(self.statsChanged)

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
        self.setFont(font)
        self.highlighter.base_font = font
        self.highlighter.rehighlight()
        self._recenter()

    def _recenter(self) -> None:
        cw = self.fontMetrics().averageCharWidth()
        center_column(self, COLUMN_CHARS * cw + 2 * self.document().documentMargin())

    def resizeEvent(self, e):
        self._recenter()  # before super(), which re-wraps text to the new viewport width
        super().resizeEvent(e)
