"""Fountain screenplay parsing: line classification and structure.

Pure Python (no Qt) so the editor, outline, search and exporters share it.
See https://fountain.io/syntax
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable


class El(IntEnum):
    BLANK = 0
    ACTION = 1
    SCENE = 2
    CHARACTER = 3
    PARENTHETICAL = 4
    DIALOGUE = 5
    DIALOGUE_PENDING = 6  # empty line right after a cue: laid out as dialogue, behaves as blank
    TRANSITION = 7
    CENTERED = 8
    SECTION = 9
    SYNOPSIS = 10
    NOTE = 11


EL_NAMES = {
    El.BLANK: "",
    El.ACTION: "Action",
    El.SCENE: "Scene Heading",
    El.CHARACTER: "Character",
    El.PARENTHETICAL: "Parenthetical",
    El.DIALOGUE: "Dialogue",
    El.DIALOGUE_PENDING: "Dialogue",
    El.TRANSITION: "Transition",
    El.CENTERED: "Centered",
    El.SECTION: "Section",
    El.SYNOPSIS: "Synopsis",
    El.NOTE: "Note",
}

IN_DIALOGUE = (El.CHARACTER, El.PARENTHETICAL, El.DIALOGUE)
AFTER_BREAK = (-1, El.BLANK, El.DIALOGUE_PENDING)

SCENE_RE = re.compile(r"^(INT|EXT|EST|INT\.?/EXT|I/E)[.\s]", re.IGNORECASE)
EXTENSION_RE = re.compile(r"\s*\([^()]*\)\s*\^?$")  # MARA (V.O.)  /  MARA (cont'd) ^

# Typed at the start of a line and followed by "." or space, these become a scene heading prefix.
SCENE_PREFIXES = {"int": "INT.", "ext": "EXT.", "est": "EST.", "i/e": "INT./EXT.", "int/ext": "INT./EXT."}
TIMES_OF_DAY = [
    "DAY", "NIGHT", "CONTINUOUS", "LATER", "MOMENTS LATER", "MORNING",
    "AFTERNOON", "EVENING", "DAWN", "DUSK", "SAME TIME",
]
CUE_EXTENSIONS = ["V.O.", "O.S.", "O.C.", "CONT'D"]

TYPED_TRANSITION_RE = re.compile(
    r"^((smash |match |jump )?cut|dissolve|fade|wipe) to:?$|^fade (in|out):?\.?$|^fade to black\.?$",
    re.IGNORECASE,
)
NAME_END_PUNCTUATION = tuple(".!?,;:-–—\"'")


def normalize_transition(s: str) -> str:
    """'cut to' -> 'CUT TO:', 'fade out' -> 'FADE OUT.', 'fade in' -> 'FADE IN:'."""
    u = s.strip().upper().rstrip(":. ")
    if u == "FADE IN":
        return "FADE IN:"
    if u in ("FADE OUT", "FADE TO BLACK"):
        return u + "."
    return u + ":"


def is_caps(s: str) -> bool:
    name = EXTENSION_RE.sub("", s).rstrip("^ ")
    return any(c.isalpha() for c in name) and name == name.upper() and "(" not in name


def character_name(cue: str) -> str:
    """'@McCLANE (V.O.) ^' -> 'McCLANE'."""
    return EXTENSION_RE.sub("", cue.strip().lstrip("@")).rstrip("^ ").strip()


def classify(
    text: str,
    prev: int,
    next_text: str | None = None,
    editing: bool = False,
    forced_cue: bool = False,
) -> El:
    """Classify one line given the previous line's element and the next line's text.

    editing:    the line holds the cursor. An all-caps line being typed is taken as a
                character cue before its dialogue exists (unless it ends in punctuation,
                like "BOOM!").
    forced_cue: the writer pressed Tab to start a cue on this line.
    """
    s = text.strip()
    if prev in IN_DIALOGUE:
        if not s:
            return El.DIALOGUE_PENDING if prev in (El.CHARACTER, El.PARENTHETICAL) else El.BLANK
        return El.PARENTHETICAL if s.startswith("(") else El.DIALOGUE
    after_break = prev in AFTER_BREAK
    if forced_cue and after_break:
        return El.CHARACTER
    if not s:
        return El.BLANK
    if s.startswith("#"):
        return El.SECTION
    if s.startswith("=") and not s.startswith("==="):
        return El.SYNOPSIS
    if s.startswith("[[") and s.endswith("]]"):
        return El.NOTE
    if s.startswith(">"):
        return El.CENTERED if s.endswith("<") else El.TRANSITION
    if not after_break:
        return El.ACTION
    if s.startswith("!"):
        return El.ACTION
    if (s.startswith(".") and not s.startswith("..")) or SCENE_RE.match(s):
        return El.SCENE
    if s.startswith("@"):
        return El.CHARACTER
    if is_caps(s):
        if s.endswith("TO:") or s in ("FADE OUT.", "FADE TO BLACK."):
            return El.TRANSITION
        if s.endswith(":"):
            return El.ACTION  # FADE IN:
        has_dialogue = bool(next_text and next_text.strip())
        typing_cue = editing and sum(c.isalpha() for c in s) >= 2 and not s.endswith(NAME_END_PUNCTUATION)
        if has_dialogue or typing_cue:
            return El.CHARACTER
    return El.ACTION


def parse(text: str) -> list[tuple[str, El]]:
    lines = text.split("\n")
    out, prev = [], -1
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        prev = classify(line, prev, nxt)
        out.append((line, prev))
    return out


# --- structure ----------------------------------------------------------------


@dataclass
class OutlineItem:
    level: int
    title: str
    line: int
    kind: str  # "section" | "scene"
    number: int = 0  # scene number


def outline(lines: Iterable[tuple[str, El]]) -> list[OutlineItem]:
    items, depth, scene_no = [], 0, 0
    for i, (text, el) in enumerate(lines):
        s = text.strip()
        if el == El.SECTION:
            depth = len(s) - len(s.lstrip("#"))
            items.append(OutlineItem(depth - 1, s.lstrip("#").strip() or "(section)", i, "section"))
        elif el == El.SCENE:
            scene_no += 1
            title = s[1:] if s.startswith(".") else s
            items.append(OutlineItem(depth, title.upper(), i, "scene", scene_no))
    return items


def characters(lines: Iterable[tuple[str, El]]) -> Counter:
    return Counter(character_name(t) for t, el in lines if el == El.CHARACTER and character_name(t))


def locations(lines: Iterable[tuple[str, El]]) -> Counter:
    """Scene heading locations without the time of day: 'INT. KITCHEN'."""
    found = Counter()
    for t, el in lines:
        if el == El.SCENE:
            heading = t.strip().lstrip(".").upper()
            found[heading.split(" - ")[0].strip()] += 1
    return found


def times_of_day(lines: Iterable[tuple[str, El]]) -> list[str]:
    used = Counter(
        t.upper().rsplit(" - ", 1)[1].strip() for t, el in lines if el == El.SCENE and " - " in t
    )
    return [t for t, _ in used.most_common()] + [t for t in TIMES_OF_DAY if t not in used]
