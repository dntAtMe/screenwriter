import shutil
from pathlib import Path

import pytest
from conftest import dispose
from PySide6.QtCore import QSettings

from screenwriter import people
from screenwriter.mainwindow import MainWindow

SAMPLE = Path(__file__).parent.parent / "examples" / "The Lighthouse"


@pytest.fixture
def window(qapp, sample_project):
    QSettings().clear()
    w = MainWindow()
    w.open_project(sample_project)
    yield w
    dispose(w)


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


def test_history_save_points_and_versions(window):
    history = window.history
    assert history is not None and history.log()  # a save point when the project opened
    window.open_document("ch02")
    editor = window.editors["ch02"]
    editor.replace_all(editor.text() + "\nMore fog.")
    point = window.save_point()
    assert point is not None and point.auto
    assert window.save_point() is None  # nothing new
    window.save_version("Draft 2")
    assert history.log()[0].title == "Draft 2"
    assert len(history.log("docs/ch02.md")) >= 2


def test_restore_document_version_is_undoable(window):
    for node_id, path in (("ch02", "docs/ch02.md"), ("pilot", "docs/pilot.fountain"), ("storymap", "docs/storymap.board.json")):
        window.open_document(node_id)
        editor = window.editors[node_id]
        before = editor.text()
        old = window.save_point("Original") or window.history.log()[0]
        if node_id == "storymap":
            editor.add_card(0, 600, "Maura", edit=False)
        else:
            editor.replace_all(before + "\nMaura.\n")
        window.save_point()
        window.restore_document_version(old.id, path)
        assert editor.text() == before
        assert window.history.log()[0].title.startswith("Before restoring")
        editor.undo()
        assert "Maura" in editor.text()


def test_restore_deleted_document(window):
    point = window.save_point("Before deleting")
    window.binder.setCurrentItem(window.binder.find_item("ch02"))
    window.binder.delete_current()  # to Trash
    item = window.binder.find_item("ch02")
    window.binder.setCurrentItem(item)
    from PySide6.QtWidgets import QMessageBox

    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.binder.delete_current()  # permanently, from the Trash
    assert window.project.find("ch02") is None
    window.restore_document_version(point.id, "docs/ch02.md")
    assert window.project.find("ch02") is not None
    assert window.binder.find_item("ch02").parent().text(0) == "Manuscript"
    assert "fog" in window.editors["ch02"].text()


def test_restore_whole_project(window):
    point = window.save_point("Start")
    window.binder.setCurrentItem(window.binder.find_item("manuscript"))
    new_id = window.binder.add("prose", "Chapter 3", edit=False)
    window.editors[new_id].replace_all("New chapter.")
    window.save_point()
    window.restore_project_version(point.id)
    assert window.project.find(new_id) is None
    assert window.binder.find_item(new_id) is None
    assert new_id not in window.editors
    assert window.history.log()[0].title == "Before restoring the whole project"


def test_history_dialog_lists_changes(window):
    from screenwriter.historydialog import HistoryDialog

    window.open_document("ch01")
    window.editors["ch01"].replace_all("Changed text.")
    window.save_version("Edited chapter 1")
    dialog = HistoryDialog(
        window.history, window._current_text_for, window._readable,
        window.restore_document_version, window.restore_project_version, window.save_version,
        focus_path="docs/ch01.md", focus_title="Chapter 1",
    )
    assert dialog.timeline.count() >= 1
    assert "Edited chapter 1" in dialog.timeline.item(0).text()
    assert dialog.selected_path() == "docs/ch01.md"
    assert "No changes" in dialog.changes.toHtml()
    dialog.deleteLater()


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
    assert window.tabs.tabText(window.tabs.indexOf(editor)) == "Ada  •"  # named, not saved yet
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


def test_two_windows_sync_through_a_cloud_folder(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from screenwriter.sync import package_name

    notices = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: notices.append(a[1])))
    desktop = window
    package = tmp_path / "Google Drive" / "Screenwriter" / package_name(desktop.project.name)
    package.parent.mkdir(parents=True)
    from screenwriter.synctargets import FolderTarget

    desktop._set_target(FolderTarget(package))
    assert desktop.sync_now().status == "uploaded"

    # the "laptop": another window opening the cloud file into its own folder
    desktop.settings.remove(f"sync_local/{desktop.project.id}")
    laptop = MainWindow()
    laptop.open_project_file(str(package), str(tmp_path / "laptop"), keep_synced=True)
    laptop.history.machine = "Laptop"
    assert laptop.project.path != desktop.project.path and laptop.sync_target.package == package

    # a one-way change reaches an open editor on the other computer
    desktop.open_document("ch01")
    laptop.open_document("ch01")
    laptop.editors["ch01"].replace_all("Written on the laptop.")
    assert laptop.sync_now().status == "uploaded"
    assert desktop.sync_now().status == "downloaded"
    assert desktop.editors["ch01"].text() == "Written on the laptop."

    # both change the same paragraph: ours stays, the review opens, choosing theirs applies it
    reviewed = []

    class FakeReview:
        def __init__(self, records, title_of, apply, parent=None):
            reviewed.extend((title_of(r), r.kept, r.other) for r in records)
            self.records, self.apply = records, apply

        def exec(self):
            assert self.apply(self.records[0], "theirs")

    monkeypatch.setattr("screenwriter.mainwindow.ConflictDialog", FakeReview)
    laptop.editors["ch01"].replace_all("Laptop again.")
    laptop.sync_now()
    desktop.editors["ch01"].replace_all("Desktop again.")
    result = desktop.sync_now()
    assert result.status == "merged" and result.conflicts
    assert reviewed == [("Chapter 1 — The Keeper", "Desktop again.", "Laptop again.")]
    manuscript = desktop.binder.find_item("manuscript")
    titles = [manuscript.child(i).text(0) for i in range(manuscript.childCount())]
    assert not any(t.endswith("(from Laptop)") for t in titles)  # no copy documents any more
    assert desktop.editors["ch01"].text() == "Laptop again."
    assert desktop.conflicts_button.isHidden()
    desktop.editors["ch01"].undo()  # the choice is an ordinary, undoable edit
    assert desktop.editors["ch01"].text() == "Desktop again."

    # the laptop then receives the merge (the choice made above syncs on the next save)
    assert laptop.sync_now().status == "downloaded"
    assert laptop.editors["ch01"].text() == "Desktop again."
    dispose(laptop)


def test_share_a_copy_and_open_it(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    target = tmp_path / "Outbox" / "Story.screenwriter"
    target.parent.mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    window.share_copy()
    assert target.exists()
    window.settings.remove(f"sync_local/{window.project.id}")
    other = MainWindow()
    other.open_project_file(str(target), str(tmp_path / "friend"), keep_synced=False)
    assert other.project.name == window.project.name and other.sync_target is None
    assert other.history.log()  # history came along
    dispose(other)


def test_people_see_each_other(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from screenwriter.sync import package_name
    from screenwriter.synctargets import FolderTarget

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    anna = window
    anna.person_name = lambda: "Anna"
    anna.history.person = "Anna"
    package = tmp_path / "Network Drive" / package_name(anna.project.name)
    package.parent.mkdir()
    anna._set_target(FolderTarget(package))
    anna.sync_now()
    anna.settings.remove(f"sync_local/{anna.project.id}")
    ben = MainWindow()
    ben.person_name = lambda: "Ben"
    ben.open_project_file(str(package), str(tmp_path / "ben"), keep_synced=True)
    ben.history.person = "Ben"

    anna.open_document("ch01")
    ben.open_document("pilot")
    anna._check_people()
    ben._check_people()
    anna._check_people()
    assert [p.person for p in anna.others] == ["Ben"] and anna.others[0].doc_title == "Pilot"
    assert "Ben" in anna.people_label.text() and "Anna" in ben.people_label.text()
    assert anna.binder.presence == {"pilot": [("Ben", people.colour_for("Ben"))]}
    assert anna.presence_banner.isHidden()  # Ben isn't in Anna's chapter

    ben.open_document("ch01")  # now he is
    ben._check_people()
    anna._check_people()
    assert not anna.presence_banner.isHidden() and "Ben" in anna.presence_banner.text()

    # changes carry the writer's name
    ben.editors["ch01"].replace_all("Ben was here.")
    ben.sync_now()
    anna.sync_now()
    assert anna.history.log()[0].person in ("Ben", "Anna")
    assert any(p.person == "Ben" for p in anna.history.log())

    # closing the project takes you off the list
    ben.close_project()
    anna._check_people()
    assert anna.others == [] and anna.presence_banner.isHidden() and anna.binder.presence == {}
    dispose(ben)


def test_updates_from_others(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from screenwriter.sync import package_name
    from screenwriter.synctargets import FolderTarget

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    anna = window
    anna.person_name = lambda: "Anna"
    anna.history.person = "Anna"
    package = tmp_path / "Network Drive" / package_name(anna.project.name)
    package.parent.mkdir()
    anna._set_target(FolderTarget(package))
    anna.sync_now()
    anna.settings.remove(f"sync_local/{anna.project.id}")
    ben = MainWindow()
    ben.person_name = lambda: "Ben"
    ben.open_project_file(str(package), str(tmp_path / "ben"), keep_synced=True)
    ben.history.person = "Ben"
    ben.history.machine = "BEN-PC"

    anna.open_document("ch01")
    anna.side.setCurrentWidget(anna.outline)
    ben.open_document("ch02")
    ben.editors["ch02"].replace_all(ben.editors["ch02"].text() + "\n\nThree more words.")
    ben.sync_now()
    anna.sync_now()

    assert anna.binder.unread == {"ch02"}  # bold in the binder until Anna opens it
    assert anna.side.tabText(anna.side.indexOf(anna.updates)) == "Updates (1)"
    top = anna.updates.tree.topLevelItem(0)
    assert top.text(0).startswith("Ben ·") and top.font(0).bold()
    assert top.child(0).text(0) == "Chapter 2 — Fog — +3 words"

    anna.side.setCurrentWidget(anna.updates)  # looking at it counts as seen
    assert anna.side.tabText(anna.side.indexOf(anna.updates)) == "Updates"
    anna.side.setCurrentWidget(anna.outline)
    anna._refresh_updates()
    assert not anna.updates.tree.topLevelItem(0).font(0).bold()

    anna.open_document("ch02")
    assert anna.binder.unread == set()
    dispose(ben)


def test_arrived_names_everyone(window, tmp_path):
    from screenwriter.updates import arrived

    before = window.history.head()
    for person, doc, text in (("Ben", "ch02", "b"), ("Cleo", "pilot", "c"), ("Ben", "ch01", "b2")):
        window.history.person = person
        window.project.write_text(window.project.find(doc), text)
        window.history.save_point()
    assert arrived(window.history, before) == ["Ben", "Cleo"]
    assert arrived(window.history, window.history.head()) == []


def test_sync_comes_sooner_when_others_are_here(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from screenwriter.sync import package_name
    from screenwriter.synctargets import FolderTarget

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    anna = window
    package = tmp_path / "Network Drive" / package_name(anna.project.name)
    package.parent.mkdir()
    anna._set_target(FolderTarget(package))
    anna.sync_now()
    anna.open_document("ch01")

    # alone: typing doesn't hurry sync
    anna.editors["ch01"].replace_all("Alone.")
    assert not anna.quick_sync_timer.isActive() and anna.sync_timer.interval() == 60 * 1000

    # Ben arrives: sync follows typing, and his changes are looked for every 15 s
    people.write_presence(package, people.Presence("s-ben", "Ben", "BEN-PC", "ch02", "Chapter 2"))
    anna._check_people()
    assert anna.sync_timer.interval() == 15 * 1000
    anna.editors["ch01"].replace_all("Together.")
    assert anna.quick_sync_timer.isActive()
    anna.quick_sync_timer.timeout.emit()
    from screenwriter.sync import read_manifest
    assert read_manifest(package)["head"] == anna.history.head().decode()


def _two_live_windows(window, tmp_path, monkeypatch, doc="ch01"):
    from PySide6.QtWidgets import QMessageBox

    from screenwriter.sync import package_name
    from screenwriter.synctargets import FolderTarget

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    anna = window
    anna.person_name = lambda: "Anna"
    package = tmp_path / "Network Drive" / package_name(anna.project.name)
    package.parent.mkdir()
    anna._set_target(FolderTarget(package))
    anna.sync_now()
    anna.settings.remove(f"sync_local/{anna.project.id}")
    ben = MainWindow()
    ben.person_name = lambda: "Ben"
    ben.open_project_file(str(package), str(tmp_path / "ben"), keep_synced=True)
    for w in (anna, ben):
        w.open_document(doc)
        for timer in (w.live.timer, w.sync_timer, w.presence_timer, w.quick_sync_timer):
            timer.stop()  # ticks by hand below
    return anna, ben


def _type(editor, pos, text):
    from PySide6.QtGui import QTextCursor

    cursor = editor.textCursor()
    cursor.setPosition(pos)
    editor.setTextCursor(cursor)
    for ch in text:  # a key at a time, as a person types
        c = editor.textCursor()
        c.insertText(ch)
        editor.setTextCursor(c)


def _exchange(anna, ben, rounds=2):
    for _ in range(rounds):
        anna.live.tick()
        ben.live.tick()


def test_live_editing(window, tmp_path, monkeypatch):
    anna, ben = _two_live_windows(window, tmp_path, monkeypatch)
    a, b = anna.editors["ch01"], ben.editors["ch01"]
    _exchange(anna, ben)
    assert anna.live.is_live("ch01") and ben.live.is_live("ch01")
    assert anna.live.session.gen == ben.live.session.gen

    # Anna adds to the first paragraph, Ben to the second, at the same time
    first_end = a.text().index("father had used.") + len("father had used.")
    _type(a, first_end, " Anna was here.")
    anna_cursor = a.textCursor().position()
    second_end = b.text().index("brought a stranger.") + len("brought a stranger.")
    _type(b, second_end, " Ben was here.")
    _exchange(anna, ben)
    assert a.text() == b.text()
    assert a.text().count("Anna was here.") == 1 and a.text().count("Ben was here.") == 1
    assert a.textCursor().position() == anna_cursor  # Ben's words came in after it: her cursor stayed put
    assert len(a.extraSelections()) == 1  # Ben's paragraph is tinted…
    assert [c for c in a.viewport().children() if hasattr(c, "text") and c.text() == "Ben"]  # …with his name

    # both typing at the very same spot: every character arrives once, and both copies agree
    end = a.text().index("Try both.]]") + len("Try both.]]")
    _type(a, end, " aaa")
    _type(b, b.text().index("Try both.]]") + len("Try both.]]"), " bbb")
    _exchange(anna, ben)
    assert a.text() == b.text()
    tail = a.text()[end:]
    assert tail.count("a") >= 3 and tail.count("b") >= 3

    # deleting works too
    start = a.text().index(" Anna was here.")
    c = a.textCursor()
    c.setPosition(start)
    c.setPosition(start + len(" Anna was here."), c.MoveMode.KeepAnchor)
    c.removeSelectedText()
    _exchange(anna, ben)
    assert "Anna was here." not in b.text() and a.text() == b.text()

    # sync while live doesn't bring the same words in a second time
    anna.sync_now(quiet=True)
    ben.sync_now(quiet=True)
    anna.sync_now(quiet=True)
    _exchange(anna, ben)
    assert a.text() == b.text() and a.text().count("Ben was here.") == 1

    # with live editing off, nothing flows
    anna.live.enabled = False
    anna.live.leave()
    _type(b, len(b.text()), "\n\nOnly Ben.")
    _exchange(anna, ben)
    assert "Only Ben." not in a.text() and a.extraSelections() == []
    dispose(ben)


def test_live_editing_a_screenplay(window, tmp_path, monkeypatch):
    anna, ben = _two_live_windows(window, tmp_path, monkeypatch, doc="pilot")
    a, b = anna.editors["pilot"], ben.editors["pilot"]
    _exchange(anna, ben)
    _type(a, a.text().index("It's Thursday.") + len("It's Thursday."), " Again.")
    _type(b, len(b.text()), "\n\nEXT. SEA - NIGHT\n\nThe boat is gone.")
    _exchange(anna, ben)
    assert a.text() == b.text()
    assert "It's Thursday. Again." in b.text() and "The boat is gone." in a.text()
    assert "EXT. SEA - NIGHT" in [line for line, _ in a.lines()]
    dispose(ben)


def test_joining_keeps_what_you_wrote_before(window, tmp_path, monkeypatch):
    anna, ben = _two_live_windows(window, tmp_path, monkeypatch)
    a, b = anna.editors["ch01"], ben.editors["ch01"]
    # both type before they've seen each other
    _type(a, a.text().index("father had used.") + len("father had used."), " Before Anna.")
    _type(b, b.text().index("father had used.") + len("father had used."), " Before Ben.")
    _exchange(anna, ben, rounds=3)
    assert a.text() == b.text()
    assert a.text().count("Before Anna.") == 1 and a.text().count("Before Ben.") == 1
    dispose(ben)


def test_open_recent_lists_projects_and_switches(qapp, tmp_path):
    from PySide6.QtCore import QSettings

    from screenwriter.mainwindow import MAX_RECENT, MainWindow
    from screenwriter.project import Project

    QSettings().clear()
    paths = [tmp_path / f"P{i}" for i in range(MAX_RECENT + 2)]
    for p in paths:
        Project.create(p, p.name)
    w = MainWindow()
    for p in paths:
        w.open_project(p)
    w._fill_recent_menu(w.recent_menu)
    names = [a.text() for a in w.recent_menu.actions() if a.text() and not a.isSeparator()]
    assert len([n for n in names if n.startswith("&")]) == MAX_RECENT
    assert names[0] == f"&1  P{MAX_RECENT + 1}" and names[1] == f"&2  P{MAX_RECENT}"
    current = w.recent_menu.actions()[0]
    assert current.isChecked() and not current.isEnabled()  # the open project

    w.recent_menu.actions()[1].trigger()  # switch to the previous one
    assert w.project.name == f"P{MAX_RECENT}"
    assert w.project_title.text() == f"P{MAX_RECENT}"
    assert w._recent()[:2] == [str(paths[-2]), str(paths[-1])]

    w.clear_recent()
    assert w._recent() == [str(paths[-2])]
    w._fill_recent_menu(w.project_title.menu())
    assert "Clear Recent Projects" not in [a.text() for a in w.project_title.menu().actions()]

    QSettings().setValue("recent", str(paths[0]))  # a single saved path comes back as a string
    assert w._recent() == [str(paths[0])]
    QSettings().clear()
    dispose(w)


def test_tab_shows_unsaved_changes_until_saved(qapp, sample_project):
    from PySide6.QtCore import QSettings

    from screenwriter.mainwindow import UNSAVED_DOT, MainWindow

    QSettings().clear()
    w = MainWindow()
    w.open_project(sample_project)
    w.open_document("ch01")
    editor = w.editors["ch01"]
    title = w.tabs.tabText(w.tabs.indexOf(editor))
    assert not title.endswith(UNSAVED_DOT)
    editor.textCursor().insertText("More. ")
    assert w.tabs.tabText(w.tabs.indexOf(editor)) == title + UNSAVED_DOT
    w.save_timer.timeout.emit()  # autosave
    assert w.tabs.tabText(w.tabs.indexOf(editor)) == title
    w.binder.rename("ch01", "Renamed")
    editor.textCursor().insertText("Again. ")
    assert w.tabs.tabText(w.tabs.indexOf(editor)) == "Renamed" + UNSAVED_DOT
    dispose(w)
