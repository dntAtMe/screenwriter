"""Bundled fonts, and which ones the editors and the screenplay PDF use (a setting per profile)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase

FONT_DIR = Path(__file__).resolve().parent / "resources" / "fonts"


@dataclass(frozen=True)
class Choice:
    family: str
    note: str
    exact: bool = False  # every character 0.6 em wide, like Courier: lays out a screenplay page exactly
    bundled: bool = True


CHOICES = [
    Choice("iA Writer Duo S", "calm, mostly monospaced — wide m and w"),
    Choice("Courier Prime", "Courier made for screenwriters", exact=True),
    Choice("TeX Gyre Cursor", "light, classic typewriter", exact=True),
    Choice("Cutive Mono", "thin, uneven typewriter"),
    Choice("Special Elite", "worn, inked typewriter"),
    Choice("Sometype Mono", "soft typewriter"),
    Choice("iA Writer Mono S", "modern monospace", exact=True),
    Choice("iA Writer Quattro S", "proportional, with a typewriter feel"),
    Choice("IBM Plex Mono", "clean monospace", exact=True),
    Choice("Anonymous Pro", "narrow monospace"),
    Choice("Xanh Mono", "condensed, with serifs"),
    Choice("Georgia", "book serif (the old prose font)", bundled=False),
    Choice("Courier New", "the standard screenplay font", exact=True, bundled=False),
]

DEFAULTS = {"script": "iA Writer Duo S", "prose": "iA Writer Duo S", "script_pdf": "Courier Prime"}
FALLBACKS = {"script": ("Courier New", "Courier"), "prose": ("Georgia", "Serif"), "script_pdf": ("Courier New", "Courier")}
KINDS = tuple(DEFAULTS)

_loaded = False


def load() -> None:
    """Make the bundled fonts available to Qt (once; needs a QGuiApplication)."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    for path in sorted(FONT_DIR.glob("*.[ot]tf")):
        QFontDatabase.addApplicationFont(str(path))


def available(family: str) -> bool:
    load()
    return family in QFontDatabase.families()


def choices(kind: str) -> list[Choice]:
    """What can be picked: the screenplay PDF needs a font that keeps Courier's page layout."""
    wanted = [c for c in CHOICES if c.exact or kind != "script_pdf"]
    return [c for c in wanted if available(c.family)]


def family(kind: str) -> str:
    chosen = QSettings().value(f"fonts/{kind}", DEFAULTS[kind], type=str)
    if kind == "script_pdf" and not any(c.exact and c.family == chosen for c in CHOICES):
        chosen = DEFAULTS[kind]
    for f in (chosen, DEFAULTS[kind], *FALLBACKS[kind]):
        if available(f):
            return f
    return FALLBACKS[kind][-1]


def set_family(kind: str, name: str) -> None:
    QSettings().setValue(f"fonts/{kind}", name)


def smooth() -> bool:
    return QSettings().value("fonts/smooth", True, type=bool)


def set_smooth(on: bool) -> None:
    QSettings().setValue("fonts/smooth", on)


def styled(font: QFont) -> QFont:
    """Softer letters: no hinting (shapes as drawn, not snapped to pixels), grayscale antialiasing.
    (On Windows the FreeType engine does the rest — chosen at startup, see app.main.)"""
    if smooth():
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.NoSubpixelAntialias)
    else:
        font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferDefault)
    return font


def font(kind: str, points: float) -> QFont:
    f = QFont(family(kind))
    f.setPointSizeF(points)
    if kind != "prose":
        f.setStyleHint(QFont.StyleHint.Monospace)
    return styled(f)
