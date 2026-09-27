"""The spelling part of the editors' right-click menu: suggestions for a misspelled word
(filled in when the background checker has them), Add to Project Dictionary, Ignore."""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMenu

from .common import word_at


def add_spelling_menu(menu: QMenu, editor, spell, pos: int, on_add: Callable[[str], None]) -> None:
    if spell is None:
        return
    found = word_at(editor, pos)
    if found is None or spell.status(found[2]) is not False:
        return
    start, end, word = found
    first = menu.actions()[0] if menu.actions() else None
    waiting = menu.addAction("Looking for suggestions…")
    waiting.setEnabled(False)
    menu.insertAction(first, waiting)
    add = menu.addAction(f"Add “{word}” to Project Dictionary")
    add.triggered.connect(lambda: on_add(word))
    ignore = menu.addAction(f"Ignore “{word}”")
    ignore.triggered.connect(lambda: spell.ignore(word))
    for action in (add, ignore):
        menu.insertAction(first, action)
    if first is not None:
        menu.insertSeparator(first)

    def replace(suggestion: str) -> None:
        def change(cursor: QTextCursor) -> None:
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(suggestion)
        editor.apply_edit(change)

    def arrived(for_word: str, suggestions: list) -> None:
        if for_word != word:
            return
        try:
            spell.suggestions.disconnect(arrived)
        except (RuntimeError, TypeError):
            pass
        try:
            if not suggestions:
                waiting.setText("No suggestions")
                return
            for s in suggestions:
                action = menu.addAction(s)
                font = action.font()
                font.setBold(True)
                action.setFont(font)
                action.triggered.connect(lambda _=False, s=s: replace(s))
                menu.insertAction(waiting, action)
            menu.removeAction(waiting)
        except RuntimeError:  # the menu has closed already
            pass

    spell.suggestions.connect(arrived)
    menu.aboutToHide.connect(lambda: _disconnect(spell, arrived))
    spell.request_suggestions(word)


def _disconnect(spell, slot) -> None:
    try:
        spell.suggestions.disconnect(slot)
    except (RuntimeError, TypeError):
        pass
