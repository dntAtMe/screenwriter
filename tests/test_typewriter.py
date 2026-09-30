from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from screenwriter.editors.common import Typewriter
from screenwriter.editors.prose import ProseEditor
from screenwriter.editors.screenplay import ScreenplayEditor


def _middle(editor) -> bool:
    y = editor.cursorRect().center().y()
    return abs(y - editor.viewport().height() / 2) <= editor.fontMetrics().height() * 1.5


def _type_at_end(qapp, editor, text: str) -> None:
    editor.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(editor, text)
    qapp.processEvents()
    qapp.processEvents()


def test_prose_line_stays_in_the_middle(qapp):
    editor = ProseEditor()
    editor.resize(600, 400)
    editor.show()
    editor.set_text("\n\n".join(f"Paragraph {i}." for i in range(80)))
    editor.typewriter = Typewriter(editor)
    editor.typewriter.set_enabled(True)
    _type_at_end(qapp, editor, " More")
    assert _middle(editor)
    editor.typewriter.set_enabled(False)
    assert not editor.centerOnScroll()
    editor.deleteLater()


def test_screenplay_line_stays_in_the_middle_without_an_edit(qapp):
    editor = ScreenplayEditor()
    editor.resize(700, 400)
    editor.show()
    editor.set_text("\n\n".join(f"Action line {i}." for i in range(80)))
    changes = []
    editor.textChanged.connect(lambda: changes.append(1))
    editor.typewriter = Typewriter(editor)
    editor.typewriter.set_enabled(True)
    qapp.processEvents()
    assert changes == [] and not editor.is_modified()  # the room below the text isn't an edit
    assert editor.document().rootFrame().frameFormat().bottomMargin() == editor.viewport().height() // 2
    _type_at_end(qapp, editor, " More")
    assert _middle(editor)
    editor.undo()
    editor.undo()
    assert editor.text().endswith("Action line 79.")  # undo takes back the typing, nothing else
    editor.undo()
    assert editor.text().endswith("Action line 79.")  # (and there's no layout step to undo)
    editor.typewriter.set_enabled(False)
    assert editor.document().rootFrame().frameFormat().bottomMargin() == 0
    editor.deleteLater()


def test_clicking_does_not_scroll(qapp):
    editor = ProseEditor()
    editor.resize(600, 400)
    editor.show()
    editor.set_text("\n\n".join(f"Paragraph {i}." for i in range(80)))
    editor.typewriter = Typewriter(editor)
    editor.typewriter.set_enabled(True)
    qapp.processEvents()
    before = editor.verticalScrollBar().value()
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=editor.viewport().rect().center())
    qapp.processEvents()
    assert editor.verticalScrollBar().value() == before
    editor.deleteLater()
