"""Dice panel: roll anything, and a log of what was rolled (from here or from your notes)."""

from __future__ import annotations

import html
import random
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import dice, theme

QUICK = ["d4", "d6", "d8", "d10", "d12", "d20", "d100", "2d20kh1", "2d20kl1"]
QUICK_LABELS = {"2d20kh1": "Adv.", "2d20kl1": "Dis."}
TIPS = {"2d20kh1": "Advantage: 2d20, keep the higher", "2d20kl1": "Disadvantage: 2d20, keep the lower"}
LOG_LIMIT = 200


class DicePanel(QWidget):
    rolled = Signal(str)  # a one-line summary, for the status bar

    def __init__(self, parent=None, rng: random.Random | None = None):
        super().__init__(parent)
        self.rng = rng or random.SystemRandom()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("2d6+3, 4d6kh3, d20+5…")
        self.entry.returnPressed.connect(self._roll_entry)
        roll = QPushButton("Roll")
        roll.setObjectName("Primary")
        roll.clicked.connect(self._roll_entry)
        top = QHBoxLayout()
        top.addWidget(self.entry, 1)
        top.addWidget(roll)

        grid = QGridLayout()
        grid.setSpacing(4)
        for i, expression in enumerate(QUICK):
            button = QPushButton(QUICK_LABELS.get(expression, expression))
            button.setToolTip(TIPS.get(expression, f"Roll {expression}"))
            button.clicked.connect(lambda _=False, e=expression: self.roll(e))
            grid.addWidget(button, i // 5, i % 5)

        self.log = QListWidget()
        self.log.setWordWrap(True)
        self.log.setObjectName("DiceLog")
        self.last = QLabel()
        self.last.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.last.setTextFormat(Qt.TextFormat.RichText)
        self.last.setMinimumHeight(64)
        hint = QLabel("⌘/Ctrl-click dice like 2d6+3 in your notes to roll them, "
                      "or the die heading a table to roll on it.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(top)
        layout.addLayout(grid)
        layout.addWidget(self.last)
        layout.addWidget(self.log, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(hint, 1)
        bottom.addWidget(clear, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(bottom)
        self._show_last(None)

    def _roll_entry(self) -> None:
        if self.entry.text().strip():
            self.roll(self.entry.text())

    def roll(self, expression: str, source: str = "") -> dice.Roll | None:
        try:
            r = dice.roll(expression, self.rng)
        except dice.DiceError as e:
            self._show_last(None, str(e))
            return None
        self._add(r, source)
        return r

    def roll_table(self, table: dice.Table, source: str = "") -> tuple[dice.Roll, str]:
        r, result = dice.roll_table(table, self.rng)
        self._add(r, source or table.title, result)
        return r, result

    def _add(self, r: dice.Roll, source: str, result: str = "") -> None:
        flag = {"crit": "  ★ natural 20", "fumble": "  ✗ natural 1"}.get(r.natural, "")
        what = f"{source} ({r.expression})" if source else r.expression
        line = f"{what}: {r.total}" + (f" → {result}" if result else "") + flag
        item = QListWidgetItem(f"{datetime.now():%H:%M}  {line}\n{r.detail}")
        item.setToolTip(r.detail)
        self.log.insertItem(0, item)
        while self.log.count() > LOG_LIMIT:
            self.log.takeItem(self.log.count() - 1)
        self._show_last(r, result=result, source=source)
        self.rolled.emit(f"🎲 {line}   {r.detail}")

    def _show_last(self, r: dice.Roll | None, error: str = "", result: str = "", source: str = "") -> None:
        if error:
            self.last.setText(f"<span style='color:#d9534f'>{html.escape(error)}</span>")
            return
        if r is None:
            self.last.setText("<span style='color:gray'>Pick a die, or type a roll.</span>")
            return
        colour = {"crit": "#3f9b5a", "fumble": "#d9534f"}.get(r.natural, theme.tokens()["text"])
        what = html.escape(f"{source} · {r.expression}" if source else r.expression)
        big = f"<div style='font-size:28pt; font-weight:700; color:{colour}'>{r.total}</div>"
        sub = f"<div style='color:gray'>{what} &nbsp; {html.escape(r.detail)}</div>"
        text = f"<div style='font-size:12pt'>{html.escape(result)}</div>" if result else ""
        self.last.setText(big + text + sub)

    def clear(self) -> None:
        self.log.clear()
        self._show_last(None)
