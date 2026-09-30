from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtTest import QTest

from conftest import dispose
from screenwriter.editors.common import link_at, link_spans
from screenwriter.editors.prose import ProseEditor
from screenwriter.editors.screenplay import ScreenplayEditor

TITLES = {"c3": "Chapter 3", "map": "Story Map"}


def point(editor, line: int, col: int):
    cursor = QTextCursor(editor.document().findBlockByNumber(line))
    cursor.movePosition(QTextCursor.MoveOperation.Right, n=col)
    return editor.cursorRect(cursor).center()


def test_link_spans():
    links = {"chapter 3": "c3"}
    assert link_spans("See [[Chapter 3]] and [[a note]].", links) == [(6, 15, "c3")]
    assert link_spans("[[ chapter 3 ]]", links) == [(2, 13, "c3")]


def test_prose_links_open_on_ctrl_click(qapp):
    editor = ProseEditor()
    editor.resize(700, 300)
    editor.show()
    editor.set_links(TITLES)
    editor.set_text("Go back to [[Chapter 3]] now. [[just a note]]")
    opened = []
    editor.linkOpenRequested.connect(opened.append)
    assert link_at(editor, point(editor, 0, 15)) == "c3"
    assert link_at(editor, point(editor, 0, 36)) is None  # a plain note
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                     point(editor, 0, 15))
    assert opened == ["c3"]
    ranges = editor.document().findBlockByNumber(0).layout().formats()
    fmt = next(QTextCharFormat(r.format) for r in ranges if r.start <= 15 < r.start + r.length)
    assert not fmt.fontItalic() and fmt.fontUnderline() is False
    editor.deleteLater()


def test_typing_brackets_offers_titles(qapp):
    editor = ProseEditor()
    editor.resize(700, 300)
    editor.show()
    editor.set_links(TITLES)
    editor.setFocus()
    QTest.keyClicks(editor, "See [[sto")
    popup = editor.link_completer.popup()
    assert popup.isVisible() and editor.link_completer.currentCompletion() == "Story Map"
    editor._insert_link("Story Map")
    assert editor.text() == "See [[Story Map]]"
    editor.deleteLater()


def test_script_links(qapp):
    editor = ScreenplayEditor()
    editor.resize(700, 300)
    editor.show()
    editor.set_links(TITLES)
    editor.set_text("INT. LAB - NIGHT\n\nShe checks the [[Story Map]].")
    opened = []
    editor.linkOpenRequested.connect(opened.append)
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                     point(editor, 2, 20))
    assert opened == ["map"]
    editor.deleteLater()


def test_window_links_follow_the_binder(qapp, sample_project):
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.open_project(sample_project)
    w.open_document("ch01")
    editor = w.editors["ch01"]
    title = w.project.find("ch02").title
    assert editor.links[title.lower()] == "ch02"
    w.binder.rename("ch02", "Fog Bank")
    w.bible_timer.timeout.emit()
    assert editor.links.get("fog bank") == "ch02" and title.lower() not in editor.links
    assert not getattr(editor, "unsaved", False) and not w.tabs.tabText(w.tabs.indexOf(editor)).endswith("•")  # re-colouring isn't an edit
    editor.linkOpenRequested.emit("ch02")
    assert w.tabs.currentWidget() is w.editors["ch02"]
    dispose(w)
