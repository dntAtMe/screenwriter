"""Shortcut hints: hold Ctrl or Alt for a moment and the shortcuts that start with
the keys you're holding appear. Add Shift (or the other one) and the list narrows;
press a key or let go and it disappears.

The list is read from the window's menus, so it's always the real shortcuts.
"""

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QKeyCombination, QObject, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QMainWindow, QMenu, QVBoxLayout, QWidget

Mod = Qt.KeyboardModifier
MODIFIERS = (Mod.ControlModifier, Mod.AltModifier, Mod.ShiftModifier, Mod.MetaModifier)
TRIGGERS = (Mod.ControlModifier, Mod.AltModifier)  # Shift alone types capitals; Meta is the Windows key
KEY_MODIFIER = {
    Qt.Key.Key_Control: Mod.ControlModifier,
    Qt.Key.Key_Alt: Mod.AltModifier,
    Qt.Key.Key_Shift: Mod.ShiftModifier,
    Qt.Key.Key_Meta: Mod.MetaModifier,
}
MODIFIER_KEYS = set(KEY_MODIFIER) | {Qt.Key.Key_AltGr}
DELAY_MS = 600
ROWS_PER_COLUMN = 12

# Keys every text box has, which no menu lists.
TEXT_KEYS = [
    (QKeySequence.StandardKey.Cut, "Cut"),
    (QKeySequence.StandardKey.Copy, "Copy"),
    (QKeySequence.StandardKey.Paste, "Paste"),
    (QKeySequence.StandardKey.SelectAll, "Select All"),
]


@dataclass
class Entry:
    modifiers: Qt.KeyboardModifier
    key: Qt.Key
    name: str
    enabled: bool = True


def _mods(flags) -> Qt.KeyboardModifier:
    out = Mod.NoModifier
    for m in MODIFIERS:
        if m in flags:
            out |= m
    return out


def _count(mods) -> int:
    return sum(1 for m in MODIFIERS if m in mods)


def _label(text: str) -> str:
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


def entries_from(window: QMainWindow) -> list[Entry]:
    """Every shortcut in the window's menus, plus Alt+letter for the menus themselves."""
    out: list[Entry] = []

    def add(action: QAction, name: str) -> None:
        for seq in action.shortcuts():
            if seq.count():
                combo = seq[0]
                out.append(Entry(_mods(combo.keyboardModifiers()), combo.key(), name, action.isEnabled()))

    def walk(menu: QMenu) -> None:
        for action in menu.actions():
            if action.isSeparator() or not action.isVisible():
                continue
            if action.menu():
                walk(action.menu())
            else:
                add(action, _label(action.text()))

    for top in window.menuBar().actions():
        title = top.text()
        i = title.replace("&&", "").find("&")
        if i >= 0 and i + 1 < len(title):
            out.append(Entry(Mod.AltModifier, Qt.Key(ord(title[i + 1].upper())), f"{_label(title)} menu"))
        if top.menu():
            walk(top.menu())

    taken = {(e.modifiers, e.key) for e in out}
    for standard, name in TEXT_KEYS:
        for seq in QKeySequence.keyBindings(standard):
            combo = seq[0]
            if (_mods(combo.keyboardModifiers()), combo.key()) not in taken:
                out.append(Entry(_mods(combo.keyboardModifiers()), combo.key(), name))
                break
    return out


def modifier_text(held) -> str:
    """'Ctrl+Shift+' (or '⌘⇧' on macOS)."""
    text = QKeySequence(QKeyCombination(_mods(held), Qt.Key.Key_A)).toString(QKeySequence.SequenceFormat.NativeText)
    return text.removesuffix("A")


def matching(entries: list[Entry], held) -> list[tuple[str, Entry]]:
    """Shortcuts that use every held modifier, as (what's left to press, entry):
    fewest extra modifiers first, then by key."""
    held = _mods(held)
    seen, rows = set(), []
    for e in entries:
        if any(m in held and m not in e.modifiers for m in MODIFIERS) or (e.modifiers, e.key) in seen:
            continue
        seen.add((e.modifiers, e.key))
        extra = _mods([m for m in MODIFIERS if m in e.modifiers and m not in held])  # not ~held: it drops Alt
        rest = QKeySequence(QKeyCombination(extra, e.key)).toString(QKeySequence.SequenceFormat.NativeText)
        rows.append((_count(extra), int(extra.value), rest, e))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return [(rest, e) for _, _, rest, e in rows]


class HintPanel(QFrame):
    """The overlay: a few columns of "key — what it does"."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("shortcut_hints")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            "#shortcut_hints { background: rgba(32, 34, 38, 235); border-radius: 10px; }"
            "#shortcut_hints QLabel { color: #e8e8e8; background: transparent; }"
            "#shortcut_hints QLabel[role='key'] { color: #f0b35a; font-weight: 600; }"
            "#shortcut_hints QLabel[role='off'] { color: #7c8088; }"
            "#shortcut_hints QLabel[role='title'] { color: #9aa0a8; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 14)
        self.body: QWidget | None = None
        self.hide()

    def show_rows(self, held, rows: list[tuple[str, Entry]]) -> None:
        if self.body is not None:  # a fresh grid each time: no leftover rows or column widths
            self.body.setParent(None)
            self.body.deleteLater()
        self.body = QWidget(self)
        grid = QGridLayout(self.body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        self.layout().addWidget(self.body)
        prefix = modifier_text(held)
        title = QLabel(f"{prefix} …" if rows else f"{prefix} — no shortcuts")
        title.setProperty("role", "title")
        columns = max(1, -(-len(rows) // ROWS_PER_COLUMN))
        per_column = max(1, -(-len(rows) // columns))  # even columns
        grid.addWidget(title, 0, 0, 1, columns * 3)
        for i, (rest, entry) in enumerate(rows):
            col, row = divmod(i, per_column)
            key = QLabel(rest)
            key.setProperty("role", "key")
            key.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            name = QLabel(entry.name)
            if not entry.enabled:
                name.setProperty("role", "off")
            grid.addWidget(key, row + 1, col * 3)
            grid.addWidget(name, row + 1, col * 3 + 1)
            if col < columns - 1:
                grid.setColumnMinimumWidth(col * 3 + 2, 18)
        self.show()  # first: labels get their style sheet fonts when shown, and the size depends on them
        self.body.show()
        grid.activate()
        self.layout().activate()
        self.adjustSize()
        parent = self.parentWidget()
        bottom = parent.height() - (parent.statusBar().height() if parent.statusBar().isVisible() else 0)
        self.move(max(8, (parent.width() - self.width()) // 2), max(8, bottom - self.height() - 24))
        self.raise_()


class ShortcutHints(QObject):
    """Watches the keyboard (application-wide event filter) and drives the panel."""

    def __init__(self, window: QMainWindow):
        super().__init__(window)
        self.window = window
        self.enabled = True
        self.panel = HintPanel(window)
        self.timer = QTimer(self, singleShot=True, interval=DELAY_MS)
        self.timer.timeout.connect(self._show)
        QApplication.instance().installEventFilter(self)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.hide()

    def hide(self) -> None:
        self.timer.stop()
        self.panel.hide()

    def _held(self):
        return _mods(QGuiApplication.queryKeyboardModifiers())

    def _show(self) -> None:
        held = self._held()
        if not self.enabled or QApplication.activeWindow() is not self.window or not any(m in held for m in TRIGGERS):
            return self.hide()
        self.panel.show_rows(held, matching(entries_from(self.window), held))

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.ShortcutOverride):
            if event.key() in MODIFIER_KEYS:
                if kind == QEvent.Type.ShortcutOverride or event.isAutoRepeat():
                    return False
                # Whether modifiers() counts the key going down / up differs by platform.
                key_mod = KEY_MODIFIER.get(event.key(), Mod.NoModifier)
                held = _mods(event.modifiers())
                held = held | key_mod if kind == QEvent.Type.KeyPress else held & ~key_mod
                if not any(m in held for m in TRIGGERS):
                    self.hide()
                elif self.panel.isVisible():
                    QTimer.singleShot(0, self._show)  # narrow / widen the list right away
                elif kind == QEvent.Type.KeyPress:
                    self.timer.start()
            elif kind != QEvent.Type.KeyRelease:
                self.hide()  # a shortcut (or anything else) was pressed
        elif kind in (QEvent.Type.MouseButtonPress, QEvent.Type.ApplicationStateChange) or (
            kind == QEvent.Type.WindowDeactivate and obj is self.window
        ):
            self.hide()  # Ctrl-click, or switching away with the keys still down
        return False
