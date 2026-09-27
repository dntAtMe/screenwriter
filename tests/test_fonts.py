from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QRawFont

from conftest import dispose
from screenwriter import fonts


def test_bundled_fonts_are_usable(qapp):
    QSettings().clear()
    families = {c.family for c in fonts.CHOICES if c.bundled}
    assert all(fonts.available(f) for f in families)
    assert fonts.family("script") == fonts.family("prose") == "iA Writer Duo S"
    assert fonts.family("script_pdf") == "Courier Prime"
    for path in fonts.FONT_DIR.glob("*-Regular.[ot]tf"):
        raw = QRawFont(str(path), 1000)
        assert all(raw.supportsCharacter(ord(c)) for c in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ„”…"), path.name


def test_exact_fonts_keep_courier_width(qapp):
    for choice in fonts.CHOICES:
        if choice.exact and choice.bundled:
            raw = QRawFont.fromFont(QFont(choice.family))
            raw.setPixelSize(1000)
            widths = {round(raw.advancesForGlyphIndexes(raw.glyphIndexesForString(c))[0].x()) for c in "imW. 0"}
            assert widths == {600}, choice.family


def test_screenplay_pdf_only_takes_an_exact_font(qapp):
    QSettings().clear()
    fonts.set_family("script_pdf", "Special Elite")  # not one width: would break the page layout
    assert fonts.family("script_pdf") == "Courier Prime"
    fonts.set_family("script_pdf", "TeX Gyre Cursor")
    assert fonts.family("script_pdf") == "TeX Gyre Cursor"
    QSettings().clear()


def test_changing_fonts_updates_open_editors(qapp, sample_project):
    from screenwriter.editors.screenplay import ScreenplayEditor
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.open_project(sample_project)
    for node_id in ("ch01", "pilot"):
        w.open_document(node_id)
    script = next(e for e in w.editors.values() if isinstance(e, ScreenplayEditor))
    prose = w.editors["ch01"]
    script.zoom(2)
    assert script.document().defaultFont().family() == "iA Writer Duo S"
    fonts.set_family("script", "Special Elite")
    fonts.set_family("prose", "Courier Prime")
    fonts.set_smooth(False)
    w.apply_fonts()
    assert script.document().defaultFont().family() == "Special Elite"
    assert script.document().defaultFont().pointSizeF() == 16  # zoom kept
    assert prose.font().family() == "Courier Prime" and prose.highlighter.base_font.family() == "Courier Prime"
    assert prose.font().hintingPreference() == QFont.HintingPreference.PreferDefaultHinting
    QSettings().clear()
    dispose(w)
