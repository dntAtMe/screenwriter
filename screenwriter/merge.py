"""Three-way merging of documents changed by two people, and the conflicts left over.

Text (prose, notes, scripts, story bible entries) merges line by line — in prose a
line is a paragraph — so edits to different paragraphs combine. Boards merge card by
card and field by field. Only the same paragraph (or the same card's text) changed
differently on both sides is a conflict: the version already here stays, and the
other one is recorded in `conflicts.json` (synced with the project) until someone
chooses what to keep.

Qt-free, like sync.py.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

CONFLICTS_FILE = "conflicts.json"


@dataclass
class Clash:
    kept: str  # the version left in the document
    other: str  # the version that lost
    base: str  # what it was before either change
    before: str = ""  # the line just before the clash, to find the spot if `kept` is empty
    card: str | None = None  # board card id, for a board


@dataclass
class ConflictRecord:
    """A clash waiting for someone to choose, as stored in conflicts.json."""
    id: str
    path: str  # "docs/<id>.md"
    kept: str
    other: str
    base: str = ""
    before: str = ""
    card: str | None = None
    kept_by: str = ""
    other_by: str = ""
    time: str = ""

    @classmethod
    def from_clash(cls, path: str, clash: Clash, kept_by: str, other_by: str) -> ConflictRecord:
        return cls(uuid.uuid4().hex[:12], path, clash.kept, clash.other, clash.base, clash.before, clash.card,
                   kept_by, other_by, datetime.now(timezone.utc).isoformat(timespec="seconds"))


# --- text ------------------------------------------------------------------------------------


def _line_map(base: list[str], side: list[str]) -> dict[int, int]:
    """Base line -> the same, unchanged line on one side."""
    out = {}
    for a, b, n in SequenceMatcher(None, base, side, autojunk=False).get_matching_blocks():
        for k in range(n):
            out[a + k] = b + k
    return out


def _merge_seq(b: list[str], o: list[str], t: list[str]):
    """diff3 over two sequences: yields ("same", items) for stretches that merge, and
    ("clash", base, ours, theirs) where both sides changed the same stretch differently."""
    to_o, to_t = _line_map(b, o), _line_map(b, t)
    ib = io = it = 0
    while ib < len(b) or io < len(o) or it < len(t):
        if ib < len(b) and to_o.get(ib) == io and to_t.get(ib) == it:  # unchanged on both sides
            yield "same", [b[ib]]
            ib, io, it = ib + 1, io + 1, it + 1
            continue
        # the next item both sides still share ends this changed stretch
        j = next((j for j in range(ib, len(b)) if to_o.get(j, -1) >= io and to_t.get(j, -1) >= it), len(b))
        eo = to_o[j] if j < len(b) else len(o)
        et = to_t[j] if j < len(b) else len(t)
        chunk_b, chunk_o, chunk_t = b[ib:j], o[io:eo], t[it:et]
        if chunk_o == chunk_b or chunk_o == chunk_t:
            yield "same", chunk_t
        elif chunk_t == chunk_b:
            yield "same", chunk_o
        else:
            yield "clash", chunk_b, chunk_o, chunk_t
        ib, io, it = j, eo, et


TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]")


def _merge_words(base: str, ours: str, theirs: str) -> str | None:
    """The same paragraph changed on both sides: merge it word by word, so edits to
    different sentences (or words) combine. None if they touch the same words."""
    tokens = lambda s: TOKEN_RE.findall(s)
    out = []
    for part in _merge_seq(tokens(base), tokens(ours), tokens(theirs)):
        if part[0] == "clash":
            return None
        out += part[1]
    return "".join(out)


def merge_text(base: str, ours: str, theirs: str) -> tuple[str, list[Clash]]:
    """diff3-style merge by lines (a prose paragraph is a line), then by words inside a
    paragraph both sides changed. Changes in different places combine; where both changed
    the same words differently, ours is kept and a Clash is reported."""
    if ours == theirs or theirs == base:
        return ours, []
    if ours == base:
        return theirs, []
    out: list[str] = []
    clashes: list[Clash] = []
    for part in _merge_seq(base.split("\n"), ours.split("\n"), theirs.split("\n")):
        if part[0] == "same":
            out += part[1]
            continue
        chunk_b, chunk_o, chunk_t = ("\n".join(c) for c in part[1:])
        words = _merge_words(chunk_b, chunk_o, chunk_t)
        if words is not None:
            out += words.split("\n")
        else:
            clashes.append(Clash(chunk_o, chunk_t, chunk_b, out[-1] if out else ""))
            out += part[2]
    return "\n".join(out), clashes


# --- boards ------------------------------------------------------------------------------------

CARD_FIELDS = ("x", "y", "w", "text", "color", "doc")


def merge_board(base: str, ours: str, theirs: str) -> tuple[str, list[Clash]]:
    """Merge board JSON card by card: moves, recolouring and text edits on different
    cards (or different fields of one card) all survive."""
    if ours == theirs or theirs == base:
        return ours, []
    if ours == base:
        return theirs, []
    load = lambda s: json.loads(s) if s.strip() else {"cards": [], "links": []}
    b, o, t = load(base), load(ours), load(theirs)
    bc = {c["id"]: c for c in b.get("cards", [])}
    oc = {c["id"]: c for c in o.get("cards", [])}
    tc = {c["id"]: c for c in t.get("cards", [])}
    clashes: list[Clash] = []
    cards = []
    for cid in list(oc) + [i for i in tc if i not in oc]:
        bv, ov, tv = bc.get(cid), oc.get(cid), tc.get(cid)
        if ov is None:  # added by them, or deleted by us
            if bv is None or (tv != bv):  # new, or edited after we deleted it: keep
                cards.append(tv)
            continue
        if tv is None:  # deleted by them: gone unless we changed it
            if bv is None or ov != bv:
                cards.append(ov)
            continue
        card = dict(ov)
        for key in CARD_FIELDS:
            bk, ok, tk = (bv or {}).get(key), ov.get(key), tv.get(key)
            if ok == tk or tk == bk:
                continue
            if ok == bk:
                if tk is None:
                    card.pop(key, None)
                else:
                    card[key] = tk
            elif key == "text":
                clashes.append(Clash(ok or "", tk or "", bk or "", card=cid))
        cards.append(card)
    ids = {c["id"] for c in cards}
    key = lambda link: (link["a"], link["b"])
    bl = {key(l) for l in b.get("links", [])}
    ol = {key(l): l for l in o.get("links", [])}
    tl = {key(l): l for l in t.get("links", [])}
    links = [l for k, l in ({**tl, **ol}).items() if not (k in bl and (k not in ol or k not in tl))]
    links = [l for l in links if l["a"] in ids and l["b"] in ids]
    merged = {**o, "cards": cards, "links": links}
    return json.dumps(merged, indent=2, ensure_ascii=False) + "\n", clashes


# --- conflicts.json ------------------------------------------------------------------------------


def parse_conflicts(data: bytes | str | None) -> list[ConflictRecord]:
    if not data:
        return []
    try:
        raw = json.loads(data)
    except ValueError:
        return []
    known = set(ConflictRecord.__dataclass_fields__)
    return [ConflictRecord(**{k: v for k, v in c.items() if k in known}) for c in raw.get("conflicts", [])
            if isinstance(c, dict) and "id" in c]


def dump_conflicts(records: list[ConflictRecord]) -> bytes:
    return (json.dumps({"conflicts": [asdict(r) for r in records]}, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def merge_conflict_lists(base: bytes | None, ours: bytes | None, theirs: bytes | None) -> list[ConflictRecord]:
    """Conflicts either side added, minus those either side resolved."""
    b = {c.id for c in parse_conflicts(base)}
    o = {c.id: c for c in parse_conflicts(ours)}
    t = {c.id: c for c in parse_conflicts(theirs)}
    resolved = (b - set(o)) | (b - set(t))
    return [c for i, c in ({**t, **o}).items() if i not in resolved]


def load_conflicts(project_path: Path) -> list[ConflictRecord]:
    path = project_path / CONFLICTS_FILE
    return parse_conflicts(path.read_bytes()) if path.is_file() else []


def save_conflicts(project_path: Path, records: list[ConflictRecord]) -> None:
    path = project_path / CONFLICTS_FILE
    if records:
        path.write_bytes(dump_conflicts(records))
    elif path.exists():
        path.unlink()


# --- resolving ---------------------------------------------------------------------------------------

KEEP, THEIRS, BOTH = "keep", "theirs", "both"


def resolve_text(text: str, record: ConflictRecord, choice: str) -> str | None:
    """The document with the choice applied, or None if the spot can't be found any more
    (the paragraph was edited again since)."""
    if choice == KEEP:
        return text
    sep = "\n\n" if record.path.endswith(".md") else "\n"
    replacement = record.other if choice == THEIRS else (
        record.kept + sep + record.other if record.kept and record.other else record.kept or record.other)
    if record.kept:
        if text.count(record.kept) != 1:
            return None
        return text.replace(record.kept, replacement, 1)
    # we had deleted it: put theirs back after the line that came before it
    anchor = record.before + "\n"
    if record.before and text.count(anchor) == 1:
        at = text.index(anchor) + len(anchor)
        return text[:at] + replacement + "\n" + text[at:]
    if not record.before:
        return replacement + "\n" + text
    return None


def resolve_board(text: str, record: ConflictRecord, choice: str) -> str | None:
    if choice == KEEP:
        return text
    data = json.loads(text) if text.strip() else {"cards": []}
    card = next((c for c in data.get("cards", []) if c.get("id") == record.card), None)
    if card is None:
        return None
    card["text"] = record.other if choice == THEIRS else f"{record.kept}\n{record.other}"
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def resolve(text: str, record: ConflictRecord, choice: str) -> str | None:
    return (resolve_board if record.card else resolve_text)(text, record, choice)
