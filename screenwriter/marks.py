"""Marked mentions: a description that stands for a Story Bible entry.

    {the hooded figure|Xardas}     this mention is Xardas — shown faintly, printed as "the hooded figure"
    [[HOODED FIGURE is Xardas]]    in this document, HOODED FIGURE is Xardas (a note: never printed),
                                   for a script's cue before the character is introduced

So a character can be written about as "the hooded figure" before the story names them,
and still be found wherever they appear. Qt-free.
"""

from __future__ import annotations

import re

MARK_RE = re.compile(r"\{([^{}|\n]+)\|([^{}|\n]+)\}")
STANDS_FOR_RE = re.compile(r"\[\[\s*([^\[\]\n]+?)\s+is\s+([^\[\]\n]+?)\s*\]\]")


def mark(phrase: str, name: str) -> str:
    return "{" + phrase + "|" + name + "}"


def strip_marks(text: str) -> str:
    """The text as printed: marks become just their phrase."""
    return MARK_RE.sub(r"\1", text)


def stands_for(text: str) -> dict[str, str]:
    """{"HOODED FIGURE": "Xardas"} from [[HOODED FIGURE is Xardas]] notes in a document."""
    return {m.group(1).strip(): m.group(2).strip() for m in STANDS_FOR_RE.finditer(text)}


def stands_for_note(what: str, name: str) -> str:
    return f"[[{what} is {name}]]"


def masked(text: str) -> str:
    """The text with marks and [[… is …]] notes blanked out (same length, so positions
    still line up), for finding the plain mentions around them."""
    blank = lambda m: " " * (m.end() - m.start())
    return STANDS_FOR_RE.sub(blank, MARK_RE.sub(blank, text))


class Mention:
    """A found mention, used like a re.Match: start(), end(), group()."""

    def __init__(self, start: int, end: int, text: str):
        self._start, self._end, self._text = start, end, text

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end

    def group(self, _=0) -> str:
        return self._text
