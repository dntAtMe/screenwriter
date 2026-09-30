"""Command palette: press Ctrl+Shift+P, type part of what you want to do, press Enter.

Lists every command in the menus, with where it lives and its shortcut, matched the same
way as Go to Document ("tws" finds Typewriter Scrolling).
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QMenuBar

from .quickopen import QuickOpen, Target

KIND = "command"


def menu_commands(bar: QMenuBar) -> list[tuple[str, QAction]]:
    """(menu path, action) for every enabled command in the menus, in menu order."""
    out: list[tuple[str, QAction]] = []

    def walk(menu: QMenu, path: str) -> None:
        for action in menu.actions():
            if action.isSeparator() or not action.isVisible():
                continue
            name = clean(action.text())
            if action.menu() is not None:
                walk(action.menu(), f"{path} › {name}" if path else name)
            elif name and action.isEnabled():
                out.append((path, action))

    for action in bar.actions():
        if action.menu() is not None:
            walk(action.menu(), clean(action.text()))
    return out


def clean(text: str) -> str:
    """A menu label without its mnemonic: "&File" → "File", "Q&&A" → "Q&A"."""
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").strip()


def targets(commands: list[tuple[str, QAction]]) -> list[Target]:
    out = []
    for i, (path, action) in enumerate(commands):
        keys = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        title = clean(action.text())
        if action.isCheckable():
            title += "  ✓" if action.isChecked() else ""
        out.append(Target(title, f"{path}   {keys}".strip(), KIND, str(i)))
    return out


class CommandPalette(QuickOpen):
    """The popup; `action` is the chosen command once accepted."""

    def __init__(self, bar: QMenuBar, parent=None, exclude: tuple[QAction, ...] = ()):
        self.commands = [(p, a) for p, a in menu_commands(bar) if a not in exclude]
        super().__init__(targets(self.commands), {}, parent)
        self.input.setPlaceholderText("Run a command…")
        self.action: QAction | None = None
        self.accepted.connect(self._chosen)

    def _chosen(self) -> None:
        if self.chosen is not None:
            self.action = self.commands[int(self.chosen.node_id)][1]
