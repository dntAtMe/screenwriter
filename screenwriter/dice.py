"""Dice: roll the notation you already write in your notes, and random tables.

    d20  2d6+3  4d6kh3  2d20kl1-1  d%  1d8+1d6+2

kh / kl keep the highest / lowest dice (advantage is 2d20kh1). A random table is a
Markdown table whose first header cell is a die, with a number or a range per row:

    | d6  | Rumour                     |
    |-----|----------------------------|
    | 1–2 | The well is poisoned.      |
    | 3   | …                          |
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

_TERM = r"(?:\d{0,3}d(?:\d{1,4}|%)(?:k[hl]\d{1,3})?|\d{1,4})"
_DICE = r"\d{0,3}d(?:\d{1,4}|%)(?:k[hl]\d{1,3})?"
# in running text: at least one die, then any + / - terms; not inside a word ("add6", "d6x")
DICE_RE = re.compile(rf"(?<![\w.]){_DICE}(?:\s*[+\-−]\s*{_TERM})*(?![\w])", re.IGNORECASE)
TERM_RE = re.compile(r"([+\-−]?)\s*(?:(\d{0,3})d(\d{1,4}|%)(?:k([hl])(\d{1,3}))?|(\d{1,4}))", re.IGNORECASE)
MAX_DICE = 100


class DiceError(ValueError):
    pass


@dataclass
class Roll:
    expression: str
    total: int
    detail: str  # "[4, 2] + 3"
    dice: list[tuple[int, int]] = field(default_factory=list)  # (sides, value) of every die kept

    @property
    def natural(self) -> str:
        """"crit" or "fumble" for a single d20 that came up 20 or 1."""
        d20s = [v for sides, v in self.dice if sides == 20]
        if len(d20s) == 1 and len(self.dice) == 1:
            return {20: "crit", 1: "fumble"}.get(d20s[0], "")
        return ""


def struck(value: int) -> str:
    """A dropped die, struck through: 7̶."""
    return "".join(c + "\u0336" for c in str(value))


def roll(expression: str, rng: random.Random | None = None) -> Roll:
    rng = rng or random
    text = expression.strip()
    if not text or not re.fullmatch(rf"\s*[+\-−]?\s*{_TERM}(?:\s*[+\-−]\s*{_TERM})*\s*", text, re.IGNORECASE):
        raise DiceError(f"Not a dice roll: {expression!r} (try 2d6+3)")
    total, parts, kept_dice = 0, [], []
    for m in TERM_RE.finditer(text):
        sign = -1 if m.group(1) in ("-", "−") else 1
        op = ("− " if sign < 0 else "+ ") if parts else ("−" if sign < 0 else "")
        if m.group(6) is not None:
            value = int(m.group(6))
            total += sign * value
            parts.append(f"{op}{value}")
            continue
        count = int(m.group(2) or 1)
        sides = 100 if m.group(3) == "%" else int(m.group(3))
        if not 1 <= count <= MAX_DICE or sides < 1:
            raise DiceError(f"Can't roll {m.group(0).strip()}")
        values = [rng.randint(1, sides) for _ in range(count)]
        kept = values
        if m.group(4):
            n = min(int(m.group(5)), count)
            ranked = sorted(range(count), key=lambda i: values[i], reverse=m.group(4).lower() == "h")
            keep = set(ranked[:n])
            kept = [v for i, v in enumerate(values) if i in keep]
            shown = ", ".join(str(v) if i in keep else struck(v) for i, v in enumerate(values))
        else:
            shown = ", ".join(map(str, values))
        total += sign * sum(kept)
        kept_dice += [(sides, v) for v in kept]
        parts.append(f"{op}[{shown}]")
    return Roll(re.sub(r"\s+", "", text), total, " ".join(parts), kept_dice)


def find(text: str):
    """Dice expressions in a line of text (regex matches)."""
    return DICE_RE.finditer(text)


# --- random tables ------------------------------------------------------------------------


@dataclass
class Table:
    die: str  # "d6"
    title: str  # the nearest heading above, or the second header cell
    rows: list[tuple[int, int, str]]  # (low, high, result)
    line: int  # the header row's line number

    def result(self, n: int) -> str | None:
        return next((text for low, high, text in self.rows if low <= n <= high), None)


_ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")
_RANGE_RE = re.compile(r"^\s*(\d+)\s*(?:[-–—]\s*(\d+)|\+)?\s*$")
_DIE_HEADER_RE = re.compile(r"^\s*(\d{0,3}d(?:\d{1,4}|%)(?:\s*[+\-]\s*\d+)?)\s*$", re.IGNORECASE)


def _cells(line: str) -> list[str] | None:
    m = _ROW_RE.match(line)
    return [c.strip() for c in m.group(1).split("|")] if m else None


def tables(text: str) -> list[Table]:
    lines = text.split("\n")
    found, heading = [], ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if h := re.match(r"^#{1,6}\s+(.*)", line):
            heading = h.group(1).strip()
        cells = _cells(line)
        if cells and (die := _DIE_HEADER_RE.match(cells[0])) and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            title = heading or (cells[1] if len(cells) > 1 else die.group(1))
            table = Table(die.group(1).replace(" ", "").lower(), title, [], i)
            j = i + 2
            while j < len(lines) and (row := _cells(lines[j])) is not None:
                if (r := _RANGE_RE.match(row[0])) and len(row) > 1 and any(row[1:]):
                    low = int(r.group(1))
                    high = int(r.group(2)) if r.group(2) else (10**6 if "+" in row[0] else low)
                    table.rows.append((low, high, " · ".join(c for c in row[1:] if c)))
                j += 1
            if table.rows:
                found.append(table)
            i = j
            continue
        i += 1
    return found


def table_at(text: str, line: int) -> Table | None:
    """The random table whose header or rows are at `line`."""
    for table in tables(text):
        if table.line <= line <= table.line + 1 + len(table.rows):
            return table
    return None


def roll_table(table: Table, rng: random.Random | None = None) -> tuple[Roll, str]:
    """Roll a table's die: (the roll, the row it lands on)."""
    r = roll(table.die, rng)
    return r, table.result(r.total) or "(no row for that number)"
