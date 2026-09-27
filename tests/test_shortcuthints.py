from conftest import dispose
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence

from screenwriter.mainwindow import MainWindow
from screenwriter.shortcuthints import Entry, entries_from, matching, modifier_text

Mod = Qt.KeyboardModifier
CTRL, ALT, SHIFT = Mod.ControlModifier, Mod.AltModifier, Mod.ShiftModifier


def names(rows):
    return [e.name for _, e in rows]


def test_matching_keeps_shortcuts_with_every_held_modifier():
    entries = [
        Entry(CTRL | SHIFT, Qt.Key.Key_N, "New Project"),
        Entry(CTRL, Qt.Key.Key_N, "New Prose"),
        Entry(CTRL | ALT, Qt.Key.Key_N, "New Screenplay"),
        Entry(ALT, Qt.Key.Key_F, "File menu"),
    ]
    assert names(matching(entries, CTRL)) == ["New Prose", "New Screenplay", "New Project"] or \
        names(matching(entries, CTRL))[0] == "New Prose"  # plain Ctrl+… first
    assert names(matching(entries, CTRL | SHIFT)) == ["New Project"]
    assert names(matching(entries, ALT)) == ["File menu", "New Screenplay"]
    rest = dict((e.name, r) for r, e in matching(entries, CTRL))
    assert rest["New Prose"] == QKeySequence("N").toString(QKeySequence.SequenceFormat.NativeText)
    assert rest["New Project"] == QKeySequence("Shift+N").toString(QKeySequence.SequenceFormat.NativeText)
    assert rest["New Screenplay"] == QKeySequence("Alt+N").toString(QKeySequence.SequenceFormat.NativeText)


def test_modifier_text():
    assert modifier_text(CTRL | SHIFT) == QKeySequence("Ctrl+Shift+A").toString(QKeySequence.SequenceFormat.NativeText)[:-1]


def test_entries_come_from_the_menus(qapp):
    w = MainWindow()
    entries = entries_from(w)
    found = {(e.modifiers, e.key): e.name for e in entries}
    assert found[(CTRL | ALT, Qt.Key.Key_N)] == "New Screenplay"
    assert found[(ALT, Qt.Key.Key_F)] == "File menu"
    assert found[(CTRL, Qt.Key.Key_1)] == "Scene Heading"
    assert "Copy" in found.values()
    dispose(w)


def test_panel_follows_held_keys(qapp, monkeypatch):
    w = MainWindow()
    w.show()
    hints = w.shortcut_hints
    held = {"mods": CTRL}
    monkeypatch.setattr(hints, "_held", lambda: held["mods"])
    monkeypatch.setattr("screenwriter.shortcuthints.QApplication.activeWindow", lambda: w)

    def key(kind, k, mods):
        hints.eventFilter(w, QKeyEvent(kind, k, mods))

    key(QEvent.Type.KeyPress, Qt.Key.Key_Control, CTRL)
    assert hints.timer.isActive() and not hints.panel.isVisible()
    hints.timer.timeout.emit()
    assert hints.panel.isVisible()
    key(QEvent.Type.KeyPress, Qt.Key.Key_N, CTRL)  # the shortcut itself
    assert not hints.panel.isVisible()

    key(QEvent.Type.KeyPress, Qt.Key.Key_Control, CTRL)
    hints.timer.timeout.emit()
    key(QEvent.Type.KeyRelease, Qt.Key.Key_Control, CTRL)  # let go
    assert not hints.panel.isVisible()

    hints.set_enabled(False)
    key(QEvent.Type.KeyPress, Qt.Key.Key_Control, CTRL)
    hints.timer.timeout.emit()
    assert not hints.panel.isVisible()
    dispose(w)
