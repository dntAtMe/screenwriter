"""Where a project syncs to: a cloud folder, or Google Drive signed in directly.

Both keep the same .screenwriter package (see sync.py). A target hands the sync
engine a local package file, and afterwards publishes it if anything changed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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

    def lock(self, machine: str, project_id: str) -> None:
        cloud.write_lock(self.package, machine, project_id)

    def unlock(self, machine: str) -> None:
        cloud.remove_lock(self.package, machine)

    def other_machine(self, machine: str) -> str | None:
        return cloud.open_elsewhere(self.package, machine)


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

    def lock(self, machine: str, project_id: str) -> None:
        if self.client and self.file_id:
            self.client.set_properties(self.file_id, {
                "open_on": machine, "heartbeat": datetime.now(timezone.utc).isoformat(timespec="seconds")})

    def unlock(self, machine: str) -> None:
        if self.client and self.file_id and self._props.get("open_on") in (machine, None):
            try:
                self.client.set_properties(self.file_id, {"open_on": None, "heartbeat": None})
            except DriveError:
                pass

    def other_machine(self, machine: str) -> str | None:
        other, beat = self._props.get("open_on"), self._props.get("heartbeat")
        if not other or other == machine or not beat:
            return None
        age = datetime.now(timezone.utc) - datetime.fromisoformat(beat)
        return other if age < cloud.LOCK_FRESH else None


def target_from_key(key: str, project_id: str, client: DriveClient | None, cache_dir: Path):
    if key.startswith(GDRIVE_PREFIX):
        return DriveTarget(client, project_id, key.removeprefix(GDRIVE_PREFIX), cache_dir)
    return FolderTarget(Path(key))
