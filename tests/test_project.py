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
