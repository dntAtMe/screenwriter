import random

import pytest

from screenwriter import dice


class Fixed(random.Random):
    """Rolls the given values in order."""

    def __init__(self, *values):
        super().__init__()
        self.values = list(values)

    def randint(self, a, b):
        return self.values.pop(0)


def test_roll_expressions():
    r = dice.roll("2d6+3", Fixed(4, 2))
    assert (r.total, r.detail, r.expression) == (9, "[4, 2] + 3", "2d6+3")
    assert dice.roll("d20", Fixed(20)).natural == "crit"
    assert dice.roll("d20+5", Fixed(1)).natural == "fumble"
    assert dice.roll("2d20", Fixed(1, 5)).natural == ""
    adv = dice.roll("2d20kh1", Fixed(7, 15))
    assert (adv.total, adv.detail) == (15, f"[{dice.struck(7)}, 15]")
    stats = dice.roll("4d6kl3 - 1", Fixed(6, 1, 3, 2))
    assert (stats.total, stats.detail) == (5, f"[{dice.struck(6)}, 1, 3, 2] − 1")
    assert dice.roll("d%", Fixed(42)).total == 42
    assert dice.roll("1d8 + 1d6 + 2", Fixed(3, 5)).total == 10


@pytest.mark.parametrize("bad", ["", "hello", "2d", "d0", "500d6", "2d6+", "2x6"])
def test_bad_rolls(bad):
    with pytest.raises(dice.DiceError):
        dice.roll(bad)


def test_find_in_text():
    text = "The ogre hits for 2d8+4 (or d20 to dodge); add6 isn't a roll, nor is 3d6x. Fireball: 8d6."
    assert [m.group(0) for m in dice.find(text)] == ["2d8+4", "d20", "8d6"]
    assert [m.group(0) for m in dice.find("Attack 1d20 + 5 then 2d6 − 1d4")] == ["1d20 + 5", "2d6 − 1d4"]


TABLE = """# Rumours

## In the tavern
| d6 | Rumour |
|----|--------|
| 1–2 | The well is poisoned. |
| 3 | A dragon was seen. |
| 4-5 | The mayor is missing. |
| 6+ | Free ale tonight. |

Not a table row.

| Name | Job |
|---|---|
| Vex | Fence |
"""


def test_random_tables():
    [table] = dice.tables(TABLE)
    assert (table.die, table.title, table.line) == ("d6", "In the tavern", 3)
    assert [table.result(n) for n in (1, 2, 3, 5, 6)] == [
        "The well is poisoned.", "The well is poisoned.", "A dragon was seen.", "The mayor is missing.", "Free ale tonight."]
    assert dice.table_at(TABLE, 6) is table or dice.table_at(TABLE, 6).line == 3
    assert dice.table_at(TABLE, 11) is None
    r, result = dice.roll_table(table, Fixed(3))
    assert (r.total, result) == (3, "A dragon was seen.")


def test_panel_rolls_and_logs(qapp):
    from screenwriter.dicepanel import DicePanel

    panel = DicePanel(rng=Fixed(20, 3, 4, 2))
    lines = []
    panel.rolled.connect(lines.append)
    assert panel.roll("d20").natural == "crit"
    assert "natural 20" in panel.log.item(0).text()
    panel.entry.setText("2d6+1")
    panel.entry.returnPressed.emit()
    assert panel.log.count() == 2 and panel.log.item(0).text().split("\n")[0].endswith("2d6+1: 8")
    [table] = dice.tables(TABLE)
    r, result = panel.roll_table(table)
    assert result == "The well is poisoned." and "In the tavern (d6): 2 → The well is poisoned." in lines[-1]
    assert panel.roll("nonsense") is None and "Not a dice roll" in panel.last.text()
    assert panel.log.count() == 3
    panel.deleteLater()


def test_editor_offers_dice_and_tables(qapp):
    from PySide6.QtCore import QPoint

    from screenwriter.editors.prose import ProseEditor

    editor = ProseEditor()
    editor.resize(700, 500)
    editor.set_text("The ogre hits for 2d8+4.\n\n" + TABLE)
    expressions, tables = [], []
    editor.diceRollRequested.connect(expressions.append)
    editor.tableRollRequested.connect(tables.append)

    def point(line: int, col: int) -> QPoint:
        from PySide6.QtGui import QTextCursor

        cursor = QTextCursor(editor.document().findBlockByNumber(line))
        cursor.movePosition(QTextCursor.MoveOperation.Right, n=col)
        return editor.cursorRect(cursor).center()

    assert editor.dice_at(point(0, 20)) == ("2d8+4", None)
    assert editor.dice_at(point(0, 3)) is None
    expression, table = editor.dice_at(point(5, 3))  # "| d6 | Rumour |"
    assert expression == "d6" and table.title == "In the tavern"
    assert editor._roll_at(point(0, 20)) and editor._roll_at(point(5, 3))
    assert expressions == ["2d8+4"] and [t.die for t in tables] == ["d6"]
    editor.deleteLater()


def test_window_rolls_into_the_panel(qapp, tmp_path):
    from PySide6.QtCore import QSettings

    from conftest import dispose
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.create_project(tmp_path / "P", "P")
    node_id = w.binder.add("note", "Encounters", edit=False)
    w.editors[node_id].diceRollRequested.emit("3d6")
    assert w.side.currentWidget() is w.dice and w.dice.log.count() == 1
    assert w.dice.log.item(0).text().split("\n")[0].split("  ", 1)[1].startswith("Encounters (3d6): ")
    dispose(w)
