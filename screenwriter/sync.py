"""Sync and backup through a cloud folder (Google Drive, Dropbox, iCloud, OneDrive…).

A project is kept in the cloud folder as ONE file, `<name>.screenwriter`: a zip of the
project's history (see projecthistory.py) plus a small manifest. One file, replaced in a
single step, is something every sync client handles reliably; a folder of many small
files can arrive half-updated.

Syncing records a save point, reads the cloud copy's history, and then either uploads,
brings in the other computer's changes, or merges both:

- a document changed on one side only takes that side's version;
- a document changed on both is merged paragraph by paragraph (boards card by card, see
  merge.py); where both changed the same paragraph, ours stays and theirs is recorded in
  conflicts.json for someone to choose — nothing is ever overwritten. (A file that isn't
  text can't be merged: theirs becomes a copy next to it, "Chapter 1 (from Laptop)".);
- edited on one side and deleted on the other: the edited text is kept;
- the binder (order, titles, synopses, new and removed items) is merged item by item.

The same file is a complete backup, and a way to share a project (see share()).
"""

from __future__ import annotations

import glob
import json
import os
import re
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dulwich.client import LocalGitClient
from dulwich.graph import find_merge_base
from dulwich.repo import Repo

from .merge import CONFLICTS_FILE, ConflictRecord, dump_conflicts, merge_board, merge_conflict_lists, merge_text
from .projecthistory import BRANCH, HISTORY_DIR, ProjectHistory

PACKAGE_EXT = ".screenwriter"
FORMAT = 1
REMOTE_REF = b"refs/remotes/cloud/main"
BINDER = "project.json"


class SyncError(Exception):
    pass


# --- the package file -------------------------------------------------------------------


def package_name(project_name: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', "-", project_name).strip(" .") or "Project"
    return safe + PACKAGE_EXT


def read_manifest(package: Path) -> dict:
    try:
        with zipfile.ZipFile(package) as z:
            return json.loads(z.read("manifest.json"))
    except (OSError, KeyError, zipfile.BadZipFile, ValueError) as e:
        raise SyncError(f"{package.name} isn't a Screenwriter project file ({e})") from e


def write_package(history: ProjectHistory, project_id: str, name: str, dest: Path) -> None:
    """Write the project's whole history to `dest`, atomically."""
    history.pack()
    head = history.head()
    manifest = {
        "format": FORMAT,
        "project_id": project_id,
        "name": name,
        "head": head.decode() if head else None,
        "machine": history.machine,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    root = history.project_path / HISTORY_DIR
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{uuid.uuid4().hex[:6]}.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            for path in sorted(root.rglob("*")):
                if path.is_file() and not path.name.endswith(".lock"):
                    z.write(path, f"history/{path.relative_to(root).as_posix()}")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def _extract_history(package: Path, into: Path) -> Path:
    with zipfile.ZipFile(package) as z:
        for info in z.infolist():
            if info.filename.startswith("history/") and not info.is_dir():
                target = into / info.filename.removeprefix("history/")
                if not target.resolve().is_relative_to(into.resolve()):
                    raise SyncError("Unsafe path in project file")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
    return into


def fetch(history: ProjectHistory, package: Path) -> bytes | None:
    """Copy the package's history into ours (under refs/remotes/cloud/main); returns its head."""
    with tempfile.TemporaryDirectory() as tmp:
        remote_dir = _extract_history(package, Path(tmp) / "history")
        remote = Repo(str(remote_dir))
        try:
            head = remote.refs[BRANCH]
        except KeyError:
            return None
        finally:
            remote.close()
        LocalGitClient().fetch(str(remote_dir), history.repo, determine_wants=lambda refs, depth=None: [head])
    history.repo.refs[REMOTE_REF] = head
    return head


def open_package(package: Path, parent_folder: Path, name: str | None = None) -> Path:
    """Create a local project folder from a package file; returns its path."""
    manifest = read_manifest(package)
    base = name or manifest.get("name") or package.stem
    dest = parent_folder / base
    n = 2
    while dest.exists():
        dest = parent_folder / f"{base} {n}"
        n += 1
    dest.mkdir(parents=True)
    _extract_history(package, dest / HISTORY_DIR)
    history = ProjectHistory(dest)
    head = history.head()
    if head is None:
        raise SyncError("The project file has no saved versions")
    history.restore_files(head)
    history.close()
    return dest


def share(history: ProjectHistory, project_id: str, name: str, dest: Path) -> None:
    """Write a copy of the project (with its history) to hand to someone."""
    write_package(history, project_id, name, dest)


# --- presence ---------------------------------------------------------------------------------


# --- merging --------------------------------------------------------------------------------------


@dataclass
class Conflict:
    path: str  # our document, kept in place
    copy_path: str  # their version as a new document ("" when recorded in conflicts.json instead)
    title: str
    record: str = ""  # its id in conflicts.json


def _doc_id(path: str) -> str:
    return Path(path).name.split(".")[0]


def _merge_document(path: str, b: bytes | None, o: bytes, t: bytes):
    """(merged bytes, clashes), or None when the file can't be merged as text."""
    try:
        texts = [(x or b"").decode("utf-8") for x in (b, o, t)]
        merge = merge_board if path.endswith(".board.json") else merge_text
        text, clashes = merge(*texts)
    except (UnicodeDecodeError, ValueError, KeyError, TypeError):
        return None
    return text.encode("utf-8"), clashes


def merge_files(base: dict[str, bytes], ours: dict[str, bytes], theirs: dict[str, bytes],
                their_machine: str, our_machine: str = "") -> tuple[dict[str, bytes], list[Conflict]]:
    """Three-way merge of a project's files (see the module docstring)."""
    merged: dict[str, bytes] = {}
    conflicts: list[Conflict] = []
    copies: dict[str, str] = {}  # our doc id -> id of their conflicting copy
    records = merge_conflict_lists(base.get(CONFLICTS_FILE), ours.get(CONFLICTS_FILE), theirs.get(CONFLICTS_FILE))
    for path in sorted((set(base) | set(ours) | set(theirs)) - {BINDER, CONFLICTS_FILE}):
        b, o, t = base.get(path), ours.get(path), theirs.get(path)
        if o == t or t == b:
            result = o
        elif o == b:
            result = t
        elif o is None or t is None:  # edited on one side, deleted on the other: keep the text
            result = o if o is not None else t
        elif (done := _merge_document(path, b, o, t)) is not None:
            result, clashes = done
            for clash in clashes:
                record = ConflictRecord.from_clash(path, clash, our_machine, their_machine)
                records.append(record)
                conflicts.append(Conflict(path, "", "", record.id))
        else:
            result = o
            copy_id = uuid.uuid4().hex[:12]
            copy_path = path.replace(_doc_id(path), copy_id, 1)
            merged[copy_path] = t
            copies[_doc_id(path)] = copy_id
            conflicts.append(Conflict(path, copy_path, ""))
        if result is not None:
            merged[path] = result
    binder = merge_binder(
        json.loads(base.get(BINDER, b"{}") or b"{}"),
        json.loads(ours.get(BINDER, b"{}") or b"{}"),
        json.loads(theirs.get(BINDER, b"{}") or b"{}"),
        present={_doc_id(p) for p in merged},
        copies=copies,
        their_machine=their_machine,
    )
    merged[BINDER] = (json.dumps(binder, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    records = [r for r in records if r.path in merged]  # its document was deleted: nothing to choose
    if records:
        merged[CONFLICTS_FILE] = dump_conflicts(records)
    titles = {n["id"]: n["title"] for n in _flatten(binder.get("binder", []))}
    for c in conflicts:
        c.title = titles.get(_doc_id(c.path), c.path)
    return merged, conflicts


def _flatten(nodes: list[dict], parent: str | None = None):
    for i, n in enumerate(nodes):
        yield {**n, "_parent": parent, "_index": i}
        yield from _flatten(n.get("children", []), n["id"])


FIELDS = ("title", "kind", "synopsis", "label", "expanded")


def merge_binder(base: dict, ours: dict, theirs: dict, present: set[str],
                 copies: dict[str, str], their_machine: str) -> dict:
    """Three-way merge of project.json. `present` holds the doc ids whose files survived
    the file merge; `copies` maps a doc id to the id of their conflicting copy."""
    b = {n["id"]: n for n in _flatten(base.get("binder", []))}
    o = {n["id"]: n for n in _flatten(ours.get("binder", []))}
    t = {n["id"]: n for n in _flatten(theirs.get("binder", []))}

    # start from our tree, as flat records: id -> (fields, parent, index)
    records = {i: {k: n[k] for k in FIELDS if k in n} | {"_parent": n["_parent"], "_index": n["_index"]} for i, n in o.items()}

    def is_doc(node: dict) -> bool:
        return node.get("kind") not in ("folder", "trash")

    for i, theirs_node in t.items():
        if i in records and i in b:  # in all three: per-field three-way merge, including moves
            for key in FIELDS + ("_parent", "_index"):
                bv, ov, tv = b[i].get(key), o[i].get(key), theirs_node.get(key)
                if ov == bv and tv != bv:
                    if tv is None:
                        records[i].pop(key, None)
                    else:
                        records[i][key] = tv
        elif i not in records and i not in b:  # added on their side
            records[i] = {k: theirs_node[k] for k in FIELDS if k in theirs_node} | {
                "_parent": theirs_node["_parent"], "_index": theirs_node["_index"]}
        elif i not in records and i in b:  # we removed it; bring it back only if its text survived
            if is_doc(theirs_node) and i in present:
                records[i] = {k: theirs_node[k] for k in FIELDS if k in theirs_node} | {
                    "_parent": theirs_node["_parent"], "_index": theirs_node["_index"]}
    for i in list(records):
        if i in b and i not in t:  # they removed it
            if is_doc(records[i]) and i not in present:
                del records[i]
            elif not is_doc(records[i]) and o.get(i, {}).get("title") == b[i].get("title"):
                del records[i]  # an untouched folder; its children are re-homed below
    # conflict copies go right after the document they belong to
    for doc_id, copy_id in copies.items():
        if doc_id in records:
            source = t.get(doc_id, records[doc_id])
            records[copy_id] = {
                "title": f"{source.get('title', 'Untitled')} (from {their_machine})",
                "kind": records[doc_id].get("kind", "prose"),
                "_parent": records[doc_id]["_parent"],
                "_index": records[doc_id]["_index"] + 0.5,
            }
    # drop records for documents whose file is gone (and that aren't folders/trash)
    for i in list(records):
        if is_doc(records[i]) and i not in present:
            del records[i]

    # rebuild the tree; missing parents fall back to the top level, the Trash stays last
    children: dict[str | None, list[str]] = {}
    for i, r in records.items():
        parent = r["_parent"] if r["_parent"] in records else None
        children.setdefault(parent, []).append(i)

    def build(parent: str | None) -> list[dict]:
        ids = sorted(children.get(parent, []), key=lambda i: (records[i].get("kind") == "trash", records[i]["_index"]))
        out = []
        for i in ids:
            node = {"id": i, **{k: v for k, v in records[i].items() if not k.startswith("_")}}
            kids = build(i)
            if kids:
                node["children"] = kids
            else:
                node.pop("expanded", None)
            out.append(node)
        return out

    merged = dict(ours)
    for key in ("name", "inbox", "id", "format"):
        bv, ov, tv = base.get(key), ours.get(key), theirs.get(key)
        if ov == bv and tv != bv and tv is not None:
            merged[key] = tv
    merged["binder"] = build(None)
    return merged


# --- syncing -------------------------------------------------------------------------------------------


@dataclass
class SyncResult:
    status: str  # "uploaded" | "downloaded" | "merged" | "up-to-date"
    changed: list[str] = field(default_factory=list)  # paths changed on disk here
    conflicts: list[Conflict] = field(default_factory=list)
    machine: str = ""  # where the incoming changes came from


def _is_ancestor(repo: Repo, ancestor: bytes, descendant: bytes) -> bool:
    return ancestor == descendant or ancestor in {e.commit.id for e in repo.get_walker(include=[descendant])}


def sync(history: ProjectHistory, project_id: str, name: str, package: Path) -> SyncResult:
    """Bring this project and the cloud copy up to date with each other.
    The caller records a save point first so everything on disk is included."""
    local = history.head()
    if local is None:
        raise SyncError("Nothing to sync yet")
    if not package.exists():
        write_package(history, project_id, name, package)
        return SyncResult("uploaded")
    manifest = read_manifest(package)
    if manifest.get("project_id") != project_id:
        raise SyncError(f"{package.name} belongs to a different project ({manifest.get('name')})")
    remote = fetch(history, package)
    if remote is None or remote == local or _is_ancestor(history.repo, remote, local):
        if remote != local:
            write_package(history, project_id, name, package)
            return SyncResult("uploaded")
        return SyncResult("up-to-date")
    result = bring_in(history, remote)
    if result.status == "merged":
        write_package(history, project_id, name, package)
    return result


def bring_in(history: ProjectHistory, remote: bytes) -> SyncResult:
    """Make `remote` (already fetched) part of our history: take it if only they changed,
    otherwise merge. Updates the project files; doesn't write any package."""
    local = history.head()
    if remote == local or _is_ancestor(history.repo, remote, local):
        return SyncResult("up-to-date")
    their_machine = history.get(remote).person
    if _is_ancestor(history.repo, local, remote):  # only they changed: take theirs
        changed = [c.path for c in history.changes(remote, against=local)]
        history.set_head(remote)
        history.restore_files(remote)
        return SyncResult("downloaded", changed, machine=their_machine)

    bases = find_merge_base(history.repo, [local, remote])
    base_files = history.files_at(bases[0]) if bases else {}
    ours = history.files_at(local)
    theirs = history.files_at(remote)
    merged, conflicts = merge_files(base_files, ours, theirs, their_machine, history.person or history.machine)
    message = f"Merged changes from {their_machine}"
    commit = history.commit_files(merged, message, [local, remote])
    history.set_head(commit)
    history.restore_files(commit)
    changed = sorted(p for p in set(ours) | set(merged) if ours.get(p) != merged.get(p))
    return SyncResult("merged", changed, conflicts, their_machine)


def absorb(history: ProjectHistory, project_id: str, copy: Path) -> SyncResult | None:
    """Bring in a stray copy of the project file — one a cloud app saved as "(conflicted copy)"
    or "(1)" when two computers wrote at once. None if it isn't this project's."""
    try:
        if read_manifest(copy).get("project_id") != project_id:
            return None
        remote = fetch(history, copy)
    except (SyncError, OSError, zipfile.BadZipFile, KeyError):
        return None
    return bring_in(history, remote) if remote else SyncResult("up-to-date")


def stray_copies(package: Path) -> list[Path]:
    """Other .screenwriter files next to the package whose names suggest a copy of it
    ("Story (1).screenwriter", "Story (Anna's conflicted copy).screenwriter", "Story-LAPTOP.screenwriter")."""
    stem = package.name.removesuffix(PACKAGE_EXT)
    try:
        return sorted(p for p in package.parent.glob(f"{glob.escape(stem)}*{PACKAGE_EXT}")
                      if p != package and p.is_file())
    except OSError:
        return []


# --- cloud folders on this computer --------------------------------------------------------------------


def cloud_folders() -> list[tuple[str, Path]]:
    """Synced folders we can suggest: Google Drive, Dropbox, iCloud Drive, OneDrive."""
    home = Path.home()
    found: list[tuple[str, Path]] = []

    def add(label: str, path: Path) -> None:
        if path.is_dir() and all(p != path for _, p in found):
            found.append((label, path))

    cloud_storage = home / "Library" / "CloudStorage"  # macOS File Provider locations
    if cloud_storage.is_dir():
        for p in sorted(cloud_storage.iterdir()):
            if p.name.startswith("GoogleDrive"):
                add("Google Drive", p / "My Drive" if (p / "My Drive").is_dir() else p)
            elif p.name.startswith("Dropbox"):
                add("Dropbox", p)
            elif p.name.startswith("OneDrive"):
                add("OneDrive", p)
    add("iCloud Drive", home / "Library" / "Mobile Documents" / "com~apple~CloudDocs")
    for name in ("Google Drive", "My Drive"):
        add("Google Drive", home / name)
    add("Dropbox", home / "Dropbox")
    for p in sorted(home.glob("OneDrive*")):
        add("OneDrive", p)
    if os.name == "nt":  # Google Drive for desktop mounts a drive letter
        for letter in "GHIJKLMNOPQRSTUVWXYZ":
            add("Google Drive", Path(f"{letter}:/My Drive"))
    return found


def inside(path: Path, folder: Path) -> bool:
    try:
        return path.resolve().is_relative_to(folder.resolve())
    except OSError:
        return False
