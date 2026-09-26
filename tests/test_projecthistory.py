import json

import pytest

from screenwriter.project import NOTE, PROSE, Project
from screenwriter.projecthistory import AUTO_MESSAGE, HISTORY_DIR, ProjectHistory, read_tracked_files


@pytest.fixture
def project(tmp_path):
    p = Project.create(tmp_path / "Story", "Story")
    chapter = p.new_node(PROSE, "Chapter 1")
    note = p.new_node(NOTE, "Ideas")
    p.root[:0] = [chapter, note]
    p.write_text(chapter, "It was a dark night.")
    p.write_text(note, "- a ghost ship")
    p.save()
    return p, chapter, note


def test_save_points_only_when_something_changed(project):
    p, chapter, _ = project
    history = ProjectHistory(p.path)
    first = history.save_point()
    assert first is not None and first.auto and first.title == AUTO_MESSAGE
    assert history.save_point() is None  # nothing changed
    named = history.save_point("Before rewrite")  # a named version is always recorded
    assert named.title == "Before rewrite" and not named.auto
    p.write_text(chapter, "It was a bright morning.")
    second = history.save_point()
    assert [s.id for s in history.log()] == [second.id, named.id, first.id]
    assert second.parents == [named.id]


def test_tracked_files_skip_history_and_snapshots(project):
    p, chapter, _ = project
    (p.path / "snapshots" / "x").mkdir(parents=True)
    (p.path / "snapshots" / "x" / "old.md").write_text("old")
    (p.path / "docs" / "leftover.md.tmp").write_text("tmp")
    ProjectHistory(p.path).save_point()
    files = read_tracked_files(p.path)
    assert "project.json" in files and f"docs/{chapter.id}.md" in files
    assert not any(k.startswith(("snapshots", HISTORY_DIR)) or k.endswith(".tmp") for k in files)


def test_changes_log_per_document_and_titles(project):
    p, chapter, note = project
    history = ProjectHistory(p.path)
    history.save_point()
    p.write_text(chapter, "Changed.")
    history.save_point()
    p.delete_files(note)
    p.root = [n for n in p.root if n.id != note.id]
    p.save()
    last = history.save_point()
    kinds = {c.path: c.kind for c in history.changes(last.id)}
    assert kinds == {f"docs/{note.id}.md": "deleted", "project.json": "modified"}
    chapter_path = f"docs/{chapter.id}.md"
    assert len(history.log(chapter_path)) == 2
    first = history.log()[-1]
    assert history.file_at(first.id, chapter_path) == b"It was a dark night."
    assert history.titles_at(first.id)[f"docs/{note.id}.md"] == ("Ideas", "note")
    node, parent = history.node_at(first.id, note.id)
    assert node.title == "Ideas" and parent is None


def test_restore_document_and_whole_project(project):
    p, chapter, note = project
    history = ProjectHistory(p.path)
    first = history.save_point()
    p.write_text(chapter, "Rewritten.")
    extra = p.new_node(PROSE, "Chapter 2")
    p.root.insert(1, extra)
    p.save()
    history.save_point()

    history.restore_files(first.id, [f"docs/{chapter.id}.md"])
    assert p.read_text(chapter) == "It was a dark night."
    assert p.doc_path(extra).exists()

    history.restore_files(first.id)  # whole project
    assert not p.doc_path(extra).exists()
    assert [n["title"] for n in json.loads((p.path / "project.json").read_text())["binder"]] == ["Chapter 1", "Ideas", "Trash"]


def test_history_survives_reopening(project):
    p, _, _ = project
    ProjectHistory(p.path).save_point("One")
    again = ProjectHistory(p.path)
    assert [s.title for s in again.log()] == ["One"]
    again.pack()
    assert [s.title for s in ProjectHistory(p.path).log()] == ["One"]
