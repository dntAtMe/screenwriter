"""Comments in the margin: a note on a stretch of text, with replies, that can be resolved.

Nothing is added to the documents themselves. A comment remembers the words it is on
(`quote`), a little of the text either side, and roughly where they were; that's enough
to find them again after edits, merges and live typing, and while a document is open the
editor follows the words as they move. If the words are gone, the comment stays, marked
as no longer found.

Comments are kept in comments.json in the project (synced with it). Two people's
comments and replies are all kept when their copies merge; resolving or editing a comment
on one side wins over the other side leaving it alone. Qt-free.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

COMMENTS_FILE = "comments.json"
CONTEXT = 32  # characters of surrounding text remembered on each side


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Reply:
    id: str
    author: str
    text: str
    time: str = ""


@dataclass
class Comment:
    id: str
    doc: str  # binder node id
    quote: str  # the commented words
    author: str
    text: str
    time: str = ""
    prefix: str = ""  # text just before and after them, to tell identical quotes apart
    suffix: str = ""
    pos: int = 0  # where they were last seen
    resolved: bool = False
    resolved_by: str = ""
    replies: list[Reply] = field(default_factory=list)

    @classmethod
    def new(cls, doc: str, text: str, start: int, end: int, author: str, body: str) -> Comment:
        c = cls(uuid.uuid4().hex[:12], doc, text[start:end], author, body, now())
        c.anchor(text, start, end)
        return c

    def anchor(self, text: str, start: int, end: int) -> bool:
        """Remember where the comment is now; whether anything changed."""
        before = (self.quote, self.prefix, self.suffix, self.pos)
        self.quote = text[start:end]
        self.prefix = text[max(0, start - CONTEXT):start]
        self.suffix = text[end:end + CONTEXT]
        self.pos = start
        return before != (self.quote, self.prefix, self.suffix, self.pos)

    def find(self, text: str) -> tuple[int, int] | None:
        """Where its words are in `text` now, or None if they're gone."""
        if not self.quote:
            return None
        best, best_score = None, None
        at = text.find(self.quote)
        while at >= 0:
            end = at + len(self.quote)
            score = (_common_suffix(text[max(0, at - CONTEXT):at], self.prefix)
                     + _common_prefix(text[end:end + CONTEXT], self.suffix)) * 1000 - abs(at - self.pos)
            if best_score is None or score > best_score:
                best, best_score = (at, end), score
            at = text.find(self.quote, at + 1)
        return best

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Comment:
        known = set(cls.__dataclass_fields__)
        replies = [Reply(**{k: v for k, v in r.items() if k in Reply.__dataclass_fields__}) for r in d.get("replies", [])]
        return cls(**{k: v for k, v in d.items() if k in known and k != "replies"}, replies=replies)


def _common_prefix(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def _common_suffix(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


# --- the file --------------------------------------------------------------------------------------


def parse(data: bytes | str | None) -> list[Comment]:
    if not data:
        return []
    try:
        raw = json.loads(data)
    except ValueError:
        return []
    return [Comment.from_dict(c) for c in raw.get("comments", []) if isinstance(c, dict) and "id" in c]


def dump(comments: list[Comment]) -> bytes:
    return (json.dumps({"comments": [c.to_dict() for c in comments]}, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load(project_path: Path) -> list[Comment]:
    path = project_path / COMMENTS_FILE
    return parse(path.read_bytes()) if path.is_file() else []


def save(project_path: Path, comments: list[Comment]) -> None:
    path = project_path / COMMENTS_FILE
    if comments:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(dump(comments))
        tmp.replace(path)
    elif path.exists():
        path.unlink()


# --- merging two people's comments ----------------------------------------------------------------

FIELDS = ("quote", "prefix", "suffix", "pos", "text", "resolved", "resolved_by", "doc")


def _merge_ids(base: dict, ours: dict, theirs: dict) -> list[str]:
    """Ids either side has, minus those one side deleted (and the other didn't change), in order."""
    ids = list(ours) + [i for i in theirs if i not in ours]
    out = []
    for i in ids:
        b, o, t = base.get(i), ours.get(i), theirs.get(i)
        if b is not None and (o is None or t is None):  # deleted on one side
            survivor = o if o is not None else t
            if survivor == b:
                continue
        out.append(i)
    return out


def merge(base: bytes | None, ours: bytes | None, theirs: bytes | None) -> bytes:
    b = {c.id: c for c in parse(base)}
    o = {c.id: c for c in parse(ours)}
    t = {c.id: c for c in parse(theirs)}
    merged = []
    for i in _merge_ids({k: v.to_dict() for k, v in b.items()}, {k: v.to_dict() for k, v in o.items()},
                        {k: v.to_dict() for k, v in t.items()}):
        bc, oc, tc = b.get(i), o.get(i), t.get(i)
        if oc is None or tc is None:
            merged.append(oc or tc)
            continue
        c = Comment.from_dict(oc.to_dict())
        for key in FIELDS:  # a field changed on one side only takes that side's value
            bv, ov, tv = getattr(bc, key) if bc else None, getattr(oc, key), getattr(tc, key)
            if ov == bv and tv != bv:
                setattr(c, key, tv)
        br = {r.id: asdict(r) for r in (bc.replies if bc else [])}
        orr = {r.id: asdict(r) for r in oc.replies}
        tr = {r.id: asdict(r) for r in tc.replies}
        replies = {**tr, **orr}
        c.replies = sorted((Reply(**replies[r]) for r in _merge_ids(br, orr, tr)), key=lambda r: r.time)
        merged.append(c)
    return dump(sorted(merged, key=lambda c: c.time))
