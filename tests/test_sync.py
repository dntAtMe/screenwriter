import json
from datetime import datetime, timedelta, timezone

import pytest

from screenwriter.merge import THEIRS, load_conflicts, resolve, save_conflicts
from screenwriter.project import FOLDER, PROSE, Project
from screenwriter.projecthistory import ProjectHistory
from screenwriter.sync import (
    SyncError,
    lock_path,
    open_elsewhere,
    open_package,
    package_name,
    read_manifest,
    remove_lock,
    share,
    sync,
    write_lock,
)


class Machine:
    """One computer with its own copy of the project."""

    def __init__(self, path, name):
        self.project = Project.open(path)
        self.history = ProjectHistory(path)
        self.history.machine = name

    def reload(self):
        self.project = Project.open(self.project.path)

    def write(self, node_id, text):
        self.project.write_text(self.project.find(node_id), text)

    def read(self, node_id):
        node = self.project.find(node_id)
        return self.project.read_text(node) if node else None

    def sync(self, package):
        self.history.save_point()
        result = sync(self.history, self.project.id, self.project.name, package)
        self.reload()
        return result


@pytest.fixture
def two_computers(tmp_path):
    p = Project.create(tmp_path / "desktop" / "Story", "Story")
    folder = p.new_node(FOLDER, "Manuscript")
    ch1, ch2 = p.new_node(PROSE, "Chapter 1"), p.new_node(PROSE, "Chapter 2")
    folder.children = [ch1, ch2]
    p.root.insert(0, folder)
    p.save()
    p.write_text(ch1, "One.")
    p.write_text(ch2, "Two.")
    desktop = Machine(p.path, "Desktop")
    cloud = tmp_path / "Google Drive" / package_name("Story")
    assert desktop.sync(cloud).status == "uploaded"
    laptop_path = open_package(cloud, tmp_path / "laptop")
    laptop = Machine(laptop_path, "Laptop")
    return desktop, laptop, cloud, ch1.id, ch2.id


def test_package_round_trip(two_computers):
    desktop, laptop, cloud, ch1, ch2 = two_computers
    assert read_manifest(cloud)["name"] == "Story"
    assert laptop.read(ch1) == "One." and laptop.project.id == desktop.project.id
    assert laptop.sync(cloud).status == "up-to-date"


def test_changes_flow_one_way(two_computers):
    desktop, laptop, cloud, ch1, _ = two_computers
    laptop.write(ch1, "One, rewritten on the train.")
    assert laptop.sync(cloud).status == "uploaded"
    result = desktop.sync(cloud)
    assert result.status == "downloaded" and result.machine == "Laptop"
    assert any(path.endswith(f"{ch1}.md") for path in result.changed)
    assert desktop.read(ch1) == "One, rewritten on the train."


def test_edits_to_different_documents_merge(two_computers):
    desktop, laptop, cloud, ch1, ch2 = two_computers
    laptop.write(ch1, "Laptop's chapter one.")
    laptop.sync(cloud)
    desktop.write(ch2, "Desktop's chapter two.")
    result = desktop.sync(cloud)
    assert result.status == "merged" and not result.conflicts
    assert desktop.read(ch1) == "Laptop's chapter one." and desktop.read(ch2) == "Desktop's chapter two."
    assert laptop.sync(cloud).status == "downloaded"
    assert laptop.read(ch2) == "Desktop's chapter two."
    assert desktop.history.log()[0].title == "Merged changes from Laptop"


def test_same_document_different_paragraphs_merge(two_computers):
    desktop, laptop, cloud, ch1, _ = two_computers
    for m in (desktop, laptop):
        m.write(ch1, "First.\n\nSecond.\n\nThird.")
        m.sync(cloud)
    laptop.write(ch1, "First, by laptop.\n\nSecond.\n\nThird.")
    laptop.sync(cloud)
    desktop.write(ch1, "First.\n\nSecond.\n\nThird, by desktop.")
    result = desktop.sync(cloud)
    assert result.status == "merged" and not result.conflicts
    assert desktop.read(ch1) == "First, by laptop.\n\nSecond.\n\nThird, by desktop."
    laptop.sync(cloud)
    assert laptop.read(ch1) == desktop.read(ch1)


def test_same_paragraph_is_recorded_for_both_to_resolve(two_computers):
    desktop, laptop, cloud, ch1, _ = two_computers
    laptop.write(ch1, "Laptop version.")
    laptop.sync(cloud)
    desktop.write(ch1, "Desktop version.")
    result = desktop.sync(cloud)
    assert result.status == "merged"
    [conflict] = result.conflicts
    assert conflict.title == "Chapter 1" and conflict.copy_path == ""
    assert desktop.read(ch1) == "Desktop version."  # ours stays; no copy documents
    assert [n.title for n in desktop.project.root[0].children] == ["Chapter 1", "Chapter 2"]
    [record] = load_conflicts(desktop.project.path)
    assert (record.kept, record.other, record.kept_by, record.other_by) == (
        "Desktop version.", "Laptop version.", "Desktop", "Laptop")

    # the laptop gets the record too, and resolves it
    laptop.sync(cloud)
    assert laptop.read(ch1) == "Desktop version."
    [seen] = load_conflicts(laptop.project.path)
    assert seen.id == record.id
    laptop.write(ch1, resolve(laptop.read(ch1), seen, THEIRS))
    save_conflicts(laptop.project.path, [])
    laptop.sync(cloud)
    desktop.sync(cloud)
    assert desktop.read(ch1) == "Laptop version."
    assert load_conflicts(desktop.project.path) == []


def test_unreadable_file_still_becomes_a_copy(two_computers):
    desktop, laptop, cloud, ch1, _ = two_computers
    laptop.project.doc_path(laptop.project.find(ch1)).write_bytes(b"\xff\xfe laptop")
    laptop.sync(cloud)
    desktop.project.doc_path(desktop.project.find(ch1)).write_bytes(b"\xff\xfe desktop")
    [conflict] = desktop.sync(cloud).conflicts
    assert conflict.copy_path
    assert [n.title for n in desktop.project.root[0].children] == ["Chapter 1", "Chapter 1 (from Laptop)", "Chapter 2"]


def test_binder_changes_merge_item_by_item(two_computers):
    desktop, laptop, cloud, ch1, ch2 = two_computers
    # laptop: rename chapter 2 and give chapter 1 a synopsis
    laptop.project.find(ch2).title = "Chapter 2 — Fog"
    laptop.project.find(ch1).synopsis = "Mara keeps the light."
    laptop.project.save()
    laptop.sync(cloud)
    # desktop: add chapter 3 to the manuscript
    ch3 = desktop.project.new_node(PROSE, "Chapter 3")
    desktop.project.root[0].children.append(ch3)
    desktop.project.save()
    desktop.write(ch3.id, "Three.")
    assert desktop.sync(cloud).status == "merged"
    titles = [n.title for n in desktop.project.root[0].children]
    assert titles == ["Chapter 1", "Chapter 2 — Fog", "Chapter 3"]
    assert desktop.project.find(ch1).synopsis == "Mara keeps the light."
    assert desktop.project.root[-1].kind == "trash"


def test_edit_beats_delete(two_computers):
    desktop, laptop, cloud, ch1, ch2 = two_computers
    node = laptop.project.find(ch2)
    laptop.project.delete_files(node)
    laptop.project.root[0].children = [n for n in laptop.project.root[0].children if n.id != ch2]
    laptop.project.save()
    laptop.sync(cloud)
    desktop.write(ch2, "Two, but better.")
    desktop.sync(cloud)
    assert desktop.read(ch2) == "Two, but better."
    assert desktop.project.find(ch2) is not None


def test_delete_on_one_side_applies_when_untouched(two_computers):
    desktop, laptop, cloud, ch1, ch2 = two_computers
    node = laptop.project.find(ch2)
    laptop.project.delete_files(node)
    laptop.project.root[0].children = [n for n in laptop.project.root[0].children if n.id != ch2]
    laptop.project.save()
    laptop.sync(cloud)
    desktop.write(ch1, "Edited elsewhere.")
    desktop.sync(cloud)
    assert desktop.project.find(ch2) is None and desktop.read(ch1) == "Edited elsewhere."


def test_wrong_project_is_refused(two_computers, tmp_path):
    desktop, laptop, cloud, _, _ = two_computers
    other = Machine(Project.create(tmp_path / "other" / "Story", "Story").path, "Desktop")
    other.history.save_point()
    with pytest.raises(SyncError):
        sync(other.history, other.project.id, "Story", cloud)


def test_presence_lock(two_computers):
    desktop, laptop, cloud, _, _ = two_computers
    write_lock(cloud, "Laptop", laptop.project.id)
    assert open_elsewhere(cloud, "Desktop") == "Laptop"
    assert open_elsewhere(cloud, "Laptop") is None
    stale = json.loads(lock_path(cloud).read_text())
    stale["heartbeat"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    lock_path(cloud).write_text(json.dumps(stale))
    assert open_elsewhere(cloud, "Desktop") is None
    remove_lock(cloud, "Laptop")
    assert not lock_path(cloud).exists()


def test_share_a_copy(two_computers, tmp_path):
    desktop, _, _, ch1, _ = two_computers
    copy = tmp_path / "Outbox" / "Story for Ana.screenwriter"
    share(desktop.history, desktop.project.id, "Story", copy)
    opened = Project.open(open_package(copy, tmp_path / "ana"))
    assert opened.read_text(opened.find(ch1)) == "One."
    assert ProjectHistory(opened.path).log()  # history travels with it
