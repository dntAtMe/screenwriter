"""Fountain screenplay editor.

The file on disk is plain Fountain text. While editing, each line is classified
(scene heading, character, dialogue, ...) by the highlighter, and a layout pass
indents it like a printed screenplay page.

Keys:
  Tab          on a new line after a blank: start a CHARACTER cue (auto caps)
               on an empty line inside dialogue: insert a (parenthetical)
               on a line with text after a blank: turn it into a CHARACTER cue
  Enter        after action / dialogue / scene heading: new paragraph (blank line)
               after a character cue or parenthetical: continue with dialogue
  Shift+Enter  plain line break
"""

import math
import re
from enum import IntEnum

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QKeySequence,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QFrame, QTextEdit

from .common import center_column, first_available_font, paint_margins_as_page, word_count

PAGE_CHARS = 60  # 6" of Courier 12pt at 10 characters per inch
LINES_PER_PAGE = 55


class El(IntEnum):
    BLANK = 0
    ACTION = 1
    SCENE = 2
    CHARACTER = 3
    PARENTHETICAL = 4
    DIALOGUE = 5
    DIALOGUE_PENDING = 6  # empty line right after a cue: laid out as dialogue, behaves as blank
    TRANSITION = 7
    CENTERED = 8
    SECTION = 9
    SYNOPSIS = 10
    NOTE = 11


EL_NAMES = {
    El.BLANK: "",
    El.ACTION: "Action",
    El.SCENE: "Scene Heading",
    El.CHARACTER: "Character",
    El.PARENTHETICAL: "Parenthetical",
    El.DIALOGUE: "Dialogue",
    El.DIALOGUE_PENDING: "Dialogue",
    El.TRANSITION: "Transition",
    El.CENTERED: "Centered",
    El.SECTION: "Section",
    El.SYNOPSIS: "Synopsis",
    El.NOTE: "Note",
}

# (left indent, right indent) in characters, within the 60-character page line
INDENTS = {
    El.CHARACTER: (22, 0),
    El.PARENTHETICAL: (16, 19),
    El.DIALOGUE: (10, 15),
    El.DIALOGUE_PENDING: (10, 15),
}
ALIGN = {El.TRANSITION: Qt.AlignmentFlag.AlignRight, El.CENTERED: Qt.AlignmentFlag.AlignHCenter}

SCENE_RE = re.compile(r"^(INT|EXT|EST|INT\.?/EXT|I/E)[.\s]", re.IGNORECASE)
IN_DIALOGUE = (El.CHARACTER, El.PARENTHETICAL, El.DIALOGUE)


EXTENSION_RE = re.compile(r"\s*\([^()]*\)\s*\^?$")  # MARA (V.O.)  /  MARA (cont'd) ^


def _is_caps(s: str) -> bool:
    """All-caps line, allowing a trailing (extension) in any case: a character cue."""
    name = EXTENSION_RE.sub("", s).rstrip("^ ")
    return any(c.isalpha() for c in name) and name == name.upper() and "(" not in name


def classify(text: str, prev: int) -> El:
    s = text.strip()
    if prev in IN_DIALOGUE:
        if not s:
            return El.DIALOGUE_PENDING if prev in (El.CHARACTER, El.PARENTHETICAL) else El.BLANK
        return El.PARENTHETICAL if s.startswith("(") else El.DIALOGUE
    if not s:
        return El.BLANK
    if s.startswith("#"):
        return El.SECTION
    if s.startswith("=") and not s.startswith("==="):
        return El.SYNOPSIS
    if s.startswith("[[") and s.endswith("]]"):
        return El.NOTE
    if s.startswith(">"):
        return El.CENTERED if s.endswith("<") else El.TRANSITION
    after_break = prev in (-1, El.BLANK, El.DIALOGUE_PENDING)
    if after_break:
        if s.startswith("!"):
            return El.ACTION
        if (s.startswith(".") and not s.startswith("..")) or SCENE_RE.match(s):
            return El.SCENE
        if s.startswith("@"):
            return El.CHARACTER
        if _is_caps(s):
            return El.TRANSITION if s.endswith("TO:") else El.CHARACTER
    return El.ACTION


def _fmt(*, bold=False, italic=False, underline=False, color=None) -> QTextCharFormat:
    f = QTextCharFormat()
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    f.setFontItalic(italic)
    f.setFontUnderline(underline)
    if color:
        f.setForeground(QColor(color))
    return f


class FountainHighlighter(QSyntaxHighlighter):
    GREY = "#8a8f98"
    ELEMENT_FORMATS = {
        El.SCENE: _fmt(bold=True),
        El.SECTION: _fmt(bold=True, color="#c27c3a"),
        El.SYNOPSIS: _fmt(italic=True, color=GREY),
        El.NOTE: _fmt(italic=True, color=GREY),
    }
    INLINE = [
        (re.compile(r"\*\*\*[^*]+\*\*\*"), _fmt(bold=True, italic=True)),
        (re.compile(r"\*\*[^*]+\*\*"), _fmt(bold=True)),
        (re.compile(r"(?<!\*)\*[^*\s][^*]*\*(?!\*)"), _fmt(italic=True)),
        (re.compile(r"(?<!\w)_[^_\s][^_]*_(?!\w)"), _fmt(underline=True)),
        (re.compile(r"\[\[.*?\]\]"), _fmt(italic=True, color=GREY)),
    ]
    FORCED_MARKERS = ".!@>"

    def highlightBlock(self, text: str) -> None:
        el = classify(text, self.previousBlockState())
        self.setCurrentBlockState(int(el))
        if el in self.ELEMENT_FORMATS:
            self.setFormat(0, len(text), self.ELEMENT_FORMATS[el])
        for regex, fmt in self.INLINE:
            for m in regex.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
        stripped = text.lstrip()
        if stripped[:1] in self.FORCED_MARKERS and el not in (El.DIALOGUE, El.PARENTHETICAL):
            self.setFormat(len(text) - len(stripped), 1, _fmt(color=self.GREY))


class ScreenplayEditor(QTextEdit):
    statsChanged = Signal()
    elementChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptRichText(False)
        font = QFont(first_available_font("Courier Prime", "Courier New", "Courier"))
        font.setPointSizeF(14)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.document().setDefaultFont(font)
        paint_margins_as_page(self)

        self.highlighter = FountainHighlighter(self.document())
        self._applying = False
        self._caps_block = -1  # block number in "CHARACTER cue" mode after Tab

        self._layout_timer = QTimer(self, singleShot=True, interval=0)
        self._layout_timer.timeout.connect(self._apply_layout)
        self.document().contentsChanged.connect(self._layout_timer.start)
        self.textChanged.connect(self.statsChanged)
        self.cursorPositionChanged.connect(self._on_cursor_moved)

    # --- content ------------------------------------------------------------

    def set_text(self, text: str) -> None:
        self.setPlainText(text)
        self._apply_layout()
        self.document().clearUndoRedoStacks()
        self.document().setModified(False)

    def text(self) -> str:
        return self.toPlainText()

    def stats(self) -> str:
        pages = self.page_estimate()
        return f"{word_count(self.toPlainText())} words · ~{pages} page{'s' if pages != 1 else ''}"

    def page_estimate(self) -> int:
        lines = 0
        block = self.document().begin()
        while block.isValid():
            left, right = INDENTS.get(El(max(block.userState(), 0)), (0, 0))
            width = PAGE_CHARS - left - right
            lines += max(1, math.ceil(len(block.text()) / width))
            block = block.next()
        return max(1, round(lines / LINES_PER_PAGE))

    # --- layout -------------------------------------------------------------

    def _char_width(self) -> float:
        return QFontMetricsF(self.document().defaultFont()).horizontalAdvance("M")

    def _apply_layout(self) -> None:
        """Indent every block according to its element. This records its own
        format-only undo step, which undo()/redo() below step over."""
        if self._applying:
            return
        self._applying = True
        cw = self._char_width()
        cursor = None
        block = self.document().begin()
        while block.isValid():
            el = El(max(block.userState(), 0))
            left, right = INDENTS.get(el, (0, 0))
            align = ALIGN.get(el, Qt.AlignmentFlag.AlignLeft)
            fmt = block.blockFormat()
            if (
                abs(fmt.leftMargin() - left * cw) > 0.5
                or abs(fmt.rightMargin() - right * cw) > 0.5
                or fmt.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask != align
            ):
                if cursor is None:
                    cursor = QTextCursor(self.document())
                    cursor.beginEditBlock()
                new = QTextBlockFormat(fmt)
                new.setLeftMargin(left * cw)
                new.setRightMargin(right * cw)
                new.setAlignment(align)
                cursor.setPosition(block.position())
                cursor.setBlockFormat(new)
            block = block.next()
        if cursor is not None:
            cursor.endEditBlock()
        self._applying = False

    def zoom(self, steps: int) -> None:
        font = self.document().defaultFont()
        font.setPointSizeF(max(9, font.pointSizeF() + steps))
        self.setFont(font)
        self.document().setDefaultFont(font)
        self._apply_layout()
        self._recenter()

    def _recenter(self) -> None:
        center_column(self, PAGE_CHARS * self._char_width() + 2 * self.document().documentMargin())

    def resizeEvent(self, e):
        self._recenter()  # before super(), which re-wraps text to the new viewport width
        super().resizeEvent(e)

    # --- undo ---------------------------------------------------------------

    def undo(self) -> None:
        """Undo back to the previous *text* state, skipping layout-only steps.
        That state's layout was already applied, so no new step is recorded
        and the redo stack stays intact."""
        doc, cursor = self.document(), self.textCursor()
        text = doc.toPlainText()
        self._applying = True
        while doc.isUndoAvailable():
            doc.undo(cursor)
            if doc.toPlainText() != text:
                break
        self._applying = False
        self.setTextCursor(cursor)

    def redo(self) -> None:
        """Redo one text change plus the layout step recorded right after it."""
        doc, cursor = self.document(), self.textCursor()
        text = doc.toPlainText()
        self._applying = True
        while doc.isRedoAvailable():
            doc.redo(cursor)
            if doc.toPlainText() != text:
                break
        while doc.isRedoAvailable():
            before = doc.toPlainText()
            doc.redo(cursor)
            if doc.toPlainText() != before:
                doc.undo(cursor)
                break
        self._applying = False
        self.setTextCursor(cursor)

    # --- keys ---------------------------------------------------------------

    def _element(self, block) -> El:
        return El(max(block.userState(), 0))

    def _on_cursor_moved(self) -> None:
        block = self.textCursor().block()
        if block.blockNumber() != self._caps_block:
            self._caps_block = -1
        name = "Character" if self._caps_block >= 0 else EL_NAMES[self._element(block)]
        self.elementChanged.emit(name)
        self.statsChanged.emit()

    def keyPressEvent(self, e):
        self._handle_key(e)
        # Lay out right away so every text step is directly followed by its own
        # layout step (undo/redo rely on that); the timer covers paste, drop, etc.
        self._layout_timer.stop()
        self._apply_layout()

    def _handle_key(self, e):
        key, mods = e.key(), e.modifiers()
        cursor = self.textCursor()
        block = cursor.block()
        el = self._element(block)
        plain = not (mods & ~Qt.KeyboardModifier.KeypadModifier)

        if e.matches(QKeySequence.StandardKey.Undo):
            self.undo()
            return
        if e.matches(QKeySequence.StandardKey.Redo):
            self.redo()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and mods & Qt.KeyboardModifier.ShiftModifier:
            cursor.insertBlock()  # a real line break, not QTextEdit's soft U+2028 separator
            self.setTextCursor(cursor)
            return

        if key == Qt.Key.Key_Tab and plain:
            self._tab(cursor)
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and plain and cursor.atBlockEnd() and block.text().strip():
            if el in (El.SCENE, El.TRANSITION):
                self._uppercase_block(cursor)
            if el in (El.ACTION, El.SCENE, El.TRANSITION, El.CENTERED, El.DIALOGUE):
                next_blank = block.next().isValid() and not block.next().text().strip()
                cursor.insertText("\n" if next_blank else "\n\n")
                if next_blank:
                    cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
                self.setTextCursor(cursor)
                self.ensureCursorVisible()
                return
            if el in (El.CHARACTER, El.PARENTHETICAL):
                self._caps_block = -1
                cursor.insertText("\n")
                self.setTextCursor(cursor)
                return

        text = e.text()
        auto_caps = block.blockNumber() == self._caps_block or el in (El.SCENE, El.TRANSITION)
        if auto_caps and text and text.isprintable() and text != text.upper() and not (mods & Qt.KeyboardModifier.ControlModifier):
            cursor.insertText(text.upper())
            self.setTextCursor(cursor)
            return

        super().keyPressEvent(e)

    def _tab(self, cursor: QTextCursor) -> None:
        block = cursor.block()
        prev = block.previous()
        prev_el = self._element(prev) if prev.isValid() else El.BLANK
        text = block.text()

        if prev_el in IN_DIALOGUE:
            if not text.strip():
                cursor.insertText("()")
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
            return

        if prev_el in (El.BLANK, El.DIALOGUE_PENDING) or not prev.isValid():
            if text.strip():
                self._uppercase_block(cursor)
            self._caps_block = block.blockNumber()
            self.elementChanged.emit("Character")

    def _uppercase_block(self, cursor: QTextCursor) -> None:
        pos = cursor.position()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        upper = cursor.selectedText().upper()
        if upper != cursor.selectedText():
            cursor.insertText(upper)
        cursor.setPosition(pos)
        self.setTextCursor(cursor)
