"""Formatting toolbar above the editor.

Buttons for the markup you'd otherwise type or reach with a shortcut: screenplay
elements and Fountain marks in a script, Markdown in prose and notes. What it
shows follows the current tab.

The edits themselves are plain functions on a QTextCursor, so they work the same
in every text editor and are easy to test.
"""

import re
from typing import Callable

from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence, QTextCursor
from PySide6.QtWidgets import QToolBar

from .editors import screenplay
from .editors.prose import ProseEditor
from .editors.screenplay import ScreenplayEditor
from .fountain import EL_NAMES, El

HEADING_MARK_RE = re.compile(r"^#{1,6}\s*")
QUOTE_MARK_RE = re.compile(r"^>\s?")
SCRIPT_MARK_RE = re.compile(r"^(#{1,6}|=(?!==))\s*")  # a script line is a section or a synopsis
CENTERED_RE = re.compile(r"^>\s*(.*?)\s*<$")
SECRET_MARK_RE = re.compile(r"^(?:gm|secret)\s*:\s?", re.IGNORECASE)

ELEMENT_LABELS = {
    El.SCENE: "Scene",
    El.ACTION: "Action",
    El.CHARACTER: "Character",
    El.PARENTHETICAL: "Paren.",
    El.DIALOGUE: "Dialogue",
    El.TRANSITION: "Transition",
}


# --- edits ---------------------------------------------------------------------------


def _plain(cursor: QTextCursor) -> str:
    return cursor.document().toPlainText()


def _run(text: str, char: str) -> int:
    """How many times `char` repeats at the start of `text`."""
    return len(text) - len(text.lstrip(char))


def _is_wrapped(text: str, open_: str, close: str) -> bool:
    if len(text) < len(open_) + len(close) or not (text.startswith(open_) and text.endswith(close)):
        return False
    if open_ == close and len(set(open_)) == 1:
        # "*" must not mistake "**bold**" for italic; "***both***" is both.
        return _run(text, open_[0]) in (len(open_), 3) and _run(text[::-1], open_[0]) in (len(open_), 3)
    return True


def toggle_wrap(cursor: QTextCursor, open_: str, close: str | None = None) -> None:
    """Wrap the selection in marks (**bold**, [[note]]), or remove them if it has them.
    With nothing selected, insert an empty pair and put the cursor inside."""
    close = open_ if close is None else close
    if not cursor.hasSelection():
        pos = cursor.position()
        cursor.insertText(open_ + close)
        cursor.setPosition(pos + len(open_))
        return
    full = _plain(cursor)
    start, end = cursor.selectionStart(), cursor.selectionEnd()
    while end > start and full[end - 1].isspace():  # double-click can take the space after a word
        end -= 1
    while start < end and full[start].isspace():
        start += 1
    text = full[start:end]

    def replace(a: int, b: int, new: str, inner_start: int, inner_len: int) -> None:
        cursor.setPosition(a)
        cursor.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(new)
        cursor.setPosition(inner_start)
        cursor.setPosition(inner_start + inner_len, QTextCursor.MoveMode.KeepAnchor)

    if _is_wrapped(text, open_, close):
        inner = text[len(open_) : len(text) - len(close)]
        replace(start, end, inner, start, len(inner))
    elif start >= len(open_) and _is_wrapped(full[start - len(open_) : end + len(close)], open_, close):
        replace(start - len(open_), end + len(close), text, start - len(open_), len(text))
    else:
        replace(start, end, open_ + text + close, start + len(open_), len(text))


def _selected_blocks(cursor: QTextCursor) -> list[int]:
    doc = cursor.document()
    first = doc.findBlock(cursor.selectionStart()).blockNumber()
    last = doc.findBlock(cursor.selectionEnd()).blockNumber()
    return list(range(first, last + 1))


def _rewrite_lines(cursor: QTextCursor, rewrite: Callable[[str], str]) -> None:
    """Rewrite each selected line (or the cursor's line), keeping the cursor on the
    same word and a selection over the same lines."""
    doc = cursor.document()
    numbers = _selected_blocks(cursor)
    had_selection = cursor.hasSelection()
    block = cursor.block()
    from_end = len(block.text()) - cursor.positionInBlock()
    for n in numbers:
        b = doc.findBlockByNumber(n)
        new = rewrite(b.text())
        if new != b.text():
            c = QTextCursor(b)
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            c.insertText(new)
    if had_selection:
        cursor.setPosition(doc.findBlockByNumber(numbers[0]).position())
        last = doc.findBlockByNumber(numbers[-1])
        cursor.setPosition(last.position() + len(last.text()), QTextCursor.MoveMode.KeepAnchor)
    else:
        b = doc.findBlockByNumber(numbers[0])
        cursor.setPosition(b.position() + max(0, len(b.text()) - from_end))


def toggle_line_prefix(cursor: QTextCursor, prefix: str, family: re.Pattern) -> None:
    """Give the lines `prefix` ("## ", "> ") in place of any other of its `family`;
    if they all have it already, take it off."""
    doc = cursor.document()
    lines = [doc.findBlockByNumber(n).text() for n in _selected_blocks(cursor)]
    marked = [ln for ln in lines if ln.strip()]
    remove = bool(marked) and all(
        (m := family.match(ln)) and m.group(0).strip() == prefix.strip() for ln in marked
    )

    def rewrite(line: str) -> str:
        if not line.strip() and len(lines) > 1:
            return line
        body = family.sub("", line, count=1)
        return body if remove else prefix + body

    _rewrite_lines(cursor, rewrite)


def toggle_centered(cursor: QTextCursor) -> None:
    """> THE END <"""

    def rewrite(line: str) -> str:
        if m := CENTERED_RE.match(line.strip()):
            return m.group(1)
        return f"> {line.strip()} <" if line.strip() else line

    _rewrite_lines(cursor, rewrite)


def insert_scene_break(cursor: QTextCursor) -> None:
    """A `***` line of its own after the current paragraph."""
    cursor.clearSelection()
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    before = "" if not cursor.block().text().strip() else "\n\n"
    cursor.insertText(before + "***\n\n")


# --- the toolbar -----------------------------------------------------------------------


class FormatBar(QToolBar):
    def __init__(self, parent=None):
        super().__init__("Formatting", parent)
        self.setObjectName("format_bar")
        self.setMovable(False)
        self.editor: ScreenplayEditor | ProseEditor | None = None
        self.script_only: list[QAction] = []
        self.prose_only: list[QAction] = []

        # Screenplay elements, showing which one the cursor's line is.
        self.elements = QActionGroup(self)
        self.elements.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        self.element_actions: dict[El, QAction] = {}
        for i, el in enumerate(screenplay.SETTABLE, start=1):
            action = self._add(ELEMENT_LABELS[el], f"{EL_NAMES[el]}", lambda e=el: self._set_element(e), f"Ctrl+{i}")
            action.setCheckable(True)
            self.elements.addAction(action)
            self.element_actions[el] = action
            self.script_only.append(action)

        for level in (1, 2, 3):
            self.prose_only.append(self._add(
                f"H{level}", f"Heading {level} — {'#' * level} at the start of the line",
                lambda n=level: self._edit(lambda c: toggle_line_prefix(c, "#" * n + " ", HEADING_MARK_RE)),
            ))

        self.script_only.append(self.addSeparator())
        self.prose_only.append(self.addSeparator())
        bold = self._add("B", "Bold — **text**", lambda: self._edit(lambda c: toggle_wrap(c, "**")))
        italic = self._add("I", "Italic — *text*", lambda: self._edit(lambda c: toggle_wrap(c, "*")))
        underline = self._add("U", "Underline — _text_", lambda: self._edit(lambda c: toggle_wrap(c, "_")))
        self.script_only.append(underline)
        for action, style in ((bold, "bold"), (italic, "italic"), (underline, "underline")):
            font = QFont(self.font())
            font.setBold(style == "bold")
            font.setItalic(style == "italic")
            font.setUnderline(style == "underline")
            action.setFont(font)
        self.addSeparator()

        self.prose_only += [
            self._add("Quote", "Quotation — > at the start of the line",
                      lambda: self._edit(lambda c: toggle_line_prefix(c, "> ", QUOTE_MARK_RE))),
            self._add("Scene Break", "Scene break — a *** line", lambda: self._edit(insert_scene_break)),
            self._add("GM Only", "GM only — GM: at the start of a paragraph; left out of player handouts",
                      lambda: self._edit(lambda c: toggle_line_prefix(c, "GM: ", SECRET_MARK_RE))),
        ]
        self.script_only += [
            self._add("Section", "Section — # Act One (for structure; not printed)",
                      lambda: self._edit(lambda c: toggle_line_prefix(c, "# ", SCRIPT_MARK_RE))),
            self._add("Synopsis", "Synopsis — = what happens (not printed)",
                      lambda: self._edit(lambda c: toggle_line_prefix(c, "= ", SCRIPT_MARK_RE))),
            self._add("Centered", "Centered — > THE END <", lambda: self._edit(toggle_centered)),
        ]
        self._add("Note", "Note to yourself — [[note]] (not exported)",
                  lambda: self._edit(lambda c: toggle_wrap(c, "[[", "]]")))
        self.set_editor(None)

    def _add(self, text: str, tip: str, slot, shortcut: str | None = None) -> QAction:
        action = self.addAction(text)
        if shortcut:
            tip += f" ({QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)})"
        action.setToolTip(tip)
        action.triggered.connect(lambda _=False: slot())
        return action

    def set_editor(self, editor) -> None:
        """The editor the buttons act on: a ScreenplayEditor, a ProseEditor, or None."""
        self.editor = editor
        is_script = isinstance(editor, ScreenplayEditor)
        for action in self.script_only:
            action.setVisible(is_script)
        for action in self.prose_only:
            action.setVisible(isinstance(editor, ProseEditor))
        self.sync_element()

    def sync_element(self) -> None:
        """Check the button of the element the cursor is on."""
        el = self.editor.current_element() if isinstance(self.editor, ScreenplayEditor) else None
        if el == El.DIALOGUE_PENDING:
            el = El.DIALOGUE
        for e, action in self.element_actions.items():
            action.setChecked(e == el)

    def _set_element(self, el: El) -> None:
        if isinstance(self.editor, ScreenplayEditor):
            self.editor.set_element(el)
            self.editor.setFocus()
        self.sync_element()

    def _edit(self, change: Callable[[QTextCursor], None]) -> None:
        if self.editor is not None:
            self.editor.apply_edit(change)
            self.editor.setFocus()
