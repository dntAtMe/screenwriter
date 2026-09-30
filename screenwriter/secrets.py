"""GM-only passages: written alongside everything else, left out of player handouts.

    ## The duke's plan (GM)          a heading marked (GM), (GM only) or (secret):
    …                                the whole section, down to the next heading
                                     of the same or a higher level
    GM: the innkeeper is a spy.      a paragraph starting "GM:" or "Secret:"
    [[note to self]]                 notes, as everywhere, are never printed

The editor shades secret text; export offers a player handout without it.
"""

from __future__ import annotations

import re

from .marks import strip_marks

SECRET_HEADING_RE = re.compile(r"^(#{1,6})\s.*\((?:gm|gm only|gm-only|secret)\)\s*$", re.IGNORECASE)
SECRET_PARAGRAPH_RE = re.compile(r"^\s*(?:[>*-]\s*)?(?:gm|secret)\s*:", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s")
NOTE_RE = re.compile(r"\[\[.*?\]\]", re.DOTALL)
MARKER_RE = re.compile(r"^\s*(?:[>*-]\s*)?((?:gm|secret)\s*:)|(\((?:gm|gm only|gm-only|secret)\))\s*$", re.IGNORECASE)

NONE, PARAGRAPH = 0, 7  # block states; 1–6: inside a secret section of that heading level


def step(state: int, line: str) -> tuple[int, bool]:
    """(state after `line`, whether `line` is secret), given the state after the line before."""
    section = state if 1 <= state <= 6 else 0
    if heading := HEADING_RE.match(line):
        level = len(heading.group(1))
        if section and level > section:
            return section, True
        if SECRET_HEADING_RE.match(line):
            return level, True
        return NONE, False
    if section:
        return section, True
    if not line.strip():
        return NONE, False
    if state == PARAGRAPH or SECRET_PARAGRAPH_RE.match(line):
        return PARAGRAPH, True
    return NONE, False


def marker(line: str) -> tuple[int, int] | None:
    """Where the "GM:" or "(GM)" that makes a line secret is, as (start, end)."""
    for m in MARKER_RE.finditer(line):
        group = 1 if m.group(1) else 2
        if group == 1 or HEADING_RE.match(line):
            return m.start(group), m.end(group)
    return None


def secret_lines(text: str) -> list[bool]:
    state, out = NONE, []
    for line in text.split("\n"):
        state, secret = step(state, line)
        out.append(secret)
    return out


def has_secrets(text: str) -> bool:
    return any(secret_lines(text)) or bool(NOTE_RE.search(text))


def count_secrets(text: str) -> int:
    """Secret passages (runs of secret lines) in a text, for "3 GM-only passages left out"."""
    runs, before = 0, False
    for secret in secret_lines(text):
        runs += secret and not before
        before = secret
    return runs


def player_copy(text: str) -> str:
    """The text without its secrets and notes, as players may read it."""
    text = NOTE_RE.sub("", text)
    kept = [line for line, secret in zip(text.split("\n"), secret_lines(text)) if not secret]
    text = strip_marks("\n".join(line.rstrip() for line in kept))
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
