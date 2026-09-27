"""Fountain screenplay editor.

The file on disk is plain Fountain text. While editing, each line is classified
(scene heading, character, dialogue, ...) by the highlighter, and a layout pass
indents it like a printed screenplay page.

Keys:
  Tab              new line after a blank: start a CHARACTER cue (auto caps)
                   empty line in dialogue: insert a (parenthetical)
                   line with text after a blank: turn it into a CHARACTER cue
  Enter            after action / dialogue / scene heading: new paragraph
                   after a character cue or parenthetical: continue with dialogue
  Shift+Enter      plain line break
  Ctrl+1 … Ctrl+6  make the line a Scene Heading, Action, Character,
                   Parenthetical, Dialogue or Transition

As you type:
  int / ext / i/e + space or "."   becomes INT. / EXT. / INT./EXT.
  cut to / fade out / dissolve to  becomes a transition when you press Enter
  scene headings and transitions   are capitalised
  character names, locations and times of day are offered for completion
"""

import math
from typing import Callable

from PySide6.QtCore import QStringListModel, Qt, QTimer, Signal
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
from PySide6.QtWidgets import QCompleter, QFrame, QTextEdit

import re

from .. import fountain
from ..fountain import AFTER_BREAK, EL_NAMES, IN_DIALOGUE, SCENE_PREFIXES, SCENE_RE, El, classify
from ..bible import BibleIndex
from .biblemenu import add_bible_menu
from .history import TextHistory
from .common import TextDocumentAPI, center_column, first_available_font, paint_margins_as_page, word_count

PAGE_CHARS = 60  # 6" of Courier 12pt at 10 characters per inch
LINES_PER_PAGE = 55

# (left indent, right indent) in characters, within the 60-character page line
INDENTS = {
    El.CHARACTER: (22, 0),
    El.PARENTHETICAL: (16, 19),
    El.DIALOGUE: (10, 15),
    El.DIALOGUE_PENDING: (10, 15),
}
ALIGN = {El.TRANSITION: Qt.AlignmentFlag.AlignRight, El.CENTERED: Qt.AlignmentFlag.AlignHCenter}
FORCED_MARKERS = ".!@>"

HEADING_PREFIX_RE = re.compile(r"^\.?(INT\.?/EXT|I/E|INT|EXT|EST)\.?\s+", re.IGNORECASE)


def heading_location(heading: str) -> str:
    """'INT. LAMP ROOM - NIGHT' -> 'LAMP ROOM'."""
    return HEADING_PREFIX_RE.sub("", heading.strip().lstrip(".")).split(" - ")[0].strip().upper()


# Elements that can be picked explicitly (Format menu / Ctrl+1…6)
SETTABLE = [El.SCENE, El.ACTION, El.CHARACTER, El.PARENTHETICAL, El.DIALOGUE, El.TRANSITION]


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
        El.TITLE_PAGE: _fmt(color="#7f9cc0"),
    }
    INLINE = [
        (re.compile(r"\*\*\*[^*]+\*\*\*"), _fmt(bold=True, italic=True)),
        (re.compile(r"\*\*[^*]+\*\*"), _fmt(bold=True)),
        (re.compile(r"(?<!\*)\*[^*\s][^*]*\*(?!\*)"), _fmt(italic=True)),
        (re.compile(r"(?<!\w)_[^_\s][^_]*_(?!\w)"), _fmt(underline=True)),
        (re.compile(r"\[\[.*?\]\]"), _fmt(italic=True, color=GREY)),
    ]

    def __init__(self, editor: "ScreenplayEditor"):
        super().__init__(editor.document())
        self.editor = editor

    def highlightBlock(self, text: str) -> None:
        block = self.currentBlock()
        number = block.blockNumber()
        cursor_block = self.editor.textCursor().blockNumber()
        nxt = block.next()
        next_text = nxt.text() if nxt.isValid() else None
        if nxt.isValid() and nxt.blockNumber() == cursor_block and not next_text.strip():
            next_text = "…"  # the writer is about to type this cue's dialogue
        el = classify(
            text,
            self.previousBlockState(),
            next_text,
            editing=number == cursor_block,
            forced_cue=number == self.editor.cue_block,
        )
        self.setCurrentBlockState(int(el))
        if el in self.ELEMENT_FORMATS:
            self.setFormat(0, len(text), self.ELEMENT_FORMATS[el])
        for regex, fmt in self.INLINE:
            for m in regex.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
        stripped = text.lstrip()
        if stripped[:1] in FORCED_MARKERS and el not in (El.DIALOGUE, El.PARENTHETICAL):
            self.setFormat(len(text) - len(stripped), 1, _fmt(color=self.GREY))


class ScreenplayEditor(TextDocumentAPI, QTextEdit):
    statsChanged = Signal()
    elementChanged = Signal(str)
    bibleRequested = Signal(str, str)  # "character" | "location", NAME
    bibleAddRequested = Signal(str, str)  # kind, selected text
    bibleAliasRequested = Signal(str, str)  # entry node id, selected text
    bible_index = BibleIndex()  # set by the main window

    # Set by the main window: story bible names for completion, and entry lookup.
    bible_names: Callable[[], tuple[list[str], list[str]]] = staticmethod(lambda: ([], []))
    bible_lookup: Callable[[str, str], str | None] = staticmethod(lambda kind, name: None)

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

        self.document().setUndoRedoEnabled(False)  # see history.py
        self.history = TextHistory()
        self._replaying = False
        self.cue_block = -1      # block number in "character cue" mode after Tab
        self._cursor_block = 0
        self._applying = False
        self._laid_out_unit = 0.0  # indent per character at the last layout
        self.highlighter = FountainHighlighter(self)

        # Edits that don't come through keyPressEvent (paste, drop, undo) get a full refresh.
        self._refresh_timer = QTimer(self, singleShot=True, interval=0)
        self._refresh_timer.timeout.connect(self._full_refresh)
        self.document().contentsChange.connect(self._on_contents_change)
        self._layout_timer = QTimer(self, singleShot=True, interval=0)
        self._layout_timer.timeout.connect(self._apply_layout)

        self.textChanged.connect(self.statsChanged)
        self.cursorPositionChanged.connect(self._on_cursor_moved)

        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setModel(QStringListModel(self.completer))
        self.completer.activated[str].connect(self._insert_completion)
        self._completion_kind = None

    # --- content ------------------------------------------------------------

    def set_text(self, text: str) -> None:
        self._replaying = True
        self.setPlainText(text)
        self._replaying = False
        self.history.reset(self.toPlainText())
        self._saved_text = self.history.text
        self._full_refresh()

    def text(self) -> str:
        return self.toPlainText()

    def is_modified(self) -> bool:
        # Not document().isModified(): with Qt's undo off, restyling sets that flag too.
        return self.history.text != self._saved_text

    def mark_saved(self) -> None:
        self._saved_text = self.history.text

    def lines(self) -> list[tuple[str, El]]:
        """Every line with its element, as currently shown."""
        out, block = [], self.document().begin()
        while block.isValid():
            out.append((block.text(), self._element(block)))
            block = block.next()
        return out

    def outline(self) -> list[fountain.OutlineItem]:
        return fountain.outline(self.lines())

    def stats(self) -> str:
        pages = self.page_estimate()
        return f"{word_count(self.toPlainText())} words · ~{pages} page{'s' if pages != 1 else ''}"

    def page_estimate(self) -> int:
        lines = 0
        block = self.document().begin()
        while block.isValid():
            left, right = INDENTS.get(self._element(block), (0, 0))
            lines += max(1, math.ceil(len(block.text()) / (PAGE_CHARS - left - right)))
            block = block.next()
        return max(1, round(lines / LINES_PER_PAGE))

    def current_element(self) -> El:
        return self._element(self.textCursor().block())

    # --- classification & layout ----------------------------------------------

    @staticmethod
    def _element(block) -> El:
        return El(max(block.userState(), 0))

    def _on_contents_change(self, pos, removed, added) -> None:
        if self._replaying or self._applying:  # undo/redo, or our layout pass (formats only)
            return
        self.history.record(self.toPlainText(), self.textCursor().position(), (pos, removed, added))
        self._refresh_timer.start()

    def _full_refresh(self) -> None:
        self.highlighter.rehighlight()
        self._apply_layout()

    def _refresh_blocks(self, *numbers: int) -> None:
        """Re-classify blocks whose element depends on the cursor or on the next line."""
        doc = self.document()
        for n in sorted(set(numbers)):
            block = doc.findBlockByNumber(n)
            if block.isValid():
                self.highlighter.rehighlightBlock(block)

    def _refresh_around_cursor(self) -> None:
        n = self.textCursor().blockNumber()
        self._refresh_blocks(n - 1, n)

    def _char_width(self) -> float:
        return QFontMetricsF(self.document().defaultFont()).horizontalAdvance("M")

    def _apply_layout(self) -> None:
        """Indent every block according to its element."""
        if self._applying:
            return
        self._applying = True
        cw = self._indent_unit()
        cursor = None
        block = self.document().begin()
        while block.isValid():
            el = self._element(block)
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
        self._laid_out_unit = cw
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

    def _indent_unit(self) -> float:
        """Width of one character of indent: a character, or less when the editor is
        narrower than a page (a split view), so dialogue keeps its shape instead of
        being squeezed into a sliver."""
        cw = self._char_width()
        room = self.viewport().width() - 2 * self.document().documentMargin()
        return min(cw, room / PAGE_CHARS) if room > 0 else cw

    def resizeEvent(self, e):
        self._recenter()  # before super(), which re-wraps text to the new viewport width
        super().resizeEvent(e)
        if abs(self._indent_unit() - self._laid_out_unit) > 0.25:
            self._apply_layout()

    # --- undo ---------------------------------------------------------------

    def replace_all(self, text: str) -> None:
        self.history.begin(self.textCursor().position())
        super().replace_all(text)
        self.history.end(0)
        self._full_refresh()

    def apply_edit(self, change) -> None:
        self.history.begin(self.textCursor().position())
        super().apply_edit(change)
        self.history.end(self.textCursor().position())
        self.cue_block = -1
        self._full_refresh()
        self.elementChanged.emit(EL_NAMES[self.current_element()])

    def can_undo(self) -> bool:
        return self.history.can_undo()

    def can_redo(self) -> bool:
        return self.history.can_redo()

    def undo(self) -> None:
        if step := self.history.pop_undo():
            self._replay([(e.pos, e.added, e.removed) for e in reversed(step.edits)], step.cursor_before)

    def redo(self) -> None:
        if step := self.history.pop_redo():
            self._replay([(e.pos, e.removed, e.added) for e in step.edits], step.cursor_after)

    def _replay(self, edits: list[tuple[int, str, str]], cursor_pos: int) -> None:
        """Apply (pos, old, new) replacements without recording them."""
        self._replaying = True
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        for pos, old, new in edits:
            cursor.setPosition(pos)
            cursor.setPosition(pos + len(old), QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(new)
        cursor.endEditBlock()
        self.history.text = self.toPlainText()
        cursor.setPosition(min(cursor_pos, len(self.history.text)))
        self.setTextCursor(cursor)
        self._replaying = False
        self.cue_block = -1
        self._full_refresh()
        self.ensureCursorVisible()

    # --- cursor ---------------------------------------------------------------

    def _on_cursor_moved(self) -> None:
        n = self.textCursor().blockNumber()
        if n != self._cursor_block:
            old = self._cursor_block
            self._cursor_block = n
            if n != self.cue_block:
                self.cue_block = -1
            # Cue detection depends on which line holds the cursor.
            self._refresh_blocks(old - 1, old, n - 1, n)
            self._layout_timer.start()
            self.completer.popup().hide()
        self.elementChanged.emit(EL_NAMES[self.current_element()])
        self.statsChanged.emit()

    # --- keys ---------------------------------------------------------------

    def keyPressEvent(self, e):
        popup = self.completer.popup()
        if popup.isVisible() and e.key() in (
            Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
        ):
            e.ignore()  # the completer handles these
            return
        self.history.begin(self.textCursor().position())
        try:
            self._handle_key(e)
        finally:
            self.history.end(self.textCursor().position())
        # Classify and lay out right away so every text step is directly followed
        # by its own layout step (undo/redo rely on that).
        self._refresh_timer.stop()
        self._layout_timer.stop()
        self._refresh_around_cursor()
        self._apply_layout()
        self.elementChanged.emit(EL_NAMES[self.current_element()])
        if e.text() and (e.text().isprintable() or e.key() == Qt.Key.Key_Backspace):
            self._update_completion()
        else:
            popup.hide()

    def _handle_key(self, e):
        key, mods = e.key(), e.modifiers()
        cursor = self.textCursor()
        block = cursor.block()
        el = self._element(block)
        plain = not (mods & ~Qt.KeyboardModifier.KeypadModifier)
        is_enter = key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        after_break = self._prev_element(block) in AFTER_BREAK

        if e.matches(QKeySequence.StandardKey.Undo):
            return self.undo()
        if e.matches(QKeySequence.StandardKey.Redo):
            return self.redo()

        if is_enter and mods & Qt.KeyboardModifier.ShiftModifier:
            cursor.insertBlock()  # a real line break, not QTextEdit's soft U+2028 separator
            return self.setTextCursor(cursor)

        if key == Qt.Key.Key_Tab and plain:
            return self._tab(cursor)

        text = e.text()
        at_end = cursor.atBlockEnd() and not cursor.hasSelection()

        # "int" + space/"." -> "INT. "
        if text in (" ", ".") and at_end and after_break and block.text().strip().lower() in SCENE_PREFIXES:
            self._replace_block_text(cursor, SCENE_PREFIXES[block.text().strip().lower()] + " ")
            return

        # No double spaces in headings ("INT." + space after the auto-expansion).
        if text == " " and el == El.SCENE and not cursor.hasSelection() and block.text()[cursor.positionInBlock() - 1 : cursor.positionInBlock()] == " ":
            return

        # Parentheticals close themselves.
        if text == "(" and at_end and not block.text().strip() and self._prev_element(block) in IN_DIALOGUE:
            cursor.insertText("()")
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            return self.setTextCursor(cursor)
        if text == ")" and not cursor.hasSelection() and self._char_after(cursor) == ")":
            cursor.movePosition(QTextCursor.MoveOperation.Right)
            return self.setTextCursor(cursor)

        if is_enter and plain and at_end and block.text().strip():
            stripped = block.text().strip()
            if after_break and fountain.TYPED_TRANSITION_RE.match(stripped):
                self._replace_block_text(cursor, fountain.normalize_transition(stripped))
                el = El.TRANSITION if not stripped.lower().startswith("fade in") else El.ACTION
            elif el in (El.SCENE, El.TRANSITION):
                self._replace_block_text(cursor, block.text().upper())
            if el in (El.ACTION, El.SCENE, El.TRANSITION, El.CENTERED, El.DIALOGUE):
                return self._new_paragraph(cursor)
            if el in (El.CHARACTER, El.PARENTHETICAL):
                self.cue_block = -1
                cursor.insertText("\n")
                return self.setTextCursor(cursor)

        auto_caps = block.blockNumber() == self.cue_block or el in (El.SCENE, El.TRANSITION)
        if "(" in block.text()[: cursor.positionInBlock()]:
            auto_caps = False  # (cont'd) and friends may stay lowercase
        if auto_caps and text and text.isprintable() and text != text.upper() and not (mods & Qt.KeyboardModifier.ControlModifier):
            cursor.insertText(text.upper())
            return self.setTextCursor(cursor)

        super().keyPressEvent(e)

    def _prev_element(self, block) -> int:
        prev = block.previous()
        return self._element(prev) if prev.isValid() else -1

    @staticmethod
    def _char_after(cursor: QTextCursor) -> str:
        text, pos = cursor.block().text(), cursor.positionInBlock()
        return text[pos] if pos < len(text) else ""

    def _new_paragraph(self, cursor: QTextCursor) -> None:
        block = cursor.block()
        next_blank = block.next().isValid() and not block.next().text().strip()
        cursor.insertText("\n" if next_blank else "\n\n")
        if next_blank:
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _replace_block_text(self, cursor: QTextCursor, text: str) -> None:
        """Replace the current line, leaving the cursor at its end."""
        if cursor.block().text() == text:
            return
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        self.setTextCursor(cursor)

    def _tab(self, cursor: QTextCursor) -> None:
        block = cursor.block()
        prev_el = self._prev_element(block)
        text = block.text()

        if prev_el in IN_DIALOGUE:
            if not text.strip():
                cursor.insertText("()")
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
            return

        if prev_el in AFTER_BREAK:
            if text.strip():
                pos = cursor.position()
                self._replace_block_text(cursor, text.upper())
                cursor.setPosition(pos)
                self.setTextCursor(cursor)
            self.cue_block = block.blockNumber()

    # --- explicit element changes ------------------------------------------------

    def set_element(self, el: El) -> None:
        """Rewrite the current line so Fountain reads it as `el` (Ctrl+1…6)."""
        cursor = self.textCursor()
        block = cursor.block()
        body = block.text().strip()
        if body[:1] in FORCED_MARKERS and not body.startswith(".."):
            body = body[1:].lstrip()
        body = body.rstrip("<").rstrip()
        if el != El.PARENTHETICAL and body.startswith("(") and body.endswith(")"):
            body = body[1:-1]

        self.history.begin(cursor.position())
        cursor.beginEditBlock()
        if el == El.SCENE:
            body = body.upper()
            text = body if SCENE_RE.match(body) else ("." + body if body else "INT. ")
            self._ensure_blank_before(cursor)
        elif el == El.ACTION:
            forced = body and (fountain.is_caps(body) or SCENE_RE.match(body) or body[0] in "#=[>")
            text = "!" + body if forced else body
        elif el == El.CHARACTER:
            text = body.upper()
            self._ensure_blank_before(cursor)
        elif el == El.PARENTHETICAL:
            inner = body.strip("()")
            text = f"({inner})"
            self._join_with_dialogue_above(cursor)
        elif el == El.DIALOGUE:
            text = body
            self._join_with_dialogue_above(cursor)
        elif el == El.TRANSITION:
            body = body.upper()
            text = body if body.endswith("TO:") or body in ("FADE OUT.", "FADE TO BLACK.") else "> " + body
            self._ensure_blank_before(cursor)
        else:
            text = body
        self._replace_block_text(cursor, text)
        if el == El.PARENTHETICAL:
            cursor.movePosition(QTextCursor.MoveOperation.Left)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.history.end(cursor.position())
        self.cue_block = cursor.blockNumber() if el == El.CHARACTER and not body else -1
        self._refresh_around_cursor()
        self._full_refresh()

    def _ensure_blank_before(self, cursor: QTextCursor) -> None:
        prev = cursor.block().previous()
        if prev.isValid() and prev.text().strip():
            c = QTextCursor(cursor.block())
            c.insertBlock()

    def _join_with_dialogue_above(self, cursor: QTextCursor) -> None:
        """Dialogue can't follow a blank line: remove blanks between it and a cue above."""
        block = cursor.block()
        above = block.previous()
        while above.isValid() and not above.text().strip():
            above = above.previous()
        if not above.isValid() or above.blockNumber() == block.blockNumber() - 1:
            return
        if fountain.is_caps(above.text().strip()) or self._element(above) in (El.PARENTHETICAL, El.DIALOGUE):
            c = QTextCursor(self.document())
            c.setPosition(above.position() + above.length() - 1)
            c.setPosition(block.position() - 1, QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()

    # --- story bible ------------------------------------------------------------------

    def contextMenuEvent(self, e):
        menu = self.createStandardContextMenu()
        # the standard Undo/Redo drive Qt's disabled undo stack; use ours
        for action in menu.actions():
            if action.text().replace("&", "").startswith(("Undo", "Redo")):
                menu.removeAction(action)
        block = self.cursorForPosition(e.pos()).block()
        el = self._element(block)
        target = None
        if el == El.CHARACTER:
            target = ("character", fountain.character_name(block.text()).upper())
        elif el == El.SCENE:
            target = ("location", heading_location(block.text()))
        selected = self.textCursor().selectedText().strip()
        if selected and "\u2029" not in selected and len(selected) <= 60:
            add_bible_menu(menu, selected, self.bible_index, self.bibleAddRequested.emit, self.bibleAliasRequested.emit)
        elif target and target[1]:
            kind, name = target
            verb = "Open" if self.bible_lookup(kind, name) else "Add"
            menu.insertSeparator(menu.actions()[0])
            action = menu.addAction(f"{verb} “{name}” in Story Bible")
            menu.insertAction(menu.actions()[0], action)
            action.triggered.connect(lambda: self.bibleRequested.emit(kind, name))
        menu.exec(e.globalPos())

    # --- completion -------------------------------------------------------------

    def _completion_context(self) -> tuple[str, list[str], str] | None:
        """(kind, candidates, prefix) for the line under the cursor, or None."""
        cursor = self.textCursor()
        block = cursor.block()
        if not cursor.atBlockEnd():
            return None
        text = block.text()
        el = self._element(block)
        lines = self.lines()
        if el == El.CHARACTER or block.blockNumber() == self.cue_block:
            prefix = text.lstrip("@")
            if "(" in prefix:
                ext = prefix.rsplit("(", 1)[1]
                return "extension", fountain.CUE_EXTENSIONS, ext
            names = [n for n, _ in fountain.characters(lines).most_common()]
            names += [n for n in self.bible_names()[0] if n not in names]
            return "character", names, prefix
        if el == El.SCENE:
            if " - " in text:
                return "time", fountain.times_of_day(lines), text.rsplit(" - ", 1)[1]
            here = text.strip().upper()
            locs = [loc for loc, _ in fountain.locations(lines).most_common() if loc != here]
            if m := HEADING_PREFIX_RE.match(text):
                prefix = m.group(0).upper()
                locs += [c for c in (prefix + name for name in self.bible_names()[1]) if c not in locs and c != here]
            return "location", locs, text
        return None

    def _update_completion(self) -> None:
        popup = self.completer.popup()
        context = self._completion_context()
        if context is None or not context[2].strip():
            popup.hide()
            return
        kind, candidates, prefix = context
        self._completion_kind = kind
        model: QStringListModel = self.completer.model()
        if model.stringList() != candidates:
            model.setStringList(candidates)
        self.completer.setCompletionPrefix(prefix)
        count = self.completer.completionCount()
        if count == 0 or (count == 1 and self.completer.currentCompletion().upper() == prefix.upper()):
            popup.hide()
            return
        popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect().translated(self.viewport().pos())
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 16)
        self.completer.complete(rect)

    def _insert_completion(self, completion: str) -> None:
        cursor = self.textCursor()
        prefix = self.completer.completionPrefix()
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix))
        if self._completion_kind == "extension":
            completion += ")"
        elif self._completion_kind == "location":
            completion += " - "
        self.history.begin(cursor.position())
        cursor.insertText(completion)
        self.setTextCursor(cursor)
        self.history.end(cursor.position())
        self._refresh_around_cursor()
        self._apply_layout()
        if self._completion_kind == "location":
            QTimer.singleShot(0, self._update_completion_times)

    def _update_completion_times(self) -> None:
        """After picking a location, offer times of day straight away."""
        model: QStringListModel = self.completer.model()
        self._completion_kind = "time"
        model.setStringList(fountain.times_of_day(self.lines()))
        self.completer.setCompletionPrefix("")
        self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect().translated(self.viewport().pos())
        rect.setWidth(180)
        self.completer.complete(rect)
