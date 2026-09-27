import json

import pytest
from conftest import dispose
from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import QMenu

from screenwriter import spelling
from screenwriter.editors.prose import ProseEditor
from screenwriter.editors.screenplay import ScreenplayEditor
from screenwriter.editors.spellmenu import add_spelling_menu


def test_dictionaries():
    speller = spelling.Speller(["pl_PL", "en_US"])
    for word in ("latarnia", "Kacprowi", "zażółć", "gęślą", "lighthouse", "Keeper's", "keeper’s"):
        assert speller.correct(word), word
    for word in ("latrania", "wrold", "lihgthouse"):
        assert not speller.correct(word), word
    assert "world" in speller.suggest("wrold")
    assert not spelling.Speller(["en_US"]).correct("latarnia")  # English only: Polish words are wrong
    assert spelling.Speller(["en_GB"]).correct("colour") and not spelling.Speller(["en_US"]).correct("colour")


def test_which_words_are_checked():
    text = "INT. JETTY - NIGHT {the hooded figure|Xardass} https://exmaple.com a b1 don't"
    words = [w for _, _, w in spelling.words_to_check(text)]
    assert "INT" not in words  # short capitals: INT, EXT, V.O.
    assert "JETTY" in words and "NIGHT" in words
    assert "hooded" in words and "Xardass" not in words  # a mark's name isn't text you wrote
    assert "exmaple" not in words and "a" not in words and "don't" in words


@pytest.fixture
def service(qapp):
    s = spelling.SpellService()
    s.set_languages(["en_US"])
    yield s
    s.stop()


def wait_for(condition, timeout=20.0):
    import time

    from PySide6.QtWidgets import QApplication

    end = time.monotonic() + timeout
    while not condition() and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)
    return condition()


def _answer(service, word):
    service.status(word)
    wait_for(lambda: service.status(word) is not None)
    return service.status(word)


def test_service_answers_in_the_background(service):
    assert _answer(service, "lighthouse") is True
    assert _answer(service, "wrold") is False
    service.set_known({"Xardas"})
    assert service.status("Xardas") is True and service.status("xardas") is True
    service.ignore("wrold")
    assert service.status("wrold") is True
    service.enabled = False
    assert service.status("zzzq") is True


def test_squiggles_and_suggestions(service, qapp):
    ed = ProseEditor()
    ed.highlighter.spell = service
    ed.set_text("The wrold was quiet.")
    _answer(service, "wrold")
    ed.highlighter.rehighlight()
    block = ed.document().firstBlock()
    styles = {r.start: r.format.underlineStyle() for r in block.layout().formats()}
    underlined = [s for s, u in styles.items() if u == QTextCharFormat.UnderlineStyle.SpellCheckUnderline]
    assert underlined == [4]  # "wrold", nothing else

    added = []
    menu = QMenu()
    add_spelling_menu(menu, ed, service, 6, added.append)
    assert wait_for(lambda: any(a.text() == "world" for a in menu.actions()))
    next(a for a in menu.actions() if a.text() == "world").trigger()
    assert ed.text() == "The world was quiet."
    ed.undo()
    assert ed.text() == "The wrold was quiet."
    menu = QMenu()
    add_spelling_menu(menu, ed, service, 6, added.append)
    next(a for a in menu.actions() if a.text().startswith("Add “wrold”")).trigger()
    assert added == ["wrold"]
    dispose(ed)

    script = ScreenplayEditor()  # scripts too, but not the title page
    script.spell = service
    script.set_text("Title: Teh Lighthouse\n\nEXT. JETTY - NIGHT\n\nTeh boat.\n")
    _answer(service, "Teh")
    script.highlighter.rehighlight()
    styles = lambda n: [r.format.underlineStyle() for r in script.document().findBlockByNumber(n).layout().formats()]
    assert QTextCharFormat.UnderlineStyle.SpellCheckUnderline not in styles(0)
    assert QTextCharFormat.UnderlineStyle.SpellCheckUnderline in styles(4)
    dispose(script)


def test_project_languages_and_dictionary(qapp, sample_project):
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.open_project(sample_project)
    assert w.project.spelling is None  # this computer's languages until chosen
    w.language_actions["pl_PL"].setChecked(True)
    w._toggle_language("pl_PL")
    w.language_actions["en_GB"].setChecked(True)
    w._toggle_language("en_GB")
    assert w.project.spelling == [c for c in ("pl_PL", "en_US", "en_GB") if c in w.project.spelling]
    assert "pl_PL" in json.loads((sample_project / "project.json").read_text(encoding="utf-8"))["spelling"]
    assert w.spell.languages == w.project.spelling

    w.add_spelling_word("Skerry")
    assert (sample_project / "dictionary.txt").read_text(encoding="utf-8") == "Skerry\n"
    assert w.spell.status("Skerry") is True
    w.binder.add("character", "Xardas Wyrm", edit=False, open_it=False)  # Story Bible names are words too
    w._refresh_bible()
    assert w.spell.status("Xardas") is True and w.spell.status("Wyrm") is True
    dispose(w)


def test_project_dictionary_merges_when_synced(tmp_path):
    from test_sync import Machine  # noqa: F401  (the two-computer helpers)
    from screenwriter.project import Project
    from screenwriter.projecthistory import ProjectHistory
    from screenwriter.sync import open_package, package_name, sync

    p = Project.create(tmp_path / "desktop" / "Story", "Story")
    desk = ProjectHistory(p.path)
    desk.save_point()
    cloud = tmp_path / "net" / package_name("Story")
    sync(desk, p.id, p.name, cloud)
    lap_path = open_package(cloud, tmp_path / "laptop")
    lap = ProjectHistory(lap_path)
    spelling.add_word(p.path, "Xardas")
    spelling.add_word(lap_path, "Skerry")
    for h, path in ((desk, p.path), (lap, lap_path), (desk, p.path)):
        h.save_point()
        sync(h, p.id, p.name, cloud)
    assert spelling.read_words(p.path) == {"Xardas", "Skerry"}
