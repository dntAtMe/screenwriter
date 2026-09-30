from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCursor

from conftest import dispose
from screenwriter import bookmarks


def _to_line(editor, n: int) -> None:
    box = editor.notes if hasattr(editor, "notes") else editor
    cursor = QTextCursor(box.document().findBlockByNumber(n))
    box.setTextCursor(cursor)


def _line(editor) -> int:
    return editor.current_line()


def test_toggle_follow_edits_and_come_back(qapp, sample_project):
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.resize(1000, 600)
    w.show()
    w.open_project(sample_project)
    w.open_document("ch01")
    ch01 = w.editors["ch01"]
    _to_line(ch01, 4)
    w.toggle_bookmark()
    assert bookmarks.lines(ch01) == [(4, ch01.document().findBlockByNumber(4).text())]
    assert ch01.bookmark_gutter.isVisible()

    # the bookmark follows its line when lines are added above it
    cursor = QTextCursor(ch01.document())
    cursor.insertText("New first line.\n\n")
    assert [n for n, _ in bookmarks.lines(ch01)] == [6]

    w.open_document("ch02")
    ch02 = w.editors["ch02"]
    _to_line(ch02, 2)
    w.toggle_bookmark()
    _to_line(ch02, 0)
    w.next_bookmark(1)
    assert w.tabs.currentWidget() is ch02 and _line(ch02) == 2
    w.next_bookmark(1)  # wraps round to the first, in the other chapter
    assert w.tabs.currentWidget() is ch01 and _line(ch01) == 6
    w.next_bookmark(-1)
    assert w.tabs.currentWidget() is ch02 and _line(ch02) == 2

    # kept when the tab closes and the project is reopened, and listed in Go to Document
    w.close_tab(w.tabs.indexOf(ch01))
    w.close_project()
    w.open_project(sample_project)
    marks = [(b.doc, b.line) for b in w._all_bookmarks()]
    assert marks == [("ch01", 6), ("ch02", 2)]
    targets = [t for t in w._quick_open_targets() if t.title.startswith("🔖")]
    assert [(t.node_id, t.line) for t in targets] == marks and targets[0].detail.startswith("Bookmark in ")
    w.go_to(targets[0])
    assert _line(w.editors["ch01"]) == 6

    # toggling again removes it
    _to_line(w.editors["ch01"], 6)
    w.toggle_bookmark()
    assert [(b.doc, b.line) for b in w._all_bookmarks()] == [("ch02", 2)]
    QSettings().clear()
    dispose(w)


def test_saved_bookmarks_find_their_line_again(qapp):
    from screenwriter.editors.prose import ProseEditor

    editor = ProseEditor()
    editor.set_text("One\n\nTwo\n\nThe storm breaks.\n\nFour")
    bookmarks.attach(editor, [(2, "The storm breaks.")])  # edited elsewhere: it moved down two lines
    assert bookmarks.lines(editor) == [(4, "The storm breaks.")]
    assert bookmarks.label("## The storm") == "The storm" and bookmarks.label("  ") == "(empty line)"
    editor.deleteLater()


def test_bookmarks_list_under_the_binder(qapp, sample_project):
    from PySide6.QtCore import Qt

    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.open_project(sample_project)
    listed = lambda: [w.bookmarks_list.item(i).text() for i in range(w.bookmarks_list.count())
                      if w.bookmarks_list.item(i).data(Qt.ItemDataRole.UserRole) is not None]
    assert listed() == [] and w.bookmarks_list.count() == 1  # a hint
    assert w.binder_split.widget(1).isAncestorOf(w.bookmarks_list)  # resizable, below the binder

    w.open_document("ch02")
    ch02 = w.editors["ch02"]
    _to_line(ch02, 2)
    w.toggle_bookmark()
    line = ch02.document().findBlockByNumber(2).text()
    assert listed() == [bookmarks.label(line)] and w.bookmarks_title.text() == "BOOKMARKS  1"
    target = w.bookmarks_list.item(0).data(Qt.ItemDataRole.UserRole)
    assert target.detail == w.project.find("ch02").title

    _to_line(ch02, 0)
    w._open_bookmark_item(w.bookmarks_list.item(0))
    assert _line(ch02) == 2

    w.binder.rename("ch02", "Fog Bank")  # the list follows the binder
    assert w.bookmarks_list.item(0).data(Qt.ItemDataRole.UserRole).detail == "Fog Bank"

    w.remove_bookmark("ch02", 2)
    assert listed() == [] and bookmarks.lines(ch02) == []
    w.close_project()
    assert w.bookmarks_list.count() == 1
    QSettings().clear()
    dispose(w)
