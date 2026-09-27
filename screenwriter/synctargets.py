"""Where a project syncs to: a cloud folder, or Google Drive signed in directly.

Both keep the same .screenwriter package (see sync.py). A target hands the sync
engine a local package file, and afterwards publishes it if anything changed. It also
keeps the presence records of the people who have the project open (see people.py).
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

from . import people
from . import sync as cloud
from .google_drive import DriveClient, DriveError

GDRIVE_PREFIX = "gdrive:"


class TargetError(Exception):
    pass


class FolderTarget:
    kind = "folder"

    def __init__(self, package: Path):
        self.package = package
        self._mtime: float | None = None

    @property
    def key(self) -> str:
        return str(self.package)

    def describe(self) -> str:
        return str(self.package)

    def available(self) -> bool:
        return self.package.parent.is_dir()

    def unavailable_reason(self) -> str:
        return f"Can't reach {self.package.parent}. Is Google Drive (or your cloud app) running?"

    def prepare(self, project) -> Path:
        return self.package

    def finish(self, result, project) -> None:
        self._mtime = self._stat()

    def changed(self) -> bool:
        return self._stat() != self._mtime

    def _stat(self) -> float | None:
        try:
            return self.package.stat().st_mtime
        except OSError:
            return None

    # --- one writer at a time -------------------------------------------------------------

    LOCK_WAIT = 5.0  # seconds to wait for someone else's sync to finish
    LOCK_STALE = 60.0  # a lock this old was left by a crash: take it over

    @contextmanager
    def exclusive(self, session: str):
        """Hold "<name>.screenwriter.writing" while syncing, so two people saving to a shared
        drive at the same moment take turns instead of overwriting each other's upload."""
        lock = self.package.with_name(self.package.name + ".writing")
        deadline = time.monotonic() + self.LOCK_WAIT
        mine = False
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, session.encode())
                os.close(fd)
                mine = True
                break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > self.LOCK_STALE:
                        lock.unlink(missing_ok=True)
                        continue
                except OSError:
                    continue
                if time.monotonic() > deadline:
                    raise TargetError("Someone else is saving to the shared project right now — trying again shortly.")
                time.sleep(0.2)
            except OSError:
                break  # a folder we can't lock in (read-only?): go ahead as before
        try:
            yield
        finally:
            if mine:
                lock.unlink(missing_ok=True)

    def strays(self) -> list[Path]:
        return cloud.stray_copies(self.package)

    def retire(self, copy: Path) -> None:
        """Keep a folded-in copy as a backup, under a name nothing will pick up again."""
        try:
            copy.replace(copy.with_name(copy.name + ".merged"))
        except OSError:
            pass

    # --- presence ----------------------------------------------------------------------------

    def announce(self, presence: people.Presence) -> None:
        people.write_presence(self.package, presence)

    def leave(self, session: str) -> None:
        people.remove_presence(self.package, session)

    def others(self, session: str) -> list[people.Presence]:
        return people.read_presence(self.package, session)


class DriveTarget:
    kind = "gdrive"

    def __init__(self, client: DriveClient | None, project_id: str, file_id: str | None, cache_dir: Path):
        self.client = client  # None when not signed in on this computer
        self.project_id = project_id
        self.file_id = file_id or None
        self.cache = cache_dir / f"{project_id}{cloud.PACKAGE_EXT}"
        self.head: str | None = None  # history head we last exchanged with Drive
        self._props: dict = {}

    @property
    def key(self) -> str:
        return GDRIVE_PREFIX + (self.file_id or "")

    def describe(self) -> str:
        who = f" ({self.client.account.email})" if self.client and self.client.account.email else ""
        return f"Google Drive{who} → My Drive/Screenwriter"

    def available(self) -> bool:
        return self.client is not None

    def unavailable_reason(self) -> str:
        return "Sign in with Google (File → Sync & Backup…) to sync this project."

    def _require(self) -> DriveClient:
        if self.client is None:
            raise TargetError(self.unavailable_reason())
        return self.client

    def _meta(self):
        client = self._require()
        if self.file_id:
            try:
                meta = client.metadata(self.file_id)
            except DriveError as e:
                if "(404)" in str(e):  # deleted or trashed in Drive: start afresh
                    self.file_id = None
                    return None
                raise
        else:
            meta = client.find_project(self.project_id)
        if meta:
            self.file_id = meta.id
            self._props = meta.properties
        return meta

    def prepare(self, project) -> Path:
        meta = self._meta()
        if meta is None:
            self.cache.unlink(missing_ok=True)  # nothing in Drive yet: sync will create it
        elif meta.properties.get("head") != self.head or not self.cache.exists():
            self._require().download(meta.id, self.cache)
            self.head = meta.properties.get("head")
        return self.cache

    def finish(self, result, project) -> None:
        if result.status in ("uploaded", "merged"):
            head = cloud.read_manifest(self.cache).get("head")
            meta = self._require().upload(self.cache, cloud.package_name(project.name), project.id, self.file_id,
                                          {"head": head})
            self.file_id, self.head, self._props = meta.id, head, meta.properties
        elif result.status in ("downloaded", "up-to-date"):
            self.head = cloud.read_manifest(self.cache).get("head")

    def changed(self) -> bool:
        meta = self._meta()
        return meta is not None and meta.properties.get("head") != self.head

    def exclusive(self, session: str):
        return nullcontext()  # Drive keeps its own revisions; sync compares heads

    def strays(self) -> list[Path]:
        return []

    def retire(self, copy: Path) -> None:
        pass

    # Presence lives in the package file's appProperties, one short key per open window
    # ("p_<session>"). Drive allows 124 bytes for a key and its value together.

    PRESENCE = "p_"

    @staticmethod
    def _encode(p: people.Presence) -> str:
        title = p.doc_title
        while True:
            value = json.dumps({"n": p.person, "m": p.machine, "d": p.doc_id, "t": title, "h": p.heartbeat},
                               ensure_ascii=False, separators=(",", ":"))
            if len((DriveTarget.PRESENCE + p.session + value).encode("utf-8")) <= 124 or not title:
                return value
            title = title[:-1]

    def _presences(self) -> list[people.Presence]:
        out = []
        for key, value in self._props.items():
            if key.startswith(self.PRESENCE):
                try:
                    d = json.loads(value)
                    out.append(people.Presence(key.removeprefix(self.PRESENCE), d.get("n", ""), d.get("m", ""),
                                               d.get("d", ""), d.get("t", ""), d.get("h", "")))
                except (ValueError, AttributeError):
                    continue
        return out

    def announce(self, presence: people.Presence) -> None:
        if not (self.client and self.file_id):
            return
        people.stamp(presence)
        changes = {self.PRESENCE + p.session: None for p in self._presences() if not p.fresh}  # tidy up
        changes[self.PRESENCE + presence.session] = self._encode(presence)
        self.client.set_properties(self.file_id, changes)
        self._props.update({k: v for k, v in changes.items() if v is not None})
        for k in [k for k, v in changes.items() if v is None]:
            self._props.pop(k, None)

    def leave(self, session: str) -> None:
        if self.client and self.file_id:
            try:
                self.client.set_properties(self.file_id, {self.PRESENCE + session: None})
            except DriveError:
                pass

    def others(self, session: str) -> list[people.Presence]:
        return sorted((p for p in self._presences() if p.session != session and p.fresh),
                      key=lambda p: (p.person.lower(), p.machine))


def target_from_key(key: str, project_id: str, client: DriveClient | None, cache_dir: Path):
    if key.startswith(GDRIVE_PREFIX):
        return DriveTarget(client, project_id, key.removeprefix(GDRIVE_PREFIX), cache_dir)
    return FolderTarget(Path(key))
