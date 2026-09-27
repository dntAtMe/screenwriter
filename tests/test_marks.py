from conftest import dispose
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMenu

from screenwriter import bible
from screenwriter.editors.biblemenu import add_cue_menu, add_mark_menu
from screenwriter.editors.common import word_count
from screenwriter.editors.prose import ProseEditor
from screenwriter.editors.screenplay import ScreenplayEditor
from screenwriter.export import manuscript, screenplay
from screenwriter.marks import mark, masked, stands_for, strip_marks

XARDAS = bible.format_entry({"name": "Xardas", "aliases": "the Great Wizard"}, "")
MARA = bible.format_entry({"name": "Mara Quinn"}, "")
INDEX = bible.BibleIndex([("xardas", "character", XARDAS), ("mara", "character", MARA)])
NAMES = bible.all_names(bible.parse_entry(XARDAS)[0], "character")


def test_marks_and_notes():
    text = "Rain. {the hooded figure|Xardas} waited.\n\n[[HOODED FIGURE is Xardas]]"
    assert strip_marks(text).startswith("Rain. the hooded figure waited.")
    assert stands_for(text) == {"HOODED FIGURE": "Xardas"}
    assert len(masked(text)) == len(text) and "Xardas" not in masked(text)
    assert mark("the hooded figure", "Xardas") == "{the hooded figure|Xardas}"


def test_index_finds_marked_mentions_once():
    text = "{the hooded figure|Xardas} met Mara. Later Xardas left.\n\nHOODED FIGURE\nHi.\n\n[[HOODED FIGURE is Xardas]]"
    found = [(m.group(), e.name) for m, e in INDEX.find(text)]
    assert ("the hooded figure", "Xardas") in found
    assert ("Mara", "Mara Quinn") in found and ("Xardas", "Xardas") in found
    assert ("HOODED FIGURE", "Xardas") in found
    assert sum(1 for _, n in found if n == "Xardas") == 3  # the tag's own "Xardas" and the note don't count again
    assert dict((e.name, n) for e, n in INDEX.cast(text))["Xardas"] == 3


def test_appears_in_prose_and_script():
    prose = ("ch1", "Chapter 1", "prose", "Rain lashed the jetty.\n\n{the hooded figure|Xardas} waited.")
    script = ("pilot", "Pilot", "screenplay",
              "EXT. JETTY - NIGHT\n\n{A hooded figure|Xardas} watches.\n\nHOODED FIGURE\nYou're late.\n\n"
              "MARA\nWho are you?\n\n[[HOODED FIGURE is Xardas]]\n")
    report = bible.character_report(NAMES, [prose, script])
    labels = [a.label for a in report.appearances]
    assert "the hooded figure waited." in labels  # shown as written, without the tag
    assert report.speeches == 1 and report.words == 2  # HOODED FIGURE's line is Xardas's
    assert any(a.speaks for a in report.appearances) and len(report.scenes) == 1
    assert bible.character_report(bible.all_names(bible.parse_entry(MARA)[0], "character"), [script]).speeches == 1


def test_exports_print_the_phrase():
    md = manuscript.compile_markdown([("One", "# One\n\n{The hooded figure|Xardas} waited.")])
    assert "The hooded figure waited." in md and "Xardas" not in md
    assert screenplay.clean("{A hooded figure|Xardas} watches.", screenplay.El.ACTION) == "A hooded figure watches."
    fdx = screenplay.to_fdx("EXT. A - DAY\n\n{A hooded figure|Xardas} watches.\n\n[[HOODED FIGURE is Xardas]]")
    assert "Xardas" not in fdx
    assert word_count("{the hooded figure|Xardas} waited") == 4


def _select(editor, phrase):
    start = editor.text().index(phrase)
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(start + len(phrase), QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    return start


def _choose(menu: QMenu, title_start: str, item: str):
    sub = next(a.menu() for a in menu.actions() if a.menu() and a.menu().title().startswith(title_start))
    next(a for a in sub.actions() if a.text() == item).trigger()


def test_marking_in_prose(qapp):
    ed = ProseEditor()
    ed.set_text("the hooded figure waited. Later the hooded figure left, and the hooded figure smiled.")
    start = _select(ed, "the hooded figure")
    menu = QMenu()
    add_mark_menu(menu, ed, INDEX, start + 3)
    _choose(menu, "“the hooded figure” is", "Xardas")
    assert ed.text().startswith("{the hooded figure|Xardas} waited.")
    ed.undo()  # one undoable step
    assert ed.text().startswith("the hooded figure waited.")

    _select(ed, "the hooded figure")
    menu = QMenu()
    add_mark_menu(menu, ed, INDEX, 3)
    _choose(menu, "Every “the hooded figure” here (3)", "Xardas")
    assert ed.text().count("{the hooded figure|Xardas}") == 3

    menu = QMenu()  # right-click on a mark: take it off again
    add_mark_menu(menu, ed, INDEX, 5)
    next(a for a in menu.actions() if a.text().startswith("Remove mark")).trigger()
    assert ed.text().startswith("the hooded figure waited.") and ed.text().count("|Xardas}") == 2
    dispose(ed)


def test_cue_in_a_script(qapp):
    ed = ScreenplayEditor()
    ed.set_text("EXT. JETTY - NIGHT\n\nHOODED FIGURE\nYou're late.\n")
    menu = QMenu()
    add_cue_menu(menu, ed, "HOODED FIGURE", INDEX)
    _choose(menu, "HOODED FIGURE in this script is", "Xardas")
    assert ed.text().rstrip().endswith("[[HOODED FIGURE is Xardas]]")
    assert "HOODED FIGURE" in [l for l, _ in ed.lines()]  # the cue itself is unchanged
    menu = QMenu()
    add_cue_menu(menu, ed, "HOODED FIGURE", INDEX)
    next(a for a in menu.actions() if a.text() == "HOODED FIGURE is no longer Xardas").trigger()
    assert ed.text() == "EXT. JETTY - NIGHT\n\nHOODED FIGURE\nYou're late.\n"
    dispose(ed)
