from PySide6.QtCore import QSettings

from conftest import dispose
from screenwriter import commands
from screenwriter.quickopen import rank


def test_palette_lists_menu_commands_and_runs_one(qapp, sample_project, monkeypatch):
    from screenwriter.commands import CommandPalette
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.open_project(sample_project)
    found = commands.menu_commands(w.menuBar())
    names = {commands.clean(a.text()): path for path, a in found}
    assert names["Typewriter Scrolling"] == "View"
    assert names["Dark"] == "View › Appearance"
    assert "Command Palette…" in names  # (left out when the palette opens)

    targets = commands.targets(found)
    assert rank("tws", targets)[0].title.startswith("Typewriter Scrolling")
    save = next(t for t in targets if t.title == "Save")
    assert save.detail.startswith("File") and "S" in save.detail  # with its shortcut

    ran = []
    def fake_exec(dialog):
        dialog.input.setText("typewriter")
        dialog._accept()
        return True
    monkeypatch.setattr(CommandPalette, "exec", fake_exec)
    w.typewriter_action.toggled.connect(ran.append)
    w.command_palette()
    assert ran == [True] and w.typewriter_action.isChecked()
    QSettings().clear()
    dispose(w)


def test_clean_labels():
    assert commands.clean("&File") == "File"
    assert commands.clean("Q&&A") == "Q&A"
