from screenwriter.project import NOTE, PROSE, SCREENPLAY, TRASH, Project


def test_create_add_reopen(tmp_path):
    project = Project.create(tmp_path / "Story", "Story")
    assert [n.kind for n in project.root] == [TRASH]

    chapter = project.new_node(PROSE, "Chapter 1")
    script = project.new_node(SCREENPLAY, "Pilot")
    chapter.children.append(project.new_node(NOTE, "Idea"))
    project.root[:0] = [chapter, script]
    project.write_text(script, "INT. HOUSE - DAY\n")
    project.save()

    assert project.doc_path(chapter).suffix == ".md"
    assert project.doc_path(script).suffix == ".fountain"

    reopened = Project.open(tmp_path / "Story")
    assert [n.title for n in reopened.root] == ["Chapter 1", "Pilot", "Trash"]
    assert reopened.root[0].children[0].title == "Idea"
    assert reopened.read_text(reopened.find(script.id)) == "INT. HOUSE - DAY\n"


def test_delete_files_removes_subtree(tmp_path):
    project = Project.create(tmp_path / "S", "S")
    parent = project.new_node(PROSE, "A")
    child = project.new_node(NOTE, "B")
    parent.children.append(child)
    project.delete_files(parent)
    assert not project.doc_path(parent).exists()
    assert not project.doc_path(child).exists()


def test_sample_project_opens():
    from pathlib import Path

    sample = Project.open(Path(__file__).parent.parent / "examples" / "The Lighthouse")
    assert sample.name == "The Lighthouse"
    assert "MARA" in sample.read_text(sample.find("pilot"))


def test_documents_are_saved_with_plain_newlines(tmp_path):
    from screenwriter.project import PROSE, Project

    p = Project.create(tmp_path / "P", "P")
    node = p.new_node(PROSE, "Doc")
    p.root.insert(0, node)
    p.write_text(node, "a\nb\n")
    assert p.doc_path(node).read_bytes() == b"a\nb\n"


def test_kinds_from_a_newer_version_are_kept(qapp, tmp_path):
    import json

    from PySide6.QtCore import QSettings

    from conftest import dispose
    from screenwriter.mainwindow import MainWindow

    project = Project.create(tmp_path / "Newer", "Newer")
    data = json.loads((project.path / "project.json").read_text())
    data["binder"].insert(0, {"id": "sword", "title": "Dawnbringer", "kind": "spaceship"})
    (project.path / "project.json").write_text(json.dumps(data))
    (project.path / "docs" / "sword.md").write_text("---\nname: Dawnbringer\n---\nA glowing blade.\n")

    QSettings().clear()
    w = MainWindow()
    w.open_project(project.path)
    assert w.project is not None and w.binder.find_item("sword") is not None
    w.open_document("sword")
    assert w.editors["sword"].text().endswith("A glowing blade.\n")
    w.save_all()
    assert json.loads((project.path / "project.json").read_text())["binder"][0]["kind"] == "spaceship"
    dispose(w)


def test_a_project_that_fails_to_open_does_not_crash(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMessageBox

    from conftest import dispose
    from screenwriter.mainwindow import MainWindow

    project = Project.create(tmp_path / "Broken", "Broken")
    before = (project.path / "project.json").read_text()
    QSettings().clear()
    w = MainWindow()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[2]))
    monkeypatch.setattr(w.binder, "load", lambda p: 1 / 0)
    w.open_project(project.path)
    assert w.project is None and warnings and "Could not open Broken" in warnings[0]
    assert w.stack.currentWidget() is w.welcome
    assert (project.path / "project.json").read_text() == before  # nothing written over it
    dispose(w)
