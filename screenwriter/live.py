"""Live editing over a shared folder: see what the others type, as they type.

Every window with the project open writes one small file next to the project file —
"<name>.screenwriter.live/<session>.json" — holding the document it shows, its text as
it is right now, the text it last synced (its base), and where its cursor is. The
others read those files every second and merge each one into their own open copy of
that document: merge_text(their base, my text, their text) brings in exactly what they
changed since they last synced, and never takes away what I've written since.

Qt-free; the window (liveedit.py) does the timing and the editors.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

FRESH = timedelta(seconds=15)  # a window that stopped writing (closed, asleep) drops out after this


@dataclass
class LiveState:
    session: str
    person: str
    doc_id: str
    text: str
    base: str  # the document as of their last sync: what their changes are measured against
    line: int = 0  # their cursor: line number, and that line's text (to find it in ours)
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


def publish(package: Path, state: LiveState) -> None:
    state.time = datetime.now(timezone.utc).isoformat(timespec="seconds")
    folder = live_dir(package)
    try:
        folder.mkdir(exist_ok=True)
        tmp = folder / f"{state.session}.json.tmp"
        tmp.write_text(json.dumps(asdict(state), ensure_ascii=False), encoding="utf-8")
        tmp.replace(folder / f"{state.session}.json")
    except OSError:
        pass


def withdraw(package: Path, session: str) -> None:
    try:
        (live_dir(package) / f"{session}.json").unlink(missing_ok=True)
    except OSError:
        pass


class LiveReader:
    """Reads the other windows' states, re-reading a file only when it has changed."""

    def __init__(self, package: Path):
        self.package = package
        self._cache: dict[Path, tuple[float, LiveState | None]] = {}

    def read(self, session: str) -> list[LiveState]:
        out = []
        try:
            files = list(live_dir(self.package).glob("*.json"))
        except OSError:
            return []
        for path in files:
            if path.stem == session:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            cached = self._cache.get(path)
            if cached is None or cached[0] != mtime:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    known = set(LiveState.__dataclass_fields__)
                    state = LiveState(**{k: v for k, v in data.items() if k in known})
                except (OSError, ValueError, TypeError):
                    state = None
                cached = self._cache[path] = (mtime, state)
            if cached[1] is not None and cached[1].fresh:
                out.append(cached[1])
        return out


def find_line(lines: list[str], line: int, text: str) -> int:
    """Where someone's cursor line is in our copy: the same text nearest to where it was,
    else the same line number."""
    if text.strip():
        matches = [i for i, l in enumerate(lines) if l == text]
        if matches:
            return min(matches, key=lambda i: abs(i - line))
    return max(0, min(line, len(lines) - 1))
