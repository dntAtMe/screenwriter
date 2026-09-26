"""Story bible: character and location sheets, and where they appear.

An entry is Markdown with a small front-matter header, readable without the app:

    ---
    name: Mara Quinn
    script names: MARA
    role: Protagonist
    ---
    Free-form notes…

Unknown header keys are kept, so fields can be added by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .fountain import El, character_name, parse

CHARACTER, LOCATION = "character", "location"

# (key, label) in form order
FIELDS = {
    CHARACTER: [
        ("name", "Name"),
        ("script names", "Name in script"),
        ("role", "Role"),
        ("age", "Age"),
        ("description", "Description"),
    ],
    LOCATION: [
        ("name", "Name"),
        ("script names", "Name in headings"),
        ("description", "Description"),
    ],
}
FRONT_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def parse_entry(text: str) -> tuple[dict[str, str], str]:
    """(fields, notes). Keys are lower-case; values may span lines when indented."""
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    fields: dict[str, str] = {}
    key = None
    for line in m.group(1).splitlines():
        if line[:1] in (" ", "\t") and key:
            fields[key] = (fields[key] + "\n" + line.strip()).strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            fields[key] = value.strip()
    return fields, text[m.end():]


def format_entry(fields: dict[str, str], notes: str) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if not value.strip():
            continue
        first, *rest = value.strip().splitlines()
        lines.append(f"{key}: {first}")
        lines += [f"  {r}" for r in rest]
    lines.append("---")
    body = notes.lstrip("\n")
    return "\n".join(lines) + "\n" + (("\n" + body) if body else "")


def script_names(fields: dict[str, str], kind: str = CHARACTER) -> list[str]:
    """The names to look for in scripts, upper-case.

    Characters: 'script names' (comma-separated), else the name and its first word.
    Locations: 'script names', else the name.
    """
    given = [n.strip().upper() for n in fields.get("script names", "").split(",") if n.strip()]
    if given:
        return given
    name = fields.get("name", "").strip().upper()
    if not name:
        return []
    if kind == CHARACTER and " " in name:
        return [name, name.split()[0]]
    return [name]


def entry_summary(text: str) -> str:
    """A one-line description, for cards and tooltips."""
    fields, notes = parse_entry(text)
    return fields.get("description") or fields.get("role") or next((l for l in notes.splitlines() if l.strip()), "")


# --- appearances ----------------------------------------------------------------------


@dataclass
class Appearance:
    doc_id: str
    doc_title: str
    pos: int
    length: int
    line: int
    label: str
    speaks: bool = False


@dataclass
class Report:
    appearances: list[Appearance] = field(default_factory=list)
    speeches: int = 0
    words: int = 0
    scenes: set[tuple[str, int]] = field(default_factory=set)  # (doc id, heading line)

    def by_document(self) -> dict[tuple[str, str], list[Appearance]]:
        out: dict[tuple[str, str], list[Appearance]] = {}
        for a in self.appearances:
            out.setdefault((a.doc_id, a.doc_title), []).append(a)
        return out


def _name_re(names: list[str]) -> re.Pattern | None:
    names = [n for n in names if n]
    if not names:
        return None
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<!\w)({alternatives})(?!\w)", re.IGNORECASE)


# (doc id, title, kind, text) — kind is "screenplay" or "prose"
Document = tuple[str, str, str, str]


def character_report(names: list[str], docs: list[Document]) -> Report:
    report = Report()
    wanted = {n.upper() for n in names}
    finder = _name_re(names)
    if not wanted:
        return report
    for doc_id, title, kind, text in docs:
        if kind == "screenplay":
            _scan_script(report, wanted, finder, doc_id, title, text)
        elif finder:
            _scan_prose(report, finder, doc_id, title, text)
    return report


def _line_offsets(text: str) -> list[int]:
    offsets, pos = [], 0
    for line in text.split("\n"):
        offsets.append(pos)
        pos += len(line) + 1
    return offsets


def _scan_script(report, wanted, finder, doc_id, title, text) -> None:
    lines = parse(text)
    offsets = _line_offsets(text)
    heading, heading_line = "(before the first scene)", -1
    speaking = False
    for i, (line, el) in enumerate(lines):
        if el == El.SCENE:
            heading, heading_line = line.strip().lstrip(".").upper(), i
        if el == El.CHARACTER:
            speaking = character_name(line).upper() in wanted
            if speaking:
                report.speeches += 1
                report.scenes.add((doc_id, heading_line))
                report.appearances.append(Appearance(doc_id, title, offsets[i], len(line), i, heading, speaks=True))
            continue
        if el == El.DIALOGUE and speaking:
            report.words += len(line.split())
            continue
        if el not in (El.PARENTHETICAL, El.DIALOGUE):
            speaking = False
        if el in (El.ACTION, El.SCENE) and finder and (m := finder.search(line)):
            report.scenes.add((doc_id, heading_line))
            report.appearances.append(
                Appearance(doc_id, title, offsets[i] + m.start(), m.end() - m.start(), i, _snippet(line, m))
            )


def _scan_prose(report, finder, doc_id, title, text) -> None:
    offsets = _line_offsets(text)
    for i, line in enumerate(text.split("\n")):
        for m in finder.finditer(line):
            report.appearances.append(
                Appearance(doc_id, title, offsets[i] + m.start(), m.end() - m.start(), i, _snippet(line, m))
            )


def _snippet(line: str, m: re.Match, width: int = 40) -> str:
    start, end = max(0, m.start() - width), min(len(line), m.end() + width)
    return ("…" if start else "") + line[start:end].strip() + ("…" if end < len(line) else "")


def location_report(names: list[str], docs: list[Document]) -> Report:
    """Scenes whose heading contains one of the names."""
    report = Report()
    finder = _name_re(names)
    if not finder:
        return report
    for doc_id, title, kind, text in docs:
        if kind != "screenplay":
            continue
        offsets = _line_offsets(text)
        for i, (line, el) in enumerate(parse(text)):
            if el == El.SCENE and (m := finder.search(line)):
                report.scenes.add((doc_id, i))
                report.appearances.append(
                    Appearance(doc_id, title, offsets[i] + m.start(), m.end() - m.start(), i, line.strip().lstrip(".").upper())
                )
    return report


def known_names(entries: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """(character cue names, location names) from (kind, text) bible entries,
    for the screenplay editor's completion."""
    characters, locations = [], []
    for kind, text in entries:
        fields, _ = parse_entry(text)
        if kind == CHARACTER:
            given = [n.strip().upper() for n in fields.get("script names", "").split(",") if n.strip()]
            names = given or ([fields["name"].strip().upper()] if fields.get("name", "").strip() else [])
            characters += names[:1] + [n for n in given[1:]]
        elif kind == LOCATION:
            locations += script_names(fields, LOCATION)
    return characters, locations
