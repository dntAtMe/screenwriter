import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from screenwriter.mainwindow import MainWindow

SAMPLE = Path(__file__).parent.parent / "examples" / "The Lighthouse"


@pytest.fixture
def window(qapp, tmp_path):
    QSettings().clear()
    shutil.copytree(SAMPLE, tmp_path / "sample")
    w = MainWindow()
    w.open_project(tmp_path / "sample")
    yield w
    w.close()


def test_outline_follows_current_tab(window):
    window.open_document("pilot")
    window._refresh_outline()
    titles = [window.outline.topLevelItem(0).text(0)] + [
        window.outline.topLevelItem(0).child(i).text(0) for i in range(window.outline.topLevelItem(0).childCount())
    ]
    assert titles[0] == "ACT ONE"
    assert "1. EXT. SKERRY ROCK LIGHTHOUSE - DUSK" in titles
    window.open_document("ch01")
    window._refresh_outline()
    assert window.outline.topLevelItem(0).text(0) == "Chapter 1 — The Keeper"


def test_search_and_open(window):
    window.search.query.setText("Thursday")
    window.search.run()
    found = {window.search.results.topLevelItem(i).text(0) for i in range(window.search.results.topLevelItemCount())}
    assert found == {"Chapter 1 — The Keeper  (1)", "Pilot  (1)"}
    window.open_document("pilot")
    editor = window.editors["pilot"]
    pos = editor.text().index("Thursday")
    window.open_at("pilot", pos, 8)
    assert editor.textCursor().selectedText() == "Thursday"


def test_search_skips_trash(window):
    window.binder.setCurrentItem(window.binder.find_item("ch02"))
    window.binder.delete_current()
    window.search.query.setText("fog came in")
    window.search.run()
    assert window.search.results.topLevelItemCount() == 0


def test_add_idea_to_closed_and_open_inbox(window):
    window.add_idea("Mara's father is alive")
    text = window.project.read_text(window.project.find("ideas"))
    assert text.splitlines()[-1].startswith("- Mara's father is alive _(")
    window.open_document("ideas")
    window.add_idea("Second idea")
    assert window.editors["ideas"].text().splitlines()[-1].startswith("- Second idea")
    assert "Second idea" in window.project.read_text(window.project.find("ideas"))


def test_add_idea_creates_inbox_when_missing(window):
    window.project.inbox_id = None
    window.add_idea("New")
    inbox = window.project.find(window.project.inbox_id)
    assert inbox.title == "Idea Inbox"
    assert window.binder.find_item(inbox.id) is not None


def test_board_document(window):
    window.open_document("storymap")
    board = window.editors["storymap"]
    from screenwriter.board import Board

    saved = Board.from_json(window.project.read_text(window.project.find("storymap")))
    assert board.stats() == f"{len(saved.cards)} cards · {len(saved.links)} links"
    window._refresh_outline()
    from PySide6.QtWidgets import QTreeWidgetItemIterator

    labels = []
    it = QTreeWidgetItemIterator(window.outline)
    while it.value():
        labels.append(it.value().text(0))
        it += 1
    assert labels.index("Mara Quinn") == labels.index("The Lighthouse") + 1  # first child under the root
    assert len(labels) == len(saved.cards)
    window.search.query.setText("skipper")
    window.search.run()
    titles = {window.search.results.topLevelItem(i).text(0) for i in range(window.search.results.topLevelItemCount())}
    assert "Story Map  (1)" in titles
    window.open_at("storymap", board.search_text().index("skipper"), 7)
    assert [c.card.id for c in board._selected_cards()] == ["owen"]
    board.add_card(0, 400, "New idea", edit=False)
    window.save_all()
    assert "New idea" in window.project.read_text(window.project.find("storymap"))


def test_find_bar_ignores_board(window):
    window.open_document("storymap")
    assert window._current_text_editor() is None


def test_daily_snapshot_and_restore(window):
    from datetime import date

    from screenwriter.snapshots import AUTO_NAME

    store = window.project.snapshots
    window.open_document("ch02")
    editor = window.editors["ch02"]
    original = editor.text()
    editor.replace_all(original + "\nMore fog.")
    window.save_all()
    snaps = store.list("ch02")
    assert [s.name for s in snaps] == [AUTO_NAME] and snaps[0].text() == original
    editor.replace_all(original + "\nEven more fog.")
    window.save_all()
    assert len(store.list("ch02")) == 1  # one automatic snapshot per day

    window.take_snapshot("Draft 2")
    window.restore_snapshot(window.project.find("ch02"), original)
    assert editor.text() == original
    assert window.project.read_text(window.project.find("ch02")) == original
    assert [s.name for s in store.list("ch02")][:2] == ["Before restore", "Draft 2"]
    editor.undo()
    assert editor.text().endswith("Even more fog.")


def test_restore_board_and_screenplay_are_undoable(window):
    for node_id in ("storymap", "pilot"):
        window.open_document(node_id)
        editor = window.editors[node_id]
        before = editor.text()
        window.restore_snapshot(window.project.find(node_id), window.project.read_text(window.project.find(node_id)).replace("Mara", "Maura"))
        assert "Maura" in editor.text()
        editor.undo()
        assert editor.text() == before


def test_permanent_delete_removes_snapshots(window):
    node = window.project.find("ch02")
    window.project.snapshots.take("ch02", "x", ".md")
    window.project.delete_files(node)
    assert window.project.snapshots.list("ch02") == []


def _add_script(window, text):
    node_id = window.binder.add("screenplay", "Test Script", edit=False)
    window.editors[node_id].set_text(text)
    window.editors[node_id].document().setModified(True)
    return node_id


def test_bible_entry_from_script(window):
    from screenwriter.editors.bible import BibleEditor

    script_id = _add_script(window, "INT. BOAT - DAY\n\nNELL\nAhoy.\n\nNELL\nAgain.\n")
    assert window._find_bible_entry("character", "NELL") is None
    window.open_bible_entry("character", "NELL")
    entry_id = window._find_bible_entry("character", "NELL")
    assert entry_id is not None
    folder = window.binder.find_item(entry_id).parent()
    assert folder.text(0) == "Story Bible"
    editor = window.editors[entry_id]
    assert isinstance(editor, BibleEditor)
    assert editor.inputs["name"].text() == "Nell"
    editor.refresh_appearances()
    assert editor.report().speeches == 2
    assert "2 speeches" in editor.summary.text()
    # opening again finds the same entry, no duplicate
    window.open_bible_entry("character", "NELL")
    assert window.tabs.currentWidget() is editor
    window.save_all()
    assert "name: Nell" in window.project.read_text(window.project.find(entry_id))
    # names feed screenplay completion
    assert "NELL" in window._bible_names()[0]
    assert window.editors[script_id].bible_lookup("character", "NELL") == entry_id


def test_bible_name_and_binder_title_stay_in_sync(window):
    window.binder.setCurrentItem(None)
    entry_id = window.binder.add("character", "New Character", edit=False)
    editor = window.editors[entry_id]
    editor.inputs["name"].setText("Ada")
    editor.inputs["name"].textEdited.emit("Ada")
    assert window.binder.find_item(entry_id).text(0) == "Ada"
    assert window.tabs.tabText(window.tabs.indexOf(editor)) == "Ada"
    item = window.binder.find_item(entry_id)
    item.setText(0, "Ada Lovelace")  # inline rename in the binder
    assert editor.inputs["name"].text() == "Ada Lovelace"


def test_location_entry_and_completion(window):
    script_id = _add_script(window, "INT. LIGHTHOUSE - NIGHT\n\nDark.\n\n")
    window.open_bible_entry("location", "LAMP ROOM")
    script = window.editors[script_id]
    window.tabs.setCurrentWidget(script)
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest

    script.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(script, "INT. LA")
    assert script.completer.currentCompletion() == "INT. LAMP ROOM"


def _prose(window, text):
    node_id = window.binder.add("prose", "Rozdział", edit=False)
    window.editors[node_id].set_text(text)
    return node_id


def test_prose_bible_workflow(window):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest

    from screenwriter.bible import parse_entry

    prose_id = _prose(window, "Kacper przyszedł. Dałem to Kacprowi.\n")
    prose = window.editors[prose_id]

    # a name selected in prose becomes a character, keeping its casing
    window.open_bible_entry("character", "Kacper")
    entry_id = window.bible_index.lookup("Kacper").node_id
    assert window.binder.find_item(entry_id).text(0) == "Kacper"
    assert [m.group(0) for m, _ in prose.bible.find(prose.text())] == ["Kacper"]

    # "Kacprowi" added as another form of Kacper, with the entry closed
    window.close_tab(window.tabs.indexOf(window.editors[entry_id]))
    window.add_bible_alias(entry_id, "Kacprowi")
    fields, _ = parse_entry(window.project.read_text(window.project.find(entry_id)))
    assert fields["aliases"] == "Kacprowi"
    assert [m.group(0) for m, _ in prose.bible.find(prose.text())] == ["Kacper", "Kacprowi"]

    # ...and a stem with the entry open in a tab
    window.open_document(entry_id)
    window.add_bible_alias(entry_id, "Kacpr*")
    assert window.editors[entry_id].inputs["aliases"].text() == "Kacprowi, Kacpr*"
    assert window.bible_index.lookup("Kacprem").node_id == entry_id

    # cast panel for the chapter
    window.tabs.setCurrentWidget(prose)
    window._refresh_outline()
    labels = [window.cast.topLevelItem(0).child(i).text(0) for i in range(window.cast.topLevelItem(0).childCount())]
    assert any(label.startswith("Kacper") and label.endswith("2") for label in labels)

    # completion while writing prose
    prose.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(prose, "Potem Kac")
    assert prose.completer.popup().isVisible() and prose.completer.currentCompletion() == "Kacper"

    # hover / ⌘-click target
    cursor = prose.textCursor()
    cursor.setPosition(2)
    assert prose.bible_at(prose.cursorRect(cursor).center()).node_id == entry_id
