"""The look of the app: colour tokens, a palette, and one app-wide stylesheet.

View → Appearance: follow the system, or always light, or always dark. Both themes
use Qt's Fusion style, so the app looks the same on macOS, Windows and Linux, and
the stylesheet below turns Fusion's defaults into calm, modern chrome: soft panel
colours, rounded selection, pill tabs, thin scrollbars, one ink-blue accent.

The text areas themselves (prose, script, board, corkboard) paint from the palette,
so they follow the theme without being styled here.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

MODES = {"system": "Follow System", "light": "Light", "dark": "Dark"}

LIGHT = {
    "window": "#f3f2ee",  # chrome: header, bars, side panels
    "sidebar": "#eeece7",
    "base": "#fdfcfa",  # the page
    "raised": "#ffffff",  # menus, inputs, cards
    "border": "#e2dfd7",
    "border_strong": "#d2cec3",
    "text": "#1f2328",
    "muted": "#6b6f76",
    "faint": "#9b9ea4",
    "icon": "#5b6067",
    "hover": "rgba(31, 35, 40, 0.06)",
    "pressed": "rgba(31, 35, 40, 0.11)",
    "accent": "#3a6db0",
    "accent_text": "#ffffff",
    "accent_soft": "rgba(58, 109, 176, 0.14)",
    "row_selected": "#dbe2ec",  # accent_soft over the sidebar, as a solid colour
    "selection": "#cddcf0",
    "scroll": "rgba(31, 35, 40, 0.22)",
}
DARK = {
    "window": "#1d1c1b",
    "sidebar": "#21201e",
    "base": "#171615",
    "raised": "#2a2927",
    "border": "#302e2b",
    "border_strong": "#403d38",
    "text": "#e8e5df",
    "muted": "#a19c93",
    "faint": "#7a756d",
    "icon": "#b3aea5",
    "hover": "rgba(255, 255, 255, 0.06)",
    "pressed": "rgba(255, 255, 255, 0.11)",
    "accent": "#86ade6",
    "accent_text": "#0f1826",
    "accent_soft": "rgba(134, 173, 230, 0.17)",
    "row_selected": "#2f3540",
    "selection": "#34465f",
    "scroll": "rgba(255, 255, 255, 0.20)",
}

_applying = False
_current = LIGHT


def mode() -> str:
    m = QSettings().value("appearance", "system", type=str)
    return m if m in MODES else "system"


def set_mode(m: str) -> None:
    QSettings().setValue("appearance", m)
    apply()


def is_dark() -> bool:
    return QApplication.instance().palette().color(QPalette.ColorRole.Base).lightness() < 128


def tokens() -> dict[str, str]:
    """The colours of the theme in use."""
    return _current


def palette(t: dict[str, str]) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t["window"],
        QPalette.ColorRole.WindowText: t["text"],
        QPalette.ColorRole.Base: t["base"],
        QPalette.ColorRole.AlternateBase: t["sidebar"],
        QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.PlaceholderText: t["faint"],
        QPalette.ColorRole.Button: t["raised"],
        QPalette.ColorRole.ButtonText: t["text"],
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: t["selection"],
        QPalette.ColorRole.HighlightedText: t["text"],
        QPalette.ColorRole.ToolTipBase: t["raised"],
        QPalette.ColorRole.ToolTipText: t["text"],
        QPalette.ColorRole.Link: t["accent"],
        QPalette.ColorRole.LinkVisited: t["accent"],
        QPalette.ColorRole.Light: t["raised"],
        QPalette.ColorRole.Midlight: t["border"],
        QPalette.ColorRole.Mid: t["border_strong"],
        QPalette.ColorRole.Dark: t["border_strong"],
        QPalette.ColorRole.Shadow: "#000000",
        QPalette.ColorRole.Accent: t["accent"],
    }
    for role, colour in roles.items():
        p.setColor(role, QColor(colour))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["faint"]))
    return p


def dark_palette() -> QPalette:
    return palette(DARK)


def stylesheet(t: dict[str, str]) -> str:
    from .icons import icon_file

    chevron_down = icon_file("chevron-down", t["muted"], 14)
    chevron_right = icon_file("chevron-right", t["muted"], 14)
    close = icon_file("close", t["faint"], 14)
    close_hover = icon_file("close", t["text"], 14)
    qss = """
QMainWindow, QDialog { background: @window; }
QToolTip { background: @raised; color: @text; border: 1px solid @border_strong; border-radius: 6px; padding: 5px 8px; }

/* menus */
QMenuBar { background: @window; border-bottom: 1px solid @border; padding: 2px 6px; }
QMenuBar::item { padding: 4px 10px; border-radius: 5px; background: transparent; }
QMenuBar::item:selected { background: @hover; }
QMenu { background: @raised; border: 1px solid @border_strong; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 6px 28px 6px 12px; border-radius: 5px; color: @text; }
QMenu::item:selected { background: @accent; color: @accent_text; }
QMenu::item:disabled { color: @faint; }
QMenu::separator { height: 1px; background: @border; margin: 5px 8px; }
QMenu::icon { padding-left: 8px; }

/* header bar */
QToolBar#HeaderBar { background: @window; border: none; border-bottom: 1px solid @border; padding: 6px 10px; spacing: 4px; }
QToolBar#HeaderBar QToolButton { color: @text; border-radius: 7px; padding: 5px 9px; }
QToolBar#HeaderBar QToolButton:hover { background: @hover; }
QToolBar#HeaderBar QToolButton:pressed, QToolBar#HeaderBar QToolButton:checked { background: @pressed; }
QToolBar#HeaderBar QToolButton::menu-indicator { image: none; width: 0; }
QToolBar#HeaderBar QToolButton#ProjectTitle { font-size: 14px; font-weight: 600; color: @text; padding: 4px 6px; }
QLabel#ProjectStatus { color: @muted; padding-left: 8px; }
QToolButton#SyncPill { border: 1px solid @border_strong; border-radius: 12px; padding: 3px 10px; color: @muted; }

/* the binder */
QWidget#BinderPanel { background: @sidebar; border-right: 1px solid @border; }
QSplitter#BinderSplit::handle { background: @sidebar; border-top: 1px solid @border; }
QSplitter#BinderSplit::handle:hover { border-top: 1px solid @border_strong; }
QListWidget#BookmarkList { background: @sidebar; border: none; padding: 0 6px 6px 4px; }
QListWidget#BookmarkList::item { padding: 3px 4px; border-radius: 6px; color: @text; }
QListWidget#BookmarkList::item:hover { background: @hover; }
QListWidget#BookmarkList::item:selected { background: @row_selected; color: @text; }
QLabel#PanelHeader { color: @muted; font-size: 11px; font-weight: 600; padding: 10px 8px 4px 14px; }
QToolButton#PanelButton { border-radius: 6px; padding: 3px; margin: 6px 6px 0 0; }
QToolButton#PanelButton:hover { background: @hover; }
QToolButton#PanelButton::menu-indicator { image: none; width: 0; }
QTreeWidget#Binder { background: @sidebar; border: none; padding: 2px 6px 8px 4px;
    selection-background-color: @row_selected; selection-color: @text; }
QTreeWidget#Binder::item { padding: 4px 4px; border-radius: 6px; color: @text; }
QTreeWidget#Binder::item:hover { background: @hover; }
QTreeWidget#Binder::item:selected { background: @row_selected; color: @text; }
QTreeView { show-decoration-selected: 0; }
QTreeView::branch { background: transparent; border-image: none; }
QTreeView::branch:selected { background: @row_selected; }
QTreeView::branch:has-children:closed { image: url(@chevron_right); }
QTreeView::branch:has-children:open { image: url(@chevron_down); }

/* side panel: its tabs are a compact switcher */
QTabWidget#SidePanel::pane { border: none; border-left: 1px solid @border; background: @sidebar; top: 0; }
QTabWidget#SidePanel QTabBar { background: @sidebar; border-left: 1px solid @border; }
QTabWidget#SidePanel QTabBar::tab { background: transparent; color: @muted; padding: 5px 7px; margin: 8px 1px 6px 1px; border-radius: 6px; border: 1px solid transparent; }
QTabWidget#SidePanel QTabBar::tab:first { margin-left: 8px; }
QTabWidget#SidePanel QTabBar::tab:selected { background: @raised; color: @text; border: 1px solid @border; }
QTabWidget#SidePanel QTabBar::tab:hover:!selected { color: @text; background: @hover; }
QTabWidget#SidePanel QTreeView, QTabWidget#SidePanel QListView, QTabWidget#SidePanel QTextBrowser {
    background: @sidebar; border: none; padding: 2px 6px; }
QTabWidget#SidePanel QTreeView::item, QTabWidget#SidePanel QListView::item { padding: 3px 4px; border-radius: 5px; }
QTabWidget#SidePanel QTreeView::item:hover, QTabWidget#SidePanel QListView::item:hover { background: @hover; }
QTabWidget#SidePanel QTreeView::item:selected, QTabWidget#SidePanel QListView::item:selected { background: @row_selected; color: @text; }
QTabWidget#SidePanel QTreeView { selection-background-color: @row_selected; selection-color: @text; }

/* tabs inside dialogs and panels (the document and side tabs have their own rules below) */
QTabWidget::pane { border: 1px solid @border; border-radius: 8px; background: @base; top: -1px; }
QTabBar::tab { background: transparent; color: @muted; padding: 6px 12px; margin: 0 3px 6px 0; border-radius: 6px; border: 1px solid transparent; }
QTabBar::tab:selected { background: @raised; color: @text; border: 1px solid @border; }
QTabBar::tab:hover:!selected { background: @hover; color: @text; }

/* document tabs */
QTabWidget#DocTabs::pane { border: none; top: 0; }
QTabWidget#DocTabs QTabBar { background: @window; }
QTabWidget#DocTabs QTabBar::tab { background: transparent; color: @muted; padding: 6px 10px 6px 14px; margin: 5px 1px 5px 1px; border-radius: 7px; border: 1px solid transparent; }
QTabWidget#DocTabs QTabBar::tab:first { margin-left: 8px; }
QTabWidget#DocTabs QTabBar::tab:selected { background: @base; color: @text; border: 1px solid @border; }
QTabWidget#DocTabs QTabBar::tab:hover:!selected { background: @hover; color: @text; }
QTabBar::close-button { image: url(@close); subcontrol-position: right; border-radius: 4px; margin: 1px; }
QTabBar::close-button:hover { image: url(@close_hover); background: @hover; }
QTabBar QToolButton { background: @window; border: none; }

/* format bar (objectName format_bar) */
QToolBar#format_bar { background: @window; border: none; border-bottom: 1px solid @border; padding: 3px 10px; spacing: 1px; }
QToolBar#format_bar QToolButton { color: @text; border-radius: 6px; padding: 3px 8px; }
QToolBar#format_bar QToolButton:hover { background: @hover; }
QToolBar#format_bar QToolButton:checked { background: @accent_soft; color: @accent; }
QToolBar#format_bar QToolButton:disabled { color: @faint; }
QToolBar::separator { width: 1px; background: @border; margin: 5px 7px; }

/* status bar */
QStatusBar { background: @window; border-top: 1px solid @border; color: @muted; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: @muted; padding: 0 6px; }

/* scroll bars: thin and quiet */
QScrollBar:vertical { background: transparent; width: 11px; margin: 2px 2px 2px 0; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 0 2px 2px 2px; }
QScrollBar::handle { background: @scroll; border-radius: 3px; }
QScrollBar::handle:vertical { min-height: 32px; margin: 0 2px; }
QScrollBar::handle:horizontal { min-width: 32px; margin: 2px 0; }
QScrollBar::handle:hover { background: @faint; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QSplitter::handle { background: transparent; }

/* controls */
QPushButton { background: @raised; color: @text; border: 1px solid @border_strong; border-radius: 7px; padding: 6px 14px; }
QPushButton:hover { border-color: @faint; }
QPushButton:pressed { background: @pressed; }
QPushButton:default, QPushButton#Primary { background: @accent; color: @accent_text; border-color: @accent; }
QPushButton:disabled { color: @faint; border-color: @border; }
QPushButton:flat { background: transparent; border: none; }
QLineEdit, QSpinBox, QComboBox, QDateEdit {
    background: @raised; color: @text; border: 1px solid @border_strong; border-radius: 7px; padding: 5px 8px;
    selection-background-color: @selection; selection-color: @text; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid @accent; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url(@chevron_down); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: @raised; border: 1px solid @border_strong; border-radius: 6px; padding: 4px;
    selection-background-color: @accent_soft; selection-color: @text; outline: 0; }
QListWidget, QTreeWidget { background: @base; border: 1px solid @border; border-radius: 8px; }
QListWidget::item, QTreeWidget::item { padding: 3px 2px; }
QListWidget::item:selected, QTreeWidget::item:selected { background: @accent_soft; color: @text; }
QListWidget#Corkboard { background: transparent; border: none; }
QTextBrowser { background: @base; border: 1px solid @border; border-radius: 8px; }

/* start screen and empty states */
QWidget#Welcome, QWidget#EmptyState { background: @window; }
QLabel#WelcomeTitle { font-size: 30px; font-weight: 700; color: @text; }
QLabel#WelcomeSubtitle, QLabel#EmptyText { color: @muted; font-size: 14px; }
QLabel#NewVersion { color: @accent; font-size: 13px; padding-top: 6px; }
QToolBar#HeaderBar QToolButton#UpdatePill { color: @accent; border: 1px solid @accent; border-radius: 12px; padding: 3px 10px; }
QLabel#SectionLabel { color: @muted; font-size: 11px; font-weight: 600; }
QPushButton#BigButton { text-align: left; padding: 0; border-radius: 10px; min-height: 52px; }
QLabel#BigButtonTitle { font-size: 14px; font-weight: 600; color: @text; }
QLabel#BigButtonDetail { color: @muted; }
QPushButton#BigButton:hover { border-color: @accent; }
QListWidget#Recent { background: transparent; border: none; }
QListWidget#Recent::item { padding: 8px 10px; border-radius: 8px; color: @text; }
QListWidget#Recent::item:hover { background: @hover; }
QListWidget#Recent::item:selected { background: @accent_soft; }
"""
    values = {**t, "chevron_down": chevron_down, "chevron_right": chevron_right, "close": close, "close_hover": close_hover}
    for key in sorted(values, key=len, reverse=True):  # "@border_strong" before "@border"
        qss = qss.replace(f"@{key}", values[key])
    return qss


def apply() -> None:
    """Style, palette and stylesheet for the chosen appearance (at startup, and when it changes)."""
    global _applying
    app = QApplication.instance()
    hints = app.styleHints()
    if not getattr(app, "_theme_watch", False):
        app._theme_watch = True
        hints.colorSchemeChanged.connect(lambda _: mode() == "system" and not _applying and apply())
    _applying = True
    try:
        _apply(app, hints)
    finally:
        _applying = False


def _apply(app, hints) -> None:
    global _current
    m = mode()
    hints.setColorScheme({"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(m, Qt.ColorScheme.Unknown))
    dark = m == "dark" or (m == "system" and hints.colorScheme() == Qt.ColorScheme.Dark)
    _current = DARK if dark else LIGHT
    app.setStyle("Fusion")  # one look everywhere; the stylesheet does the rest
    app.setPalette(palette(_current))
    app.setStyleSheet(stylesheet(_current))
    for widget in app.allWidgets():  # icons and text marks drawn in the old colours
        if hasattr(widget, "refresh_icons"):
            widget.refresh_icons()
        if hasattr(widget, "refresh_theme"):
            widget.refresh_theme()
