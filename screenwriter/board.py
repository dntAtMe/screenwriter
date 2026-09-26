"""Board documents: cards and links for mind maps and corkboards.

Stored as JSON (docs/<id>.board.json):

    {"cards": [{"id", "x", "y", "w", "text", "color", "doc"?}],
     "links": [{"a": card id, "b": card id}]}

Qt-free so search and tests can read boards without a canvas.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field

COLORS = {
    "yellow": "#f6e7a8",
    "blue": "#c3dcf3",
    "green": "#cfe8bf",
    "pink": "#f5cbd5",
    "purple": "#dacdf2",
    "grey": "#dddddd",
}
DEFAULT_WIDTH = 180.0


def new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Card:
    id: str
    x: float
    y: float
    text: str = ""
    color: str = "yellow"
    w: float = DEFAULT_WIDTH
    doc: str | None = None  # linked binder document id


@dataclass
class Link:
    a: str
    b: str


@dataclass
class Board:
    cards: list[Card] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)

    def to_json(self) -> str:
        data = {
            "cards": [{k: v for k, v in asdict(c).items() if v is not None} for c in self.cards],
            "links": [asdict(link) for link in self.links],
        }
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Board:
        if not text.strip():
            return cls()
        data = json.loads(text)
        cards = [
            Card(
                id=c["id"], x=c.get("x", 0), y=c.get("y", 0), text=c.get("text", ""),
                color=c.get("color", "yellow") if c.get("color") in COLORS else "yellow",
                w=c.get("w", DEFAULT_WIDTH), doc=c.get("doc"),
            )
            for c in data.get("cards", [])
        ]
        ids = {c.id for c in cards}
        links = [Link(l["a"], l["b"]) for l in data.get("links", []) if l["a"] in ids and l["b"] in ids]
        return cls(cards, links)

    def search_text(self) -> str:
        """One line per card, in tree order, for project search."""
        return "\n".join(c.text.replace("\n", " ") for _, c in self.tree_order())

    def tree_order(self) -> list[tuple[int, Card]]:
        """(depth, card) walking the mind map from its roots (cards nothing links to),
        right-hand children before left-hand ones, top to bottom. Unconnected cards are roots too; cycles are cut."""
        by_id = {c.id: c for c in self.cards}
        children: dict[str, list[Card]] = {c.id: [] for c in self.cards}
        has_parent = set()
        for link in self.links:
            children[link.a].append(by_id[link.b])
            has_parent.add(link.b)
        position = lambda c: (c.y, c.x)
        roots = sorted((c for c in self.cards if c.id not in has_parent), key=position)
        out, seen = [], set()

        def visit(card: Card, depth: int) -> None:
            if card.id in seen:
                return
            seen.add(card.id)
            out.append((depth, card))
            # right-hand branches first, then left-hand ones, each top to bottom
            for child in sorted(children[card.id], key=lambda c: (c.x < card.x, c.y, c.x)):
                visit(child, depth + 1)

        for root in roots:
            visit(root, 0)
        for card in sorted(self.cards, key=position):  # pure cycles have no root
            visit(card, 0)
        return out


def search_text(json_text: str) -> str:
    try:
        return Board.from_json(json_text).search_text()
    except (ValueError, KeyError):
        return ""
