import pytest
from conftest import dispose
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from screenwriter.board import Board, Card, Link, search_text
from screenwriter.editors.board import BoardEditor, CardItem, LinkItem


def test_board_json_round_trip():
    board = Board([Card("a", 0, 0, "Hello"), Card("b", 200, 0, "World", "blue", doc="ch01")], [Link("a", "b")])
    again = Board.from_json(board.to_json())
    assert again == board
    assert Board.from_json("") == Board()


def test_links_to_missing_cards_are_dropped():
    assert Board.from_json('{"cards": [{"id": "a"}], "links": [{"a": "a", "b": "zz"}]}').links == []


def test_tree_order():
    cards = [Card("root", 0, 100, "root"), Card("low", 300, 200, "low"), Card("high", 300, 0, "high"),
             Card("leaf", 600, 0, "leaf"), Card("lone", 0, 400, "lone")]
    links = [Link("root", "low"), Link("root", "high"), Link("high", "leaf"), Link("leaf", "root")]
    board = Board(cards, links)
    # "root" has a parent via the leaf→root cycle, so ordering falls back to position for it
    assert [(d, c.id) for d, c in Board(cards, links[:3]).tree_order()] == [
        (0, "root"), (1, "high"), (2, "leaf"), (1, "low"), (0, "lone"),
    ]
    assert {c.id for _, c in board.tree_order()} == {c.id for c in cards}


def test_search_text_in_tree_order():
    board = Board([Card("b", 300, 0, "second"), Card("a", 0, 5, "first\nline"), Card("c", 0, 200, "third")],
                  [Link("a", "c")])
    assert board.search_text() == "second\nfirst line\nthird"
    assert search_text("not json") == ""


@pytest.fixture
def board(qapp):
    ed = BoardEditor(lambda node_id: {"ch01": "Chapter 1"}.get(node_id, ""))
    ed.resize(800, 600)
    ed.show()
    ed.set_text("")
    yield ed
    dispose(ed)


def type_into(card: CardItem, text: str):
    card.text_item.setPlainText(text)
    card.stop_editing()


def test_mind_map_flow(board):
    root = board.add_card(0, 0)
    type_into(root, "Story")
    child = board.add_child(root)
    type_into(child, "Hero")
    sibling = board.add_sibling(child)
    type_into(sibling, "Villain")

    assert child.pos().x() > root.pos().x() + root.card.w
    assert sibling.pos().x() == child.pos().x() and sibling.pos().y() > child.pos().y()
    saved = Board.from_json(board.text())
    assert {(l.a, l.b) for l in saved.links} == {(root.card.id, child.card.id), (root.card.id, sibling.card.id)}
    assert [o.title for o in board.outline()] == ["Story", "Hero", "Villain"]
    assert board.stats() == "3 cards · 2 links"


def test_keyboard_tab_and_enter(board):
    root = board.add_card(0, 0, "Root", edit=False)
    root.setSelected(True)
    board.setFocus()
    QTest.keyClick(board, Qt.Key.Key_Tab)
    assert len(board.cards) == 2 and board._editing_card() is not None
    board._editing_card().stop_editing()
    QTest.keyClick(board, Qt.Key.Key_Return)
    assert len(board.cards) == 3 and len(board.link_items) == 2


def test_delete_removes_links(board):
    a = board.add_card(0, 0, "A", edit=False)
    b = board.add_card(300, 0, "B", edit=False)
    board.connect_cards(a, b)
    board.scene().clearSelection()
    a.setSelected(True)
    board.delete_selected()
    assert list(board.cards) == [b.card.id] and board.link_items == [] and b.links == []


def test_links_follow_cards(board):
    a = board.add_card(0, 0, "A", edit=False)
    b = board.add_card(300, 0, "B", edit=False)
    board.connect_cards(a, b)
    link: LinkItem = board.link_items[0]
    before = link.path().pointAtPercent(1)
    b.setPos(300, 200)
    assert link.path().pointAtPercent(1) != before


def test_undo_redo(board):
    a = board.add_card(0, 0, "A", edit=False)
    board.add_card(300, 0, "B", edit=False)
    assert len(board.cards) == 2
    board.undo()
    assert list(board.cards) == [a.card.id]
    board.undo()
    assert board.cards == {}
    board.redo()
    board.redo()
    assert len(board.cards) == 2


def test_modified_tracking(board):
    assert not board.is_modified()
    board.add_card(0, 0, "A", edit=False)
    assert board.is_modified()
    board.mark_saved()
    assert not board.is_modified()


def test_reveal_selects_card(board):
    board.add_card(0, 0, "Alpha", edit=False)
    board.add_card(0, 200, "Beta gamma", edit=False)
    text = board.search_text()
    board.reveal(text.index("gamma"))
    assert [c.card.text for c in board._selected_cards()] == ["Beta gamma"]
    assert board.current_line() == 1


def test_linked_card_opens_document(board):
    opened = []
    board.openRequested.connect(opened.append)
    card = board.add_card(0, 0, "Chapter 1", doc="ch01", edit=False)
    view_pos = board.mapFromScene(card.scene_rect().center())
    QTest.mouseDClick(board.viewport(), Qt.MouseButton.LeftButton, pos=view_pos)
    assert opened == ["ch01"]
