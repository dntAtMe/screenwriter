"""View → Appearance: follow the system, or always light, or always dark."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

MODES = {"system": "Follow System", "light": "Light", "dark": "Dark"}

_native_style: str | None = None  # the platform's own style, for light mode
_applying = False


def mode() -> str:
    m = QSettings().value("appearance", "system", type=str)
    return m if m in MODES else "system"


def set_mode(m: str) -> None:
    QSettings().setValue("appearance", m)
    apply()


def is_dark() -> bool:
    return QApplication.instance().palette().color(QPalette.ColorRole.Base).lightness() < 128


def dark_palette() -> QPalette:
    """Warm dark greys, like paper at night (the corkboard's dark cards use the same tones)."""
    p = QPalette()
    colours = {
        QPalette.ColorRole.Window: "#2b2a28",
        QPalette.ColorRole.WindowText: "#e6e2da",
        QPalette.ColorRole.Base: "#1f1e1c",
        QPalette.ColorRole.AlternateBase: "#282725",
        QPalette.ColorRole.Text: "#e6e2da",
        QPalette.ColorRole.PlaceholderText: "#8a8680",
        QPalette.ColorRole.Button: "#34322e",
        QPalette.ColorRole.ButtonText: "#e6e2da",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: "#4a6fa5",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#34322e",
        QPalette.ColorRole.ToolTipText: "#e6e2da",
        QPalette.ColorRole.Link: "#7fa7e0",
        QPalette.ColorRole.LinkVisited: "#b294d6",
        QPalette.ColorRole.Light: "#45423d",
        QPalette.ColorRole.Midlight: "#3a3834",
        QPalette.ColorRole.Mid: "#2f2d2a",
        QPalette.ColorRole.Dark: "#1a1917",
        QPalette.ColorRole.Shadow: "#0d0d0c",
    }
    for role, colour in colours.items():
        p.setColor(role, QColor(colour))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor("#77736c"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#3a3834"))
    return p


def apply() -> None:
    """Style and palette for the chosen appearance (at startup, and when it's changed)."""
    global _native_style, _applying
    app = QApplication.instance()
    hints = app.styleHints()
    if _native_style is None:
        _native_style = app.style().name()
        hints.colorSchemeChanged.connect(lambda _: mode() == "system" and not _applying and apply())
    _applying = True
    try:
        _apply(app, hints)
    finally:
        _applying = False


def _apply(app, hints) -> None:
    m = mode()
    hints.setColorScheme({"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(m, Qt.ColorScheme.Unknown))
    dark = m == "dark" or (m == "system" and hints.colorScheme() == Qt.ColorScheme.Dark)
    if dark:
        # the native Windows 10 style can't draw dark; Fusion can, everywhere
        app.setStyle("Fusion")
        app.setPalette(dark_palette())
    else:
        app.setStyle(_native_style)
        app.setPalette(app.style().standardPalette())
