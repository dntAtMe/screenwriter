import pytest
from conftest import dispose
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from screenwriter.editors.board import BoardEditor
from screenwriter.mainwindow import MainWindow
from screenwriter.quickopen import DoubleShift, Target, rank, score

H, V = Qt.Orientation.Horizontal, Qt.Orientation.Vertical


@pytest.fixture
def window(qapp, sample_project):
    QSettings().clear()
    w = MainWindow()
    w.show()
    w.open_project(sample_project)
    yield w
    dispose(w)


def open_three(window):
    for node_id in ("ch01", "ch02", "pilot"):
        window.open_document(node_id)
    return [window.editors[i] for i in ("ch01", "ch02", "pilot")]


# --- split view -------------------------------------------------------------------------


def test_split_moves_current_tab_beside(window):
    ch01, ch02, pilot = open_three(window)
    window.split(H)
    tabs = window.tabs
    assert tabs.is_split() and tabs.orientation() == H
    assert tabs.panes[1].currentWidget() is pilot and tabs.currentWidget() is pilot
    assert tabs.panes[0].count() == 2
    # indexes run through both panes, as with one tab widget
    assert [tabs.widget(i) for i in range(tabs.count())] == [ch01, ch02, pilot]
    assert tabs.indexOf(pilot) == 2
    window.open_document("ch01")  # already open on the left: that side becomes active
    assert tabs.active is tabs.panes[0] and tabs.currentWidget() is ch01
    window.open_document("ideas")  # new tabs open on the active side
    assert tabs.panes[0].indexOf(window.editors["ideas"]) >= 0


def test_split_down_and_unsplit(window):
    ch01, ch02, pilot = open_three(window)
    window.split(V)
    assert window.tabs.orientation() == V
    window.tabs.unsplit()
    assert not window.tabs.is_split() and window.tabs.count() == 3
    assert window.tabs.currentWidget() is pilot


def test_closing_last_tab_on_one_side_closes_that_side(window):
    ch01, ch02, pilot = open_three(window)
    window.split(H)
    window.close_tab(window.tabs.indexOf(pilot))
    assert not window.tabs.is_split()
    assert window.tabs.count() == 2 and window.tabs.currentWidget() in (ch01, ch02)


def test_move_and_focus_other_side(window):
    ch01, ch02, pilot = open_three(window)
    window.split(H)
    window.tabs.focus_other_pane()
    assert window.tabs.currentWidget() is ch02
    window.tabs.move_to_other_pane()
    assert window.tabs.panes[1].indexOf(ch02) >= 0 and window.tabs.currentWidget() is ch02
    window.tabs.move_to_other_pane()  # back again: its side was left with ch01 only
    assert window.tabs.panes[0].indexOf(ch02) >= 0


def test_split_with_one_tab_does_nothing(window):
    window.open_document("ch01")
    window.split(H)
    assert not window.tabs.is_split()


# --- moving through tabs ----------------------------------------------------------------------


def test_next_previous_and_numbered_tabs(window):
    ch01, ch02, pilot = open_three(window)
    window.tabs.next_tab(1)
    assert window.tabs.currentWidget() is ch01  # wraps around
    window.tabs.next_tab(-1)
    assert window.tabs.currentWidget() is pilot
    window.tabs.go_to_tab(2)
    assert window.tabs.currentWidget() is ch02
    window.tabs.go_to_tab(9)
    assert window.tabs.currentWidget() is pilot
    window.tabs.go_to_tab(7)  # no such tab
    assert window.tabs.currentWidget() is pilot


def test_ctrl_tab_works_from_inside_an_editor(window):
    ch01, ch02, pilot = open_three(window)
    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    pilot.setFocus()
    QTest.keyClick(pilot, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
    assert window.tabs.currentWidget() is ch01
    QTest.keyClick(ch01, Qt.Key.Key_PageDown, Qt.KeyboardModifier.ControlModifier)
    assert window.tabs.currentWidget() is ch02
    assert "\t" not in ch01.text() + ch02.text()


# --- go to document ---------------------------------------------------------------------------


def test_score_prefers_words_and_runs():
    assert score("chk", "Chapter 1 — The Keeper") is not None
    assert score("xyz", "Chapter 1") is None
    assert score("keeper", "Chapter 1 — The Keeper") > score("cptr", "Chapter 1 — The Keeper")
    titles = ["Fog", "Chapter 2 — Fog", "Story Map"]
    ranked = rank("fog", [Target(t, "", "prose", t) for t in titles])
    assert [t.title for t in ranked] == ["Fog", "Chapter 2 — Fog"]


def test_targets_list_open_tabs_first_then_everything(window):
    window.open_document("pilot")
    window.open_document("ch02")
    targets = window._quick_open_targets()
    assert [t.node_id for t in targets[:2]] == ["ch02", "pilot"]  # most recent first
    kinds = {t.node_id: t for t in targets if t.line is None}
    assert kinds["manuscript"].detail == "Corkboard"
    assert kinds["ch01"].detail == "Manuscript"
    cards = [t for t in targets if t.line is not None]
    assert cards and all(t.node_id == "storymap" and t.detail == "Card on Story Map" for t in cards)
    assert not any(t.node_id == "trash" for t in targets)


def test_go_to_card_opens_board_and_selects_it(window):
    card = next(t for t in window._quick_open_targets() if t.line == 1)
    window.go_to(card)
    board = window.tabs.currentWidget()
    assert isinstance(board, BoardEditor) and board.current_line() == 1


def test_go_to_beside_splits(window):
    window.open_document("ch01")
    window.open_document("ch02")
    window.go_to(Target("Pilot", "", "screenplay", "pilot"), beside=True)
    assert window.tabs.is_split()
    assert window.tabs.panes[1].currentWidget() is window.editors["pilot"]


def test_double_shift(qapp, monkeypatch):
    fired = []
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    detector = DoubleShift(host)
    detector.triggered.connect(lambda: fired.append(1))
    monkeypatch.setattr("screenwriter.quickopen.QApplication.activeWindow", lambda: host)

    def key(kind, k, mods=Qt.KeyboardModifier.NoModifier):
        detector.eventFilter(host, QKeyEvent(kind, k, mods))

    P, R = QEvent.Type.KeyPress, QEvent.Type.KeyRelease
    key(P, Qt.Key.Key_Shift), key(R, Qt.Key.Key_Shift)
    key(P, Qt.Key.Key_Shift)
    assert fired == [1]
    key(R, Qt.Key.Key_Shift)
    # Shift+A then Shift: typing a capital isn't a tap
    key(P, Qt.Key.Key_Shift), key(P, Qt.Key.Key_A, Qt.KeyboardModifier.ShiftModifier), key(R, Qt.Key.Key_Shift)
    key(P, Qt.Key.Key_Shift)
    assert fired == [1]
    QApplication.instance().removeEventFilter(detector)
    dispose(host)


def test_location_counts_only_after_a_space():
    targets = [Target("Did the lamp ever go dark?", "Card on Story Map", "board", "storymap", line=3)]
    assert rank("map", targets) == []
    assert rank("map lamp", targets) == targets


def test_narrow_screenplay_keeps_its_shape(qapp):
    from screenwriter.editors.screenplay import ScreenplayEditor

    ed = ScreenplayEditor()
    ed.resize(1000, 600)
    ed.show()
    ed.set_text("INT. ROOM - DAY\n\nMARA\n(to herself)\nRight on time.\n")
    paren = ed.document().findBlockByNumber(3)
    wide = paren.blockFormat().leftMargin()
    ed.resize(360, 600)
    QApplication.processEvents()
    narrow = ed.document().findBlockByNumber(3).blockFormat()
    room = ed.viewport().width() - 2 * ed.document().documentMargin()
    assert narrow.leftMargin() < wide
    assert room - narrow.leftMargin() - narrow.rightMargin() >= room * 0.4  # the (…) still has room
    dispose(ed)
