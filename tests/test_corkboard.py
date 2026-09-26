import json
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from screenwriter.corkboard import FOOTER_ROLE, SYNOPSIS_ROLE, CorkboardView
from screenwriter.mainwindow import MainWindow
from screenwriter.project import Node

SAMPLE = Path(__file__).parent.parent / "examples" / "The Lighthouse"


@pytest.fixture
def window(qapp, tmp_path):
    QSettings().clear()
    shutil.copytree(SAMPLE, tmp_path / "sample")
    w = MainWindow()
    w.open_project(tmp_path / "sample")
    yield w
    w.close()


def binder_json(window) -> dict:
    return json.loads((window.project.path / "project.json").read_text())


def children(window, folder_id):
    return [n.id for n in window.binder.children_of(folder_id)]


def test_node_synopsis_and_label_round_trip():
    node = Node("a", "A", "prose", synopsis="She arrives.", label="red")
    assert Node.from_dict(node.to_dict()) == node
    assert "synopsis" not in Node("b", "B", "prose").to_dict()


def test_open_corkboard_shows_folder_children(window):
    window.open_corkboard("manuscript")
    view = window.tabs.currentWidget()
    assert isinstance(view, CorkboardView)
    assert window.tabs.tabText(window.tabs.currentIndex()) == "Manuscript — Corkboard"
    assert view.ids() == children(window, "manuscript")
    assert view.item(0).data(FOOTER_ROLE).endswith("words")


def test_synopsis_edit_saves_to_project(window):
    window.open_corkboard("manuscript")
    view = window.tabs.currentWidget()
    view.item(0).setData(SYNOPSIS_ROLE, "Mara keeps the light; a stranger comes.")
    first = binder_json(window)["binder"][0]["children"][0]
    assert first["synopsis"] == "Mara keeps the light; a stranger comes."
    assert window.binder.find_item(first["id"]).toolTip(0) == "Mara keeps the light; a stranger comes."


def test_reorder_cards_reorders_binder(window):
    window.open_corkboard("manuscript")
    view = window.tabs.currentWidget()
    before = view.ids()
    item = view.takeItem(0)
    view.addItem(item)  # drag first card to the end
    view._apply_order()
    assert children(window, "manuscript") == before[1:] + before[:1]
    assert [c["id"] for c in binder_json(window)["binder"][0]["children"]] == before[1:] + before[:1]


def test_binder_changes_refresh_corkboard(window):
    window.open_corkboard("manuscript")
    view = window.tabs.currentWidget()
    n = view.count()
    new_id = view.add_card("prose", "Chapter 3 — Signal")
    assert view.count() == n + 1 and view.ids()[-1] == new_id
    assert window.tabs.currentWidget() is view  # didn't jump to the new document
    window._refresh_outline()
    assert window.outline.topLevelItemCount() == n + 1
    window.binder.trash(new_id)
    assert new_id not in view.ids()
    window.binder.rename(view.ids()[0], "Renamed")
    assert view.item(0).text() == "Renamed"


def test_label_and_open(window):
    window.open_corkboard("manuscript")
    view = window.tabs.currentWidget()
    view.clearSelection()
    view.item(0).setSelected(True)
    view._set_label("green")
    assert binder_json(window)["binder"][0]["children"][0]["label"] == "green"
    first = view.ids()[0]
    view._open(view.item(0))
    assert window.tabs.currentWidget() is window.editors[first]


def test_corkboard_tab_restored_with_project(window, qapp):
    path = window.project.path
    window.open_corkboard("manuscript")
    window.close_project()
    window.open_project(path)
    assert isinstance(window.editors.get("manuscript"), CorkboardView)


def test_selected_document_opens_its_folders_corkboard(window):
    window.binder.setCurrentItem(window.binder.find_item(children(window, "manuscript")[0]))
    window.open_selected_corkboard()
    assert isinstance(window.tabs.currentWidget(), CorkboardView)
    assert window.tabs.currentWidget().node_id == "manuscript"
