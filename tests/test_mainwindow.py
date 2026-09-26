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
