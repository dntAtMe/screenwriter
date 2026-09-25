import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from screenwriter.editors.screenplay import El, ScreenplayEditor, classify


def classify_lines(text: str) -> list[El]:
    prev, out = -1, []
    for line in text.split("\n"):
        prev = classify(line, prev)
        out.append(prev)
    return out


@pytest.mark.parametrize(
    "text, expected",
    [
        ("INT. KITCHEN - DAY", El.SCENE),
        ("ext. beach", El.SCENE),
        (".FLASHBACK", El.SCENE),
        ("MARA", El.CHARACTER),
        ("MARA (V.O.)", El.CHARACTER),
        ("@McCLANE", El.CHARACTER),
        ("MARA (40s, tired) winds the clock.", El.ACTION),
        ("CUT TO:", El.TRANSITION),
        ("> THE END <", El.CENTERED),
        ("# ACT ONE", El.SECTION),
        ("= Synopsis here", El.SYNOPSIS),
        ("[[a note]]", El.NOTE),
        ("She walks in.", El.ACTION),
    ],
)
def test_classify_after_blank(text, expected):
    assert classify(text, El.BLANK) == expected


def test_dialogue_block():
    assert classify_lines("MARA\n(quietly)\nHello.\n\nShe leaves.") == [
        El.CHARACTER, El.PARENTHETICAL, El.DIALOGUE, El.BLANK, El.ACTION,
    ]


def test_caps_line_after_action_is_action():
    assert classify_lines("She turns.\nBOOM") == [El.ACTION, El.ACTION]


@pytest.fixture
def editor(qapp):
    ed = ScreenplayEditor()
    ed.show()
    ed.set_text("EXT. SEA - DAY\n\n")
    ed.moveCursor(QTextCursor.MoveOperation.End)
    return ed


def type_scene(ed):
    QTest.keyClicks(ed, "int. kitchen - day")
    QTest.keyClick(ed, Qt.Key.Key_Return)
    QTest.keyClicks(ed, "Mara pours tea.")
    QTest.keyClick(ed, Qt.Key.Key_Return)
    QTest.keyClick(ed, Qt.Key.Key_Tab)
    QTest.keyClicks(ed, "mara")
    QTest.keyClick(ed, Qt.Key.Key_Return)
    QTest.keyClick(ed, Qt.Key.Key_Tab)
    QTest.keyClicks(ed, "sighing")
    QTest.keyClick(ed, Qt.Key.Key_End)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    QTest.keyClicks(ed, "Some things never change.")


def test_typing_produces_fountain(editor):
    type_scene(editor)
    assert editor.text() == (
        "EXT. SEA - DAY\n\nINT. KITCHEN - DAY\n\nMara pours tea.\n\nMARA\n(sighing)\nSome things never change."
    )


def test_elements_are_indented(editor):
    type_scene(editor)
    block = editor.document().lastBlock()
    dialogue, paren, cue = block, block.previous(), block.previous().previous()
    assert [El(b.userState()) for b in (cue, paren, dialogue)] == [El.CHARACTER, El.PARENTHETICAL, El.DIALOGUE]
    assert cue.blockFormat().leftMargin() > paren.blockFormat().leftMargin() > dialogue.blockFormat().leftMargin() > 0


def test_undo_redo_round_trip(editor, qapp):
    type_scene(editor)
    final = editor.text()
    for _ in range(100):
        if not editor.document().isUndoAvailable():
            break
        editor.undo()
        qapp.processEvents()
    assert editor.text() == "EXT. SEA - DAY\n\n"
    while editor.document().isRedoAvailable():
        editor.redo()
        qapp.processEvents()
    assert editor.text() == final


def test_load_leaves_no_undo_history(editor):
    assert not editor.document().isUndoAvailable()
    assert not editor.document().isModified()
