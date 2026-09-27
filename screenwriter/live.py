"""Live editing over a shared folder: see what the others type, as they type.

A document being edited by more than one window at once is shared as a CRDT (pycrdt,
a port of Yjs): every insertion and deletion is an operation with its own identity, so
applying one twice, or in a different order, changes nothing — all copies end up the
same, without guessing how two texts line up.

On the shared folder, next to the project file, "<name>.screenwriter.live/" holds:

- "<session>.json": which document a window is live on (and in which session — "gen" —
  of it), who it is and where its cursor is; rewritten every second or so.
- "base-<gen>.json": the text a live session of a document started from. Everyone builds
  the same first version of the CRDT from it, with the same fixed client id, so it is one
  and the same starting text for all (not everyone's own copy of it). It also names the
  saved version that text grew from ("origin"), so someone joining can tell what they
  wrote that the session doesn't have yet.
- "<session>-<gen>.ystate": that window's whole CRDT state; the others merge it in.

Qt-free; liveedit.py connects it to the editors.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pycrdt import Doc, Text

FRESH = timedelta(seconds=15)  # a window that stopped writing (closed, asleep) drops out after this
BASE_CLIENT = 1  # the client id the shared starting text is written with, the same everywhere
KEEP_OLD = 3600  # seconds before a finished session's files are tidied away


@dataclass
class LiveState:
    session: str
    person: str
    doc_id: str
    gen: str = ""  # the live session of that document this window is in
    line: int = 0  # cursor line, and that line's text (to find it in another copy)
    line_text: str = ""
    time: str = ""

    @property
    def fresh(self) -> bool:
        try:
            return datetime.now(timezone.utc) - datetime.fromisoformat(self.time) < FRESH
        except ValueError:
            return False


def live_dir(package: Path) -> Path:
    return package.with_name(package.name + ".live")


def _write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def new_gen() -> str:
    """Sorts by time, so everyone can agree on the older of two sessions started at once."""
    return f"{time.time_ns():020d}-{uuid.uuid4().hex[:6]}"


# --- positions: the CRDT counts UTF-8 bytes, Qt counts UTF-16 units ---------------------------------


def byte_offset(text: str, index: int) -> int:
    return len(text[:index].encode("utf-8"))


def char_index(text: str, offset: int) -> int:
    return len(text.encode("utf-8")[:offset].decode("utf-8", "ignore"))


def qt_position(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le")) // 2


def text_index(text: str, position: int) -> int:
    """A Qt (UTF-16) position in `text` as a Python string index."""
    return len(text.encode("utf-16-le")[: position * 2].decode("utf-16-le", "ignore"))


# --- the shared folder ----------------------------------------------------------------------------


class Channel:
    def __init__(self, package: Path):
        self.package = package
        self.folder = live_dir(package)
        self._mtimes: dict[Path, float] = {}

    def publish(self, state: LiveState) -> None:
        state.time = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            self.folder.mkdir(exist_ok=True)
            _write(self.folder / f"{state.session}.json", json.dumps(asdict(state), ensure_ascii=False).encode("utf-8"))
        except OSError:
            pass

    def states(self, session: str) -> list[LiveState]:
        out = []
        try:
            files = list(self.folder.glob("*.json"))
        except OSError:
            return []
        for path in files:
            if path.stem == session or path.name.startswith("base-"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                state = LiveState(**{k: v for k, v in data.items() if k in LiveState.__dataclass_fields__})
            except (OSError, ValueError, TypeError):
                continue
            if state.fresh:
                out.append(state)
        return out

    def withdraw(self, session: str) -> None:
        try:
            (self.folder / f"{session}.json").unlink(missing_ok=True)
        except OSError:
            pass

    # starting texts

    def create_base(self, gen: str, doc_id: str, text: str, origin: str = "", origin_text: str = "") -> None:
        """The starting text of a new session, and the saved version (history commit) it grew from."""
        data = {"doc_id": doc_id, "text": text, "origin": origin, "origin_text": origin_text}
        try:
            self.folder.mkdir(exist_ok=True)
            fd = os.open(self.folder / f"base-{gen}.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "wb") as f:
                f.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        except OSError:
            pass

    def base(self, gen: str) -> dict | None:
        try:
            data = json.loads((self.folder / f"base-{gen}.json").read_text(encoding="utf-8"))
            return data if "text" in data else None
        except (OSError, ValueError):
            return None

    # CRDT states

    def write_state(self, session: str, gen: str, update: bytes) -> None:
        try:
            self.folder.mkdir(exist_ok=True)
            _write(self.folder / f"{session}-{gen}.ystate", update)
        except OSError:
            pass

    def changed_states(self, session: str, gen: str) -> list[bytes]:
        """The others' CRDT states for this session of the document that changed since last read."""
        out = []
        try:
            files = list(self.folder.glob(f"*-{gen}.ystate"))
        except OSError:
            return []
        for path in files:
            if path.name.startswith(f"{session}-"):
                continue
            try:
                mtime = path.stat().st_mtime_ns
                if self._mtimes.get(path) == mtime:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            self._mtimes[path] = mtime
            out.append(data)
        return out

    def forget(self, gen: str) -> None:
        """Read every state of this session again next time (after joining it anew)."""
        for path in [p for p in self._mtimes if p.name.endswith(f"-{gen}.ystate")]:
            del self._mtimes[path]

    def tidy(self) -> None:
        """Remove files of live sessions nobody has touched for a while."""
        cutoff = time.time() - KEEP_OLD
        try:
            for path in self.folder.iterdir():
                if path.suffix in (".ystate", ".tmp") or path.name.startswith("base-"):
                    if path.stat().st_mtime < cutoff:
                        path.unlink(missing_ok=True)
        except OSError:
            pass


# --- one document's CRDT ------------------------------------------------------------------------------------


def base_update(text: str) -> bytes:
    """The starting text as a CRDT update — byte for byte the same on every computer."""
    doc = Doc(client_id=BASE_CLIENT)
    doc["text"] = ytext = Text()
    ytext += text
    return doc.get_update()


def new_doc(base_text: str) -> tuple[Doc, Text]:
    doc = Doc()
    doc.apply_update(base_update(base_text))
    return doc, doc.get("text", type=Text)


def find_line(lines: list[str], line: int, text: str) -> int:
    """Where someone's cursor line is in our copy: the same text nearest to where it was,
    else the same line number."""
    if text.strip():
        matches = [i for i, l in enumerate(lines) if l == text]
        if matches:
            return min(matches, key=lambda i: abs(i - line))
    return max(0, min(line, len(lines) - 1))
