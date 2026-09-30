from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat

from screenwriter import secrets
from screenwriter.bible import format_entry
from screenwriter.project import CHARACTER, NOTE, FOLDER, Project

TEXT = """# Waterdeep

The city of splendours.

GM: the Open Lord is
secretly a doppelganger.

Everyone knows the harbour.

## The Xanathar (GM)
A beholder crime lord.

### Lair
Under the Yawning Portal.

## Taverns
The Yawning Portal. [[prices are double]]
- Secret: Durnan was an adventurer.
"""


def test_secret_lines():
    marked = [line for line, s in zip(TEXT.split("\n"), secrets.secret_lines(TEXT)) if s]
    assert marked == [
        "GM: the Open Lord is", "secretly a doppelganger.",
        "## The Xanathar (GM)", "A beholder crime lord.", "", "### Lair", "Under the Yawning Portal.", "",
        "- Secret: Durnan was an adventurer.",
    ]
    assert secrets.count_secrets(TEXT) == 3


def test_player_copy_leaves_secrets_out():
    assert secrets.player_copy(TEXT) == (
        "# Waterdeep\n\nThe city of splendours.\n\nEveryone knows the harbour.\n\n## Taverns\nThe Yawning Portal.\n"
    )
    assert not secrets.has_secrets("Just a note.") and secrets.has_secrets("A [[note]].")


def test_highlighter_shades_secrets(qapp):
    from screenwriter.editors.prose import ProseEditor

    editor = ProseEditor()
    editor.set_text(TEXT)
    doc = editor.document()

    def shaded(n: int) -> bool:
        ranges = doc.findBlockByNumber(n).layout().formats()  # keep the list alive while reading from it
        return any(QTextCharFormat(r.format).background().style() != Qt.BrushStyle.NoBrush for r in ranges)

    lines = TEXT.split("\n")
    assert [shaded(i) for i in range(len(lines))] == [bool(s) and bool(l) for l, s in zip(lines, secrets.secret_lines(TEXT))]
    editor.deleteLater()


def test_player_handout_export(tmp_path):
    from screenwriter.exportdialog import export_formats

    project = Project.create(tmp_path / "Camp", "Camp")
    lore = project.new_node(NOTE, "Lore")
    project.write_text(lore, TEXT)
    vex = project.new_node(CHARACTER, "Vex")
    project.write_text(vex, format_entry({"name": "Vex", "role": "Fence", "description": "A tiefling with a limp.",
                                          "aliases": "the fox"}, "Sells anything.\n\nGM: works for the Zhentarim.\n"))
    folder = project.new_node(FOLDER, "Handouts")
    folder.children = [lore, vex]
    project.root.insert(0, folder)

    what, formats = export_formats(project, lore, project.read_text)
    labels = [f.label for f in formats]
    assert labels[-2:] == ["Player handout, PDF — 3 GM-only passages left out",
                           "Player handout, Markdown — 3 GM-only passages left out"]
    out = tmp_path / "lore.md"
    formats[-1].run(str(out), "Letter")
    assert "doppelganger" not in out.read_text() and "Taverns" in out.read_text()
    assert formats[-1].suffix == " (players)"

    what, formats = export_formats(project, vex, project.read_text)
    assert what == "Character “Vex”" and len(formats) == 2
    formats[-1].run(str(out), "Letter")
    card = out.read_text()
    assert card.startswith("# Vex\n\n*Fence*\n\nA tiefling with a limp.\n\nSells anything.")
    assert "Zhentarim" not in card and "the fox" not in card

    what, formats = export_formats(project, folder, project.read_text)
    formats[-1].run(str(out), "Letter")
    assert "# Waterdeep" in out.read_text() and "# Vex" in out.read_text()

    plain = project.new_node(NOTE, "Plain")
    project.write_text(plain, "Nothing to hide.")
    assert [f.label for f in export_formats(project, plain, project.read_text)[1]] == [
        "PDF", "Word (.docx, manuscript format)", "Markdown (.md)"]


def test_marker_position():
    assert secrets.marker("GM: the Open Lord") == (0, 3)
    assert secrets.marker("- Secret: Durnan") == (2, 9)
    assert secrets.marker("## The Xanathar (GM)") == (16, 20)
    assert secrets.marker("Not a heading (GM)") is None
    assert secrets.marker("Plain text") is None
