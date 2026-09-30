from PySide6.QtCore import QSettings

from conftest import dispose
from screenwriter import campaign
from screenwriter.project import FOLDER, NOTE, Node, Project, walk


def test_new_campaign_has_the_gm_folders(tmp_path):
    project = Project.create(tmp_path / "Tomb", "Tomb of Horrors")
    campaign.create_campaign(project)
    project = Project.open(project.path)
    folders = [n.title for n in project.root if n.kind == FOLDER]
    assert folders[:3] == ["Campaign", campaign.SESSIONS, "Adventures"]
    assert project.root[-1].kind == "trash"
    overview = next(n for n in walk(project.root) if n.title == "Campaign Overview")
    assert project.read_text(overview).startswith("# Tomb of Horrors\n")
    first = next(n for n in walk(project.root) if n.title == "Session 1")
    assert "## Secrets & clues" in project.read_text(first)


def test_session_numbers_and_recap():
    nodes = [Node("a", "Session 2 – The Heist", NOTE), Node("b", "Session 10", NOTE), Node("c", "Sessions", FOLDER),
             Node("d", "Notes", NOTE)]
    assert [n.id for n in campaign.sessions(nodes)] == ["a", "b"]
    assert campaign.next_title(nodes) == "Session 11"
    assert campaign.next_title([]) == "Session 1"

    last = campaign.session_text("Session 2")
    assert campaign.recap_from(last) == ""  # only the hint: nothing happened yet
    last = last.rstrip() + "\n- The party burned down the inn.\n- Mira owes Vex 50 gp.\n"
    text = campaign.session_text("Session 3", last)
    assert campaign.section(text, "Recap") == "- The party burned down the inn.\n- Mira owes Vex 50 gp."
    assert text.startswith("# Session 3\n")


def test_new_session_and_npcs_in_a_campaign(qapp, tmp_path):
    from screenwriter.mainwindow import MainWindow
    from screenwriter.newproject import CAMPAIGN

    QSettings().clear()
    w = MainWindow()
    w.create_project(tmp_path / "Camp", "Camp", CAMPAIGN)
    assert w.tabs.tabText(w.tabs.currentIndex()) == "Campaign Overview"
    session1 = next(n for n in walk(w.binder.to_nodes()) if n.title == "Session 1")
    w.open_document(session1.id)
    w.editors[session1.id].replace_all(w.editors[session1.id].text() + "\nThey met Vex at the docks.\n")
    w.new_session()
    folder = next(n for n in w.binder.to_nodes() if n.title == campaign.SESSIONS)
    assert [n.title for n in folder.children] == ["Session 1", "Session 2"]
    text = w.editors[folder.children[1].id].text()
    assert "They met Vex at the docks." in campaign.section(text, "Recap")

    w.open_bible_entry("character", "Vex")
    npcs = next(n for n in w.binder.to_nodes() if n.title == "NPCs")
    assert [n.title for n in npcs.children] == ["Vex"]
    w.open_bible_entry("faction", "The Black Network")
    factions = next(n for n in w.binder.to_nodes() if n.title == "Factions")
    assert [n.title for n in factions.children] == ["The Black Network"]
    dispose(w)
