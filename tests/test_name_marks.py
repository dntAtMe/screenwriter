from PySide6.QtGui import QTextCharFormat

from conftest import dispose
from screenwriter.bible import CHARACTER, LOCATION, BibleIndex, format_entry
from screenwriter.editors.common import name_span_at, update_name_hover
from screenwriter.editors.prose import ProseEditor
from screenwriter.editors.screenplay import ScreenplayEditor

INDEX = BibleIndex([
    ("m", CHARACTER, format_entry({"name": "Mara"}, "")),
    ("r", LOCATION, format_entry({"name": "Skerry Rock"}, "")),
])


def formats_at(editor, line: int, col: int) -> QTextCharFormat:
    block = editor.document().findBlockByNumber(line)
    ranges = block.layout().formats()  # keep the list alive while reading from it
    for r in ranges:
        if r.start <= col < r.start + r.length:
            return QTextCharFormat(r.format)
    return QTextCharFormat()


def test_prose_names_are_tinted_not_underlined(qapp):
    editor = ProseEditor()
    editor.set_bible(INDEX)
    editor.set_text("Mara walked to Skerry Rock.")
    mara, rock, plain = formats_at(editor, 0, 1), formats_at(editor, 0, 17), formats_at(editor, 0, 7)
    assert mara.background().color().alpha() > 0 and rock.background().color().alpha() > 0
    assert mara.background().color().rgb() != rock.background().color().rgb()  # a colour per kind
    assert plain.background().style() == plain.background().style().NoBrush
    for f in (mara, rock):
        assert f.underlineStyle() == QTextCharFormat.UnderlineStyle.NoUnderline  # underlines are for spelling
    dispose(editor)


def test_hover_deepens_the_tint(qapp):
    editor = ProseEditor()
    editor.resize(700, 300)
    editor.show()
    editor.set_bible(INDEX)
    editor.set_text("Mara walked to Skerry Rock.")
    qapp.processEvents()
    before = formats_at(editor, 0, 1).background().color().alpha()
    cursor = editor.textCursor()
    cursor.setPosition(1)
    point = editor.cursorRect(cursor).center()
    assert name_span_at(editor, point, INDEX) == (0, 0, 4)
    update_name_hover(editor, editor.highlighter, INDEX, point)
    assert formats_at(editor, 0, 1).background().color().alpha() > before
    assert formats_at(editor, 0, 17).background().color().alpha() == formats_at(editor, 0, 20).background().color().alpha()
    update_name_hover(editor, editor.highlighter, INDEX, None)  # the mouse leaves
    assert formats_at(editor, 0, 1).background().color().alpha() == before
    dispose(editor)


def test_point_past_the_end_of_a_line_is_not_a_hover(qapp):
    editor = ProseEditor()
    editor.resize(700, 300)
    editor.show()
    editor.set_bible(INDEX)
    editor.set_text("Owen met Mara")
    qapp.processEvents()
    cursor = editor.textCursor()
    cursor.setPosition(13)
    far_right = editor.cursorRect(cursor).center()
    far_right.setX(far_right.x() + 200)
    assert name_span_at(editor, far_right, INDEX) is None
    dispose(editor)


def test_script_names_are_tinted(qapp):
    editor = ScreenplayEditor()
    editor.bible_index = INDEX
    editor.set_text("EXT. SKERRY ROCK - DUSK\n\nMara climbs the stairs.\n")
    heading, action = formats_at(editor, 0, 6), formats_at(editor, 2, 1)
    assert heading.background().color().alpha() > 0 and action.background().color().alpha() > 0
    assert action.underlineStyle() == QTextCharFormat.UnderlineStyle.NoUnderline
    dispose(editor)
