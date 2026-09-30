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

from .marks import MARK_RE, Mention, masked, stands_for, strip_marks
from .fountain import El, character_name, parse

from .project import BIBLE_KINDS, CHARACTER, FACTION, ITEM, LOCATION

LABELS = {CHARACTER: "Character", LOCATION: "Location", FACTION: "Faction", ITEM: "Item"}
PLURALS = {CHARACTER: "Characters", LOCATION: "Locations", FACTION: "Factions", ITEM: "Items"}
COLORS = {CHARACTER: "#c07a2c", LOCATION: "#2f8a86", FACTION: "#b0466c", ITEM: "#a0801c"}  # icons and name tints
ALIAS_HINTS = {
    CHARACTER: "Other names, comma-separated: MARA, the keeper",
    LOCATION: "Other names, comma-separated: LAMP ROOM, the tower",
    FACTION: "Other names, comma-separated: the Guild, Zhents",
    ITEM: "Other names, comma-separated: the blade, Dawnbringer",
}

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
    FACTION: [
        ("name", "Name"),
        ("aliases", "Also called"),
        ("type", "Kind"),
        ("leader", "Leader"),
        ("goal", "Wants"),
        ("description", "Description"),
    ],
    ITEM: [
        ("name", "Name"),
        ("aliases", "Also called"),
        ("type", "Type"),
        ("rarity", "Rarity"),
        ("owner", "Held by"),
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


def all_names(fields: dict[str, str], kind: str = CHARACTER) -> list[str]:
    """Every name an entry goes by, as written: the name, a character's first
    name ("Mara Quinn" → "Mara"), then the "also called" forms."""
    name = fields.get("name", "").strip()
    names = [name] if name else []
    if kind == CHARACTER and " " in name:
        names.append(name.split()[0])
    names += aliases(fields)
    return list(dict.fromkeys(names))


def script_names(fields: dict[str, str], kind: str = CHARACTER) -> list[str]:
    """all_names, upper-case, as they appear in a script."""
    return list(dict.fromkeys(n.upper() for n in all_names(fields, kind)))


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


def _is_wanted(name: str, wanted: set[str]) -> bool:
    """Whether a name (from a mark or an "is" note) is one of the entry's names, "stem*" forms too."""
    name = name.strip().upper()
    return name in wanted or any(w.endswith("*") and name.startswith(w[:-1]) for w in wanted)


def character_report(names: list[str], docs: list[Document]) -> Report:
    report = Report()
    wanted = {n.upper() for n in names}
    finder = _name_re(names)
    if not wanted:
        return report
    for doc_id, title, kind, text in docs:
        if kind == "screenplay":
            _scan_script(report, wanted, finder, doc_id, title, text)
        else:
            _scan_prose(report, finder, doc_id, title, text, wanted)
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
    # cues that stand for this character in this script: [[HOODED FIGURE is Xardas]]
    cues = {cue.upper() for cue, name in stands_for(text).items() if _is_wanted(name, wanted)}
    for i, (line, el) in enumerate(lines):
        if el == El.SCENE:
            heading, heading_line = line.strip().lstrip(".").upper(), i
        if el == El.CHARACTER:
            cue = character_name(line).upper()
            speaking = cue in wanted or cue in cues
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
        if el in (El.ACTION, El.SCENE):
            m = next(_marked(line, wanted), None) or (finder.search(masked(line)) if finder else None)
            if m:
                report.scenes.add((doc_id, heading_line))
                report.appearances.append(
                    Appearance(doc_id, title, offsets[i] + m.start(), m.end() - m.start(), i, _snippet(line, m))
                )


def _marked(line: str, wanted: set[str]):
    """Mentions marked as this entry in a line: {the hooded figure|Xardas}."""
    for m in MARK_RE.finditer(line):
        if _is_wanted(m.group(2), wanted):
            yield Mention(m.start(1), m.end(1), m.group(1))


def _scan_prose(report, finder, doc_id, title, text, wanted: set[str] = frozenset()) -> None:
    offsets = _line_offsets(text)
    for i, line in enumerate(text.split("\n")):
        found = list(_marked(line, wanted)) + (list(finder.finditer(masked(line))) if finder else [])
        for m in sorted(found, key=lambda m: m.start()):
            report.appearances.append(
                Appearance(doc_id, title, offsets[i] + m.start(), m.end() - m.start(), i, _snippet(line, m))
            )


def _snippet(line: str, m, width: int = 40) -> str:
    start, end = max(0, m.start() - width), min(len(line), m.end() + width)
    return ("…" if start else "") + strip_marks(line[start:end]).strip() + ("…" if end < len(line) else "")


def location_report(names: list[str], docs: list[Document]) -> Report:
    """Scenes whose heading contains one of the names, and mentions in prose."""
    report = Report()
    finder = _name_re(names)
    if not finder:
        return report
    wanted = {n.upper() for n in names}
    for doc_id, title, kind, text in docs:
        if kind != "screenplay":
            _scan_prose(report, finder, doc_id, title, text, wanted)
            continue
        offsets = _line_offsets(text)
        for i, (line, el) in enumerate(parse(text)):
            if el == El.SCENE and (m := finder.search(line)):
                report.scenes.add((doc_id, i))
                report.appearances.append(
                    Appearance(doc_id, title, offsets[i] + m.start(), m.end() - m.start(), i, line.strip().lstrip(".").upper())
                )
    return report


def report(kind: str, names: list[str], docs: list[Document]) -> Report:
    """Where an entry of any kind turns up: scenes set at a location, a character's
    speeches and mentions, mentions of anything else."""
    return location_report(names, docs) if kind == LOCATION else character_report(names, docs)


def known_names(entries: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """(character cue names, location names) from (kind, text) bible entries,
    for the screenplay editor's completion: the forms first, then the name."""
    characters, locations = [], []
    for kind, text in entries:
        fields, _ = parse_entry(text)
        name = fields.get("name", "").strip().upper()
        names = [n.upper() for n in aliases(fields) if not n.endswith("*")] + ([name] if name else [])
        (characters if kind == CHARACTER else locations if kind == LOCATION else []).extend(
            n for n in dict.fromkeys(names) if n not in characters + locations
        )
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
            entry = IndexEntry(node_id, kind, name, entry_summary(text), all_names(fields, kind))
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
        """(match, entry) for every mention in text: names, marked descriptions
        ({the hooded figure|Xardas}), and what a document's [[X is Name]] notes stand for."""
        if not self.entries:
            return
        for m in MARK_RE.finditer(text):
            if entry := self.lookup(m.group(2).strip()):
                yield Mention(m.start(1), m.end(1), m.group(1)), entry
        plain = masked(text)
        if self.regex is not None:
            for m in self.regex.finditer(plain):
                if entry := self.lookup(m.group(0)):
                    yield m, entry
        for what, name in stands_for(text).items():
            if entry := self.lookup(name):
                for m in re.finditer(rf"(?<!\w){re.escape(what)}(?!\w)", plain):
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
