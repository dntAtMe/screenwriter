import pytest
from conftest import dispose
from PySide6.QtGui import QTextCursor

from screenwriter.editors.prose import ProseEditor
from screenwriter.editors.screenplay import El, ScreenplayEditor
from screenwriter.formatbar import FormatBar


@pytest.fixture
def prose(qapp):
    ed = ProseEditor()
    bar = FormatBar()
    bar.set_editor(ed)
    yield ed, bar
    dispose(ed, bar)


@pytest.fixture
def script(qapp):
    ed = ScreenplayEditor()
    ed.show()
    bar = FormatBar()
    bar.set_editor(ed)
    yield ed, bar
    dispose(ed, bar)


def select(ed, start, end):
    cursor = ed.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(cursor)


def put_cursor(ed, pos):
    cursor = ed.textCursor()
    cursor.setPosition(pos)
    ed.setTextCursor(cursor)


def press(bar, text):
    next(a for a in bar.actions() if a.text() == text and a.isVisible()).trigger()


def test_buttons_follow_the_editor(prose, script, qapp):
    _, bar = prose
    visible = [a.text() for a in bar.actions() if a.isVisible() and a.text()]
    assert "H1" in visible and "Quote" in visible and "Scene" not in visible and "U" not in visible
    bar.set_editor(script[0])
    visible = [a.text() for a in bar.actions() if a.isVisible() and a.text()]
    assert "Scene" in visible and "U" in visible and "H1" not in visible


def test_bold_wraps_and_unwraps_selection(prose):
    ed, bar = prose
    ed.set_text("a quiet night")
    select(ed, 2, 7)
    press(bar, "B")
    assert ed.text() == "a **quiet** night"
    assert ed.textCursor().selectedText() == "quiet"
    press(bar, "B")  # the selection is inside the marks
    assert ed.text() == "a quiet night"


def test_italic_leaves_bold_alone(prose):
    ed, bar = prose
    ed.set_text("**loud**")
    select(ed, 0, 8)
    press(bar, "I")
    assert ed.text() == "***loud***"
    select(ed, 0, 10)
    press(bar, "I")
    assert ed.text() == "**loud**"


def test_marks_with_nothing_selected_put_cursor_inside(prose):
    ed, bar = prose
    ed.set_text("x ")
    put_cursor(ed, 2)
    press(bar, "Note")
    assert ed.text() == "x [[]]"
    assert ed.textCursor().position() == 4


def test_heading_levels_replace_and_toggle(prose):
    ed, bar = prose
    ed.set_text("Chapter One\n\nText")
    put_cursor(ed, 3)
    press(bar, "H1")
    assert ed.text().split("\n")[0] == "# Chapter One"
    assert ed.textCursor().position() == 5  # still after "Cha"
    press(bar, "H2")
    assert ed.text().split("\n")[0] == "## Chapter One"
    press(bar, "H2")
    assert ed.text().split("\n")[0] == "Chapter One"


def test_quote_over_several_lines(prose):
    ed, bar = prose
    ed.set_text("one\ntwo\nthree")
    select(ed, 1, 6)
    press(bar, "Quote")
    assert ed.text() == "> one\n> two\nthree"
    press(bar, "Quote")
    assert ed.text() == "one\ntwo\nthree"


def test_scene_break(prose):
    ed, bar = prose
    ed.set_text("The end of it.")
    put_cursor(ed, 3)
    press(bar, "Scene Break")
    assert ed.text() == "The end of it.\n\n***\n\n"


def test_prose_edit_undoes_in_one_step(prose):
    ed, bar = prose
    ed.set_text("word")
    select(ed, 0, 4)
    press(bar, "B")
    ed.undo()
    assert ed.text() == "word"


def test_element_buttons_set_and_show_the_element(script):
    ed, bar = script
    ed.set_text("EXT. SEA - DAY\n\nmara\n")
    put_cursor(ed, len("EXT. SEA - DAY\n\n"))
    press(bar, "Character")
    assert ed.text().split("\n")[2] == "MARA"
    assert bar.element_actions[El.CHARACTER].isChecked()
    put_cursor(ed, 0)
    bar.sync_element()
    assert bar.element_actions[El.SCENE].isChecked()


def test_script_marks_and_undo(script):
    ed, bar = script
    ed.set_text("She runs.\n")
    select(ed, 4, 8)
    press(bar, "U")
    assert ed.text() == "She _runs_.\n"
    ed.undo()
    assert ed.text() == "She runs.\n"


def test_centered_section_synopsis(script):
    ed, bar = script
    ed.set_text("the end\n")
    put_cursor(ed, 2)
    press(bar, "Centered")
    assert ed.text() == "> the end <\n"
    assert ed.current_element() == El.CENTERED
    press(bar, "Centered")
    assert ed.text() == "the end\n"
    press(bar, "Section")
    assert ed.text() == "# the end\n"
    press(bar, "Synopsis")
    assert ed.text() == "= the end\n"


def test_bar_stays_put_on_a_board(qapp, sample_project):
    """Switching to a board greys the buttons out instead of hiding the bar, so the tabs don't jump."""
    from PySide6.QtCore import QSettings

    from conftest import dispose
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.resize(1100, 700)
    w.show()
    w.open_project(sample_project)
    w.open_document("ch01")
    qapp.processEvents()
    tabs_y = w.tabs.mapTo(w, w.tabs.rect().topLeft()).y()
    shown = [a.text() for a in w.format_bar.actions() if a.isVisible() and a.text()]
    w.open_document("storymap")  # a board
    qapp.processEvents()
    assert w.format_bar.isVisible()
    assert [a.text() for a in w.format_bar.actions() if a.isVisible() and a.text()] == shown
    assert not any(a.isEnabled() for a in w.format_bar.actions() if a.text())
    assert w.tabs.mapTo(w, w.tabs.rect().topLeft()).y() == tabs_y
    w.open_document("ch01")
    assert all(a.isEnabled() for a in w.format_bar.actions() if a.isVisible() and a.text())
    dispose(w)
