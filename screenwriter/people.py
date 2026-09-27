"""Who is working on a project: your name, a colour per person, and presence.

Presence is a small heartbeat each open window writes next to the synced project
file: who (person and computer), which document is in front, and when. Records older
than FRESH are ignored — a window that crashed simply fades out.

Qt-free; the sync targets (synctargets.py) decide where the records are kept.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

FRESH = timedelta(minutes=3)
COLOURS = ["#d9534f", "#2f8a86", "#8a63b8", "#c07a2c", "#4f7cac", "#6b8f4e", "#b5563c", "#c2185b"]


def default_name() -> str:
    """A first guess at the writer's name: their login, tidied ("kacper" → "Kacper")."""
    name = getpass.getuser().replace(".", " ").replace("_", " ").strip()
    return name.title() if name.islower() else (name or "Writer")


def colour_for(name: str) -> str:
    """The same colour for a name everywhere, on every computer."""
    digest = hashlib.sha1(name.strip().lower().encode("utf-8")).digest()
    return COLOURS[digest[0] % len(COLOURS)]


def new_session() -> str:
    return uuid.uuid4().hex[:10]


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Presence:
    session: str  # one open window
    person: str
    machine: str
    doc_id: str = ""  # the document in front, if any
    doc_title: str = ""
    heartbeat: str = ""  # ISO time, UTC

    @property
    def fresh(self) -> bool:
        try:
            return now() - datetime.fromisoformat(self.heartbeat) < FRESH
        except ValueError:
            return False

    def label(self, me: str = "") -> str:
        """"Anna", or "Kacper on LAPTOP" for yourself on another computer."""
        return f"{self.person} on {self.machine}" if self.person == me else self.person

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> Presence | None:
        try:
            data = json.loads(text)
            known = set(cls.__dataclass_fields__)
            return cls(**{k: str(v) for k, v in data.items() if k in known})
        except (ValueError, TypeError):
            return None


def stamp(p: Presence) -> Presence:
    p.heartbeat = now().isoformat(timespec="seconds")
    return p


# --- presence in a folder (next to a .screenwriter file in a cloud folder) -------------------


def presence_dir(package: Path) -> Path:
    return package.with_name(package.name + ".people")


def write_presence(package: Path, p: Presence) -> None:
    """One small file per open window, so people never overwrite each other's."""
    folder = presence_dir(package)
    try:
        folder.mkdir(exist_ok=True)
        tmp = folder / f"{p.session}.json.tmp"
        tmp.write_text(stamp(p).to_json(), encoding="utf-8")
        tmp.replace(folder / f"{p.session}.json")
    except OSError:
        pass


def remove_presence(package: Path, session: str) -> None:
    try:
        (presence_dir(package) / f"{session}.json").unlink(missing_ok=True)
    except OSError:
        pass


def read_presence(package: Path, session: str = "") -> list[Presence]:
    """Everyone else with the project open now (not this window); stale records are tidied away."""
    folder = presence_dir(package)
    out = []
    try:
        files = list(folder.glob("*.json"))
    except OSError:
        return []
    for path in files:
        try:
            p = Presence.from_json(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if p is None or p.session == session:
            continue
        if p.fresh:
            out.append(p)
        else:
            try:
                path.unlink()
            except OSError:
                pass
    return sorted(out, key=lambda p: (p.person.lower(), p.machine))
