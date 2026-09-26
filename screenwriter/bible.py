"""Story bible: character and location sheets, and where they appear.

An entry is Markdown with a small front-matter header, readable without the app:

    ---
    name: Mara Quinn
    aliases: MARA, the keeper
    role: Protagonist
    ---
    Free-form notes…

Unknown header keys are kept, so fields can be added by hand.

Aliases may end in * to match any ending, for inflected languages:
"Kacpr*" finds Kacpra, Kacprowi, Kacprem…
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
        ("aliases", "Also called"),
        ("role", "Role"),
        ("age", "Age"),
        ("description", "Description"),
    ],
    LOCATION: [
        ("name", "Name"),
        ("aliases", "Also called"),
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
    if "script names" in fields and "aliases" not in fields:  # older entries
        fields["aliases"] = fields.pop("script names")
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


def aliases(fields: dict[str, str]) -> list[str]:
    return [n.strip() for n in fields.get("aliases", fields.get("script names", "")).split(",") if n.strip()]


def script_names(fields: dict[str, str], kind: str = CHARACTER) -> list[str]:
    """The names to look for in scripts, upper-case.

    Characters: the aliases, else the name and its first word.
    Locations: the aliases, else the name.
    """
    given = [n.upper() for n in aliases(fields)]
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
    """Whole-word, case-insensitive match of any name; "stem*" matches any ending."""
    names = [n for n in names if n.rstrip("*")]
    if not names:
        return None

    def pattern(n: str) -> str:
        return re.escape(n[:-1]) + r"\w*" if n.endswith("*") else re.escape(n)

    alternatives = "|".join(pattern(n) for n in sorted(names, key=len, reverse=True))
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
    """Scenes whose heading contains one of the names, and mentions in prose."""
    report = Report()
    finder = _name_re(names)
    if not finder:
        return report
    for doc_id, title, kind, text in docs:
        if kind != "screenplay":
            _scan_prose(report, finder, doc_id, title, text)
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
            given = [n.upper() for n in aliases(fields)]
            names = given or ([fields["name"].strip().upper()] if fields.get("name", "").strip() else [])
            characters += names[:1] + [n for n in given[1:]]
        elif kind == LOCATION:
            locations += script_names(fields, LOCATION)
    return characters, locations


# --- names across the whole bible (prose highlighting, completion, cast lists) ----------------


@dataclass
class IndexEntry:
    node_id: str
    kind: str
    name: str
    summary: str
    names: list[str]  # everything that refers to this entry, as written


class BibleIndex:
    """All bible entries and the names they go by, for finding them in any text."""

    def __init__(self, entries: list[tuple[str, str, str]] = ()):  # (node id, kind, entry text)
        self.entries: list[IndexEntry] = []
        by_name: dict[str, IndexEntry] = {}
        for node_id, kind, text in entries:
            fields, notes = parse_entry(text)
            name = fields.get("name", "").strip()
            if not name:
                continue
            names = [name] + aliases(fields)
            if kind == CHARACTER and not aliases(fields) and " " in name:
                names.append(name.split()[0])  # "Mara Quinn" is also "Mara"
            entry = IndexEntry(node_id, kind, name, entry_summary(text), list(dict.fromkeys(names)))
            self.entries.append(entry)
            for n in entry.names:
                by_name.setdefault(n.lower(), entry)
        self._by_name = by_name
        # "kacpr*" stems, longest first so the most specific wins
        self._stems = sorted(((n[:-1], e) for n, e in by_name.items() if n.endswith("*")), key=lambda s: -len(s[0]))
        self.regex = _name_re(list(by_name)) if by_name else None

    def __bool__(self) -> bool:
        return bool(self.entries)

    def lookup(self, text: str) -> IndexEntry | None:
        text = text.lower()
        if entry := self._by_name.get(text):
            return entry
        return next((e for stem, e in self._stems if text.startswith(stem)), None)

    def find(self, text: str):
        """(match, entry) for every mention in text."""
        if self.regex is None:
            return
        for m in self.regex.finditer(text):
            if entry := self.lookup(m.group(0)):
                yield m, entry

    def completions(self) -> list[str]:
        """Names as they'd be written in prose: 'Mara Quinn', 'Mara', 'the keeper'."""
        out = []
        for entry in self.entries:
            for n in entry.names:
                if not n.endswith("*"):
                    out.append(n.title() if n.isupper() else n)
        return list(dict.fromkeys(out))

    def cast(self, text: str) -> list[tuple[IndexEntry, int]]:
        """Entries mentioned in text, most mentioned first."""
        counts: dict[str, int] = {}
        for _, entry in self.find(text):
            counts[entry.node_id] = counts.get(entry.node_id, 0) + 1
        by_id = {e.node_id: e for e in self.entries}
        return sorted(((by_id[i], n) for i, n in counts.items()), key=lambda x: (-x[1], x[0].name))
