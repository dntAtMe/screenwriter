import pytest
from conftest import dispose
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from screenwriter.editors.screenplay import El, ScreenplayEditor


@pytest.fixture
def editor(qapp):
    ed = ScreenplayEditor()
    ed.show()
    ed.set_text("EXT. SEA - DAY\n\n")
    ed.moveCursor(QTextCursor.MoveOperation.End)
    yield ed
    dispose(ed)


def keys(ed, *steps):
    """Strings are typed; Qt.Key values are pressed; ("shift", key) presses with Shift."""
    for step in steps:
        if isinstance(step, str):
            QTest.keyClicks(ed, step)
        elif isinstance(step, tuple):
            QTest.keyClick(ed, step[1], Qt.KeyboardModifier.ShiftModifier)
        else:
            QTest.keyClick(ed, step)
        ed.completer.popup().hide()  # tests type exact text; completion has its own test


def tail(ed):
    return ed.text()[len("EXT. SEA - DAY\n\n"):]


def elements(ed):
    return [el for _, el in ed.lines()]


def type_scene(ed):
    keys(ed, "int. kitchen - day", Qt.Key.Key_Return, "Mara pours tea.", Qt.Key.Key_Return,
         Qt.Key.Key_Tab, "mara", Qt.Key.Key_Return, Qt.Key.Key_Tab, "sighing", Qt.Key.Key_End,
         Qt.Key.Key_Return, "Some things never change.")


def test_typing_produces_fountain(editor):
    type_scene(editor)
    assert tail(editor) == "INT. KITCHEN - DAY\n\nMara pours tea.\n\nMARA\n(sighing)\nSome things never change."


def test_elements_are_indented(editor):
    type_scene(editor)
    block = editor.document().lastBlock()
    dialogue, paren, cue = block, block.previous(), block.previous().previous()
    assert [El(b.userState()) for b in (cue, paren, dialogue)] == [El.CHARACTER, El.PARENTHETICAL, El.DIALOGUE]
    assert cue.blockFormat().leftMargin() > paren.blockFormat().leftMargin() > dialogue.blockFormat().leftMargin() > 0


def test_scene_prefix_expands(editor):
    keys(editor, "ext ", "jetty")
    assert tail(editor) == "EXT. JETTY"
    assert editor.current_element() == El.SCENE


def test_typed_transition(editor):
    keys(editor, "cut to", Qt.Key.Key_Return)
    assert tail(editor) == "CUT TO:\n\n"
    assert elements(editor)[-3] == El.TRANSITION


def test_caps_word_starting_action_does_not_jump(editor):
    keys(editor, "I")
    assert editor.current_element() == El.ACTION
    keys(editor, " walk in.")
    assert editor.current_element() == El.ACTION


def test_typed_caps_cue_then_dialogue(editor):
    keys(editor, "OWEN", Qt.Key.Key_Return)
    assert elements(editor)[-2:] == [El.CHARACTER, El.DIALOGUE_PENDING]
    keys(editor, "Hello.")
    assert elements(editor)[-2:] == [El.CHARACTER, El.DIALOGUE]


def test_cue_left_without_dialogue_becomes_action(editor):
    keys(editor, "BOOM", Qt.Key.Key_Return)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    assert elements(editor)[-2] == El.ACTION


def test_parenthesis_autoclose(editor):
    keys(editor, "MARA", Qt.Key.Key_Return, "(", "quietly", ")", Qt.Key.Key_Return, "Hi.")
    assert tail(editor) == "MARA\n(quietly)\nHi."


def test_set_element(editor):
    keys(editor, "the lighthouse")
    editor.set_element(El.SCENE)
    assert tail(editor) == ".THE LIGHTHOUSE"
    editor.set_element(El.ACTION)
    assert tail(editor) == "!THE LIGHTHOUSE"
    editor.set_element(El.TRANSITION)
    assert tail(editor) == "> THE LIGHTHOUSE"


def test_set_dialogue_joins_cue(editor):
    editor.set_text("MARA\n\nHello there.")
    editor.moveCursor(QTextCursor.MoveOperation.End)
    editor.set_element(El.DIALOGUE)
    assert editor.text() == "MARA\nHello there."
    assert elements(editor) == [El.CHARACTER, El.DIALOGUE]


def test_character_completion(editor, qapp):
    editor.set_text("MARA\nHi.\n\nOWEN\nHey.\n\n")
    editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(editor, "OW")
    assert editor.completer.popup().isVisible()
    assert editor.completer.currentCompletion() == "OWEN"
    editor._insert_completion("OWEN")
    assert editor.text().endswith("OWEN")


def test_location_completion(editor):
    QTest.keyClicks(editor, "INT. KI")
    assert not editor.completer.popup().isVisible()  # no locations yet besides EXT. SEA
    editor.set_text("INT. KITCHEN - DAY\n\nTea.\n\n")
    editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(editor, "INT. K")
    assert editor.completer.currentCompletion() == "INT. KITCHEN"
    editor._insert_completion("INT. KITCHEN")
    assert editor.text().endswith("INT. KITCHEN - ")


def test_undo_redo_round_trip(editor, qapp):
    type_scene(editor)
    final = editor.text()
    for _ in range(100):
        if not editor.can_undo():
            break
        editor.undo()
        qapp.processEvents()
    assert editor.text() == "EXT. SEA - DAY\n\n"
    while editor.can_redo():
        editor.redo()
        qapp.processEvents()
    assert editor.text() == final


def test_load_leaves_no_undo_history(editor):
    assert not editor.can_undo()
    assert not editor.is_modified()
    keys(editor, "x")
    assert editor.is_modified()
    editor.mark_saved()
    assert not editor.is_modified()
