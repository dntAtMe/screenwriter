from PySide6.QtCore import QSettings
from PySide6.QtGui import QPalette

from conftest import dispose
from screenwriter import theme


def test_dark_and_light_at_runtime(qapp, sample_project):
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.open_project(sample_project)
    w.open_document("ch01")
    editor = w.editors["ch01"]
    try:
        w.set_appearance("dark")
        qapp.processEvents()
        assert theme.is_dark() and qapp.style().name().lower() == "fusion"
        pal = editor.palette()
        assert pal.color(QPalette.ColorRole.Base).lightness() < 128
        assert pal.color(QPalette.ColorRole.Window) == pal.color(QPalette.ColorRole.Base)  # margins look like the page
        assert w.appearance_actions["dark"].isChecked()

        w.set_appearance("light")
        qapp.processEvents()
        assert not theme.is_dark()
        pal = editor.palette()
        assert pal.color(QPalette.ColorRole.Base).lightness() > 128
        assert pal.color(QPalette.ColorRole.Window) == pal.color(QPalette.ColorRole.Base)
    finally:
        QSettings().clear()
        theme.apply()  # back to how the tests started
        dispose(w)


def test_ctrl_s_says_it_saved(qapp, sample_project):
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.open_project(sample_project)
    w.open_document("ch01")
    editor = w.editors["ch01"]
    editor.textCursor().insertText("New line. ")
    assert w.save_label.text() == "Editing…"
    w.save_now()
    assert (sample_project / "docs" / "ch01.md").read_text(encoding="utf-8").startswith("New line. ")
    assert w.save_label.text().startswith("✓ Saved")
    assert "Saved" in w.statusBar().currentMessage()
    dispose(w)
