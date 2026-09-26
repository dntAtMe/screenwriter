"""The "Add … to Story Bible" right-click submenu shared by prose and scripts."""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QMenu

from ..bible import CHARACTER, LOCATION, BibleIndex


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
