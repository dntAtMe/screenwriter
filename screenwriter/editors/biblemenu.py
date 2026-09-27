"""Story Bible right-click menus shared by prose and scripts: add a name to the bible, and mark
a description as a character ("the hooded figure" is Xardas, see marks.py)."""

from __future__ import annotations

import re
from typing import Callable

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMenu

from ..bible import CHARACTER, LOCATION, BibleIndex
from ..marks import MARK_RE, mark, masked, stands_for, stands_for_note


def add_bible_menu(
    menu: QMenu,
    name: str,
    index: BibleIndex,
    on_new: Callable[[str, str], None],  # (kind, name)
    on_alias: Callable[[str, str], None],  # (entry node id, name)
) -> QMenu:
    """Insert, at the top of `menu`, a submenu to create an entry from `name`
    or record `name` as another form of an existing entry (e.g. "Kacprowi" for Kacper)."""
    sub = QMenu(f"Add “{name}” to Story Bible", menu)
    sub.addAction("as a new Character", lambda: on_new(CHARACTER, name))
    sub.addAction("as a new Location", lambda: on_new(LOCATION, name))
    others = [e for e in index.entries if name.lower() not in (n.lower() for n in e.names)]
    if others:
        sub.addSeparator()
        header = sub.addAction("as another name for:")
        header.setEnabled(False)
        for kind in (CHARACTER, LOCATION):
            group = sorted((e for e in others if e.kind == kind), key=lambda e: e.name.lower())
            if kind == LOCATION and group and len(group) != len(others):
                sub.addSeparator()
            for entry in group:
                sub.addAction(f"   {entry.name}", lambda _=False, i=entry.node_id: on_alias(i, name))
    first = menu.actions()[0] if menu.actions() else None
    menu.insertMenu(first, sub)
    if first is not None:
        menu.insertSeparator(first)
    return sub


# --- marks: this description is that character --------------------------------------------------------


def mark_at(text: str, pos: int):
    """The {phrase|Name} mark around a position, if any."""
    return next((m for m in MARK_RE.finditer(text) if m.start() <= pos <= m.end()), None)


def _unmarked(text: str, phrase: str) -> list[int]:
    """Where `phrase` stands on its own (not already inside a mark or note)."""
    plain = masked(text)
    return [m.start() for m in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", plain)]


def _replace(editor, spans: list[tuple[int, int, str]]) -> None:
    """Replace (start, end, text) spans as one undoable edit."""
    def change(cursor: QTextCursor) -> None:
        for start, end, text in sorted(spans, reverse=True):
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(text)
    editor.apply_edit(change)


def add_mark_menu(menu: QMenu, editor, index: BibleIndex, click_pos: int) -> None:
    """"This is… ▸ Xardas" for a selected description; "Remove mark" on a marked one."""
    characters = sorted((e for e in index.entries if e.kind == CHARACTER), key=lambda e: e.name.lower())
    text = editor.text()
    first = menu.actions()[0] if menu.actions() else None
    if (m := mark_at(text, click_pos)) is not None:
        phrase, name = m.group(1), m.group(2)
        remove = menu.addAction(f"Remove mark (“{phrase}” is {name})")
        remove.triggered.connect(lambda: _replace(editor, [(m.start(), m.end(), phrase)]))
        menu.insertAction(first, remove)
        return
    cursor = editor.textCursor()
    phrase = cursor.selectedText().strip()
    if not characters or not phrase or "\u2029" in phrase or len(phrase) > 80 or "{" in phrase or "|" in phrase:
        return
    start = min(cursor.position(), cursor.anchor())
    start += len(cursor.selectedText()) - len(cursor.selectedText().lstrip())
    end = start + len(phrase)
    this = QMenu(f"“{phrase}” is…", menu)
    for entry in characters:
        this.addAction(entry.name, lambda _=False, n=entry.name: _replace(editor, [(start, end, mark(phrase, n))]))
    menu.insertMenu(first, this)
    others = _unmarked(text, phrase)
    if len(others) > 1:
        every = QMenu(f"Every “{phrase}” here ({len(others)}) is…", menu)
        for entry in characters:
            every.addAction(entry.name, lambda _=False, n=entry.name: _replace(
                editor, [(p, p + len(phrase), mark(phrase, n)) for p in _unmarked(editor.text(), phrase)]))
        menu.insertMenu(first, every)
    if first is not None:
        menu.insertSeparator(first)


def add_cue_menu(menu: QMenu, editor, cue: str, index: BibleIndex) -> None:
    """For a script's cue: "HOODED FIGURE in this script is… ▸ Xardas", kept as a note
    [[HOODED FIGURE is Xardas]] at the end of the script (never printed)."""
    characters = sorted((e for e in index.entries if e.kind == CHARACTER), key=lambda e: e.name.lower())
    first = menu.actions()[0] if menu.actions() else None
    text = editor.text()
    current = next((n for what, n in stands_for(text).items() if what.upper() == cue.upper()), None)
    if current:
        note = stands_for_note(cue, current)
        remove = menu.addAction(f"{cue} is no longer {current}")
        at = text.find(note)

        def drop() -> None:
            lead = min(2, len(text[:at]) - len(text[:at].rstrip("\n")))  # and the blank line added with it
            _replace(editor, [(at - lead, at + len(note), "")])

        remove.triggered.connect(drop)
        menu.insertAction(first, remove)
        return
    if not characters:
        return
    sub = QMenu(f"{cue} in this script is…", menu)
    for entry in characters:
        def add(_=False, n=entry.name) -> None:
            end = len(editor.text())
            _replace(editor, [(end, end, ("\n\n" if editor.text().strip() else "") + stands_for_note(cue, n))])
        sub.addAction(entry.name, add)
    menu.insertMenu(first, sub)
