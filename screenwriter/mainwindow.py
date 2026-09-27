import html
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import REPOSITORY, __version__
from .binder import Binder
from .capture import QuickCapture, append_idea, format_idea
from .cast import CastPanel
from .corkboard import CorkboardView
from .conflictdialog import ConflictDialog
from .exportdialog import run_export
from . import merge, people
from .formatbar import FormatBar
from .liveedit import LiveEditing
from .panes import TabArea
from .updates import UpdatesPanel, arrived, recent_updates
from .quickopen import DoubleShift, QuickOpen, Target
from .shortcuthints import ShortcutHints
from .historydialog import HistoryDialog
from .projecthistory import ProjectHistory
from . import sync as cloud
from .google_drive import DriveClient, DriveError, GoogleAccount, load_client_config
from .googlesignin import sign_in_with_google
from .syncdialog import SIGN_OUT, SyncDialog
from .synctargets import GDRIVE_PREFIX, DriveTarget, FolderTarget, TargetError, target_from_key
from . import board
from .editors.board import BoardEditor
from .editors.bible import BibleEditor
from . import bible
from .outline import OutlinePanel
from .search import FindBar, SearchPanel
from .editors.prose import ProseEditor
from .editors.screenplay import ScreenplayEditor
from .editors import screenplay
from .fountain import EL_NAMES
from .project import BIBLE_KINDS, BOARD, CHARACTER, DOCUMENT_KINDS, LOCATION, FOLDER, NOTE, PROSE, SCREENPLAY, TRASH, Project, walk

APP_NAME = "Screenwriter"
MAX_RECENT = 8


class Welcome(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 32px; font-weight: 600;")
        subtitle = QLabel("Screenplays, books, notes and ideas.")
        subtitle.setStyleSheet("color: gray;")
        new_btn = QPushButton("New Project…")
        open_btn = QPushButton("Open Project…")
        file_btn = QPushButton("Open Project File…")
        file_btn.setToolTip("Open a .screenwriter file — a project synced through a cloud folder, or a copy someone sent you")
        new_btn.clicked.connect(window.new_project)
        open_btn.clicked.connect(window.open_project_dialog)
        file_btn.clicked.connect(window.open_project_file)
        self.recent = QListWidget()
        self.recent.setMaximumHeight(180)
        self.recent.itemActivated.connect(lambda item: window.open_project(Path(item.text())))

        buttons = QHBoxLayout()
        buttons.addWidget(new_btn)
        buttons.addWidget(open_btn)
        buttons.addWidget(file_btn)
        column = QVBoxLayout()
        column.addStretch()
        column.addWidget(title)
        column.addWidget(subtitle)
        column.addSpacing(16)
        column.addLayout(buttons)
        column.addSpacing(16)
        column.addWidget(QLabel("Recent projects"))
        column.addWidget(self.recent)
        column.addStretch()
        outer = QHBoxLayout(self)
        outer.addStretch()
        outer.addLayout(column)
        outer.addStretch()

    def set_recent(self, paths: list[str]) -> None:
        self.recent.clear()
        self.recent.addItems(paths)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.project: Project | None = None
        self.editors: dict[str, ProseEditor | ScreenplayEditor] = {}

        self.binder = Binder()
        self.binder.openRequested.connect(self.open_document)
        self.binder.structureChanged.connect(self._save_structure)
        self.binder.renamed.connect(self._on_renamed)
        self.binder.deletedPermanently.connect(self._on_deleted)
        self.binder.corkboardRequested.connect(self.open_corkboard)

        self.tabs = TabArea()  # one tab pane, or two when the view is split
        self.tab_history: list[str] = []  # node ids, most recently viewed first
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.find_bar = FindBar(self._current_text_editor)
        self.format_bar = FormatBar()
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self.format_bar)
        self.presence_banner = QLabel()
        self.presence_banner.setWordWrap(True)
        self.presence_banner.setStyleSheet(
            "background: rgba(240, 179, 90, 0.18); border-left: 3px solid #f0b35a; padding: 6px 12px;")
        self.presence_banner.hide()
        center_layout.addWidget(self.presence_banner)
        center_layout.addWidget(self.tabs, 1)  # the page takes the room; the bars above stay their own size
        center_layout.addWidget(self.find_bar)

        # Right-hand side panel: document outline and project search.
        self.outline = OutlinePanel()
        self.outline.jumpRequested.connect(self._jump_to_line)
        self.search = SearchPanel(self._searchable_documents)
        self.search.openRequested.connect(self.open_at)
        self.side = QTabWidget()
        self.side.setDocumentMode(True)
        self.side.addTab(self.outline, "Outline")
        self.side.addTab(self.search, "Search")
        self.cast = CastPanel(self.binder.icons)
        self.cast.openRequested.connect(self.open_document)
        self.side.addTab(self.cast, "Cast")
        self.updates = UpdatesPanel()
        self.updates.openRequested.connect(self.open_document)
        self.updates.historyRequested.connect(lambda path: self.show_history(path))
        self.side.addTab(self.updates, "Updates")
        self.side.currentChanged.connect(lambda _: self._refresh_updates())
        self.bible_index = bible.BibleIndex()
        self.bible_timer = QTimer(self, singleShot=True, interval=600)
        self.bible_timer.timeout.connect(self._refresh_bible)
        self.binder.structureChanged.connect(self.bible_timer.start)
        self.outline_timer = QTimer(self, singleShot=True, interval=300)
        self.outline_timer.timeout.connect(self._refresh_outline)

        self.splitter = QSplitter()
        self.splitter.addWidget(self.binder)
        self.splitter.addWidget(center)
        self.splitter.addWidget(self.side)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([240, 900, 280])

        self.welcome = Welcome(self)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.splitter)
        self.setCentralWidget(self.stack)

        self.sync_label = QLabel()
        self.sync_label.setStyleSheet("color: gray;")
        self.conflicts_button = QPushButton()
        self.conflicts_button.setFlat(True)
        self.conflicts_button.setStyleSheet("color: #b5563c; font-weight: 600;")
        self.conflicts_button.setToolTip("Paragraphs two people changed differently — choose what to keep")
        self.conflicts_button.clicked.connect(self.review_conflicts)
        self.conflicts_button.hide()
        self.statusBar().addPermanentWidget(self.conflicts_button)
        self.people_label = QLabel()
        self.statusBar().addPermanentWidget(self.people_label)
        self.statusBar().addPermanentWidget(self.sync_label)
        self.stats_label = QLabel()
        self.element_label = QLabel()
        self.element_label.setStyleSheet("color: gray;")
        self.statusBar().addPermanentWidget(self.element_label)
        self.statusBar().addPermanentWidget(self.stats_label)

        # Project history: an automatic save point every few minutes of changes, and on close.
        self.history: ProjectHistory | None = None
        self.history_timer = QTimer(self, interval=5 * 60 * 1000)
        self.history_timer.timeout.connect(self._periodic_save_point)

        # Cloud sync: the package file this project syncs with (per computer, in settings).
        self.sync_target = None  # FolderTarget | DriveTarget
        self.google_config = load_client_config()
        self.google_account = GoogleAccount.restore(self.google_config) if self.google_config else None
        self.sync_timer = QTimer(self, interval=60 * 1000)
        self.sync_timer.timeout.connect(self._check_cloud)

        # Presence: who else has the project open, and where (see people.py).
        self.session = people.new_session()
        self.others: list[people.Presence] = []
        self.presence_timer = QTimer(self, interval=30 * 1000)
        self.presence_timer.timeout.connect(self._check_people)
        self.announce_timer = QTimer(self, singleShot=True, interval=1500)  # after switching tabs
        self.announce_timer.timeout.connect(self._check_people)
        # While others are in the project too: sync shortly after typing stops, and look for
        # their changes more often, so everyone's copy stays close and clashes stay rare.
        self.quick_sync_timer = QTimer(self, singleShot=True, interval=10 * 1000)
        self.quick_sync_timer.timeout.connect(lambda: self.sync_now(quiet=True))

        # Autosave: shortly after typing stops, and always on tab switch / close.
        self.save_timer = QTimer(self, singleShot=True, interval=1500)
        self.save_timer.timeout.connect(self.save_all)

        self._build_menus()
        self._update_format_bar()
        self.shortcut_hints = ShortcutHints(self)
        self.double_shift = DoubleShift(self)
        self.live = LiveEditing(self)
        self.live.enabled = self.live_action.isChecked()
        self.double_shift.triggered.connect(self.quick_open)
        self.shortcut_hints.set_enabled(self.hints_action.isChecked())
        self._set_project_actions_enabled(False)
        self.welcome.set_recent(self._recent())
        self.setWindowTitle(self._app_title())
        self.resize(1280, 820)
        if geometry := self.settings.value("geometry"):
            self.restoreGeometry(geometry)
        if splitter := self.settings.value("splitter"):
            self.splitter.restoreState(splitter)

    # --- menus ------------------------------------------------------------------

    def _action(self, menu, text, slot, shortcut=None) -> QAction:
        action = menu.addAction(text)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file = bar.addMenu("&File")
        self._action(file, "New Project…", self.new_project, "Ctrl+Shift+N")
        self._action(file, "Open Project…", self.open_project_dialog, "Ctrl+O")
        self._action(file, "Open Project File…", self.open_project_file)
        self._action(file, "Open from Google Drive…", self.open_from_google_drive)
        self._action(file, "Your Name…", self.set_your_name)
        file.addSeparator()
        self.project_actions = [
            self._action(file, "Save", self.save_all, QKeySequence.StandardKey.Save),
            self._action(file, "Export…", self.export_current, "Ctrl+E"),
            self._action(file, "Save Version…", self.save_version, "Ctrl+Alt+S"),
            self._action(file, "History…", self.show_history, "Ctrl+Alt+H"),
            self._action(file, "Sync & Backup…", self.show_sync_settings),
            self._action(file, "Review Conflicts…", self.review_conflicts),
            self._action(file, "Share a Copy…", self.share_copy),
            self._action(file, "Close Tab", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W"),
            self._action(file, "Close Project", self._close_project_from_menu),
        ]

        edit = bar.addMenu("&Edit")
        self.project_actions += [
            self._action(edit, "Undo", lambda: self._current_call("undo"), QKeySequence.StandardKey.Undo),
            self._action(edit, "Redo", lambda: self._current_call("redo"), QKeySequence.StandardKey.Redo),
        ]
        edit.addSeparator()
        self.project_actions += [
            self._action(edit, "Find…", self.find_bar.open_bar, QKeySequence.StandardKey.Find),
            self._action(edit, "Find Next", self.find_bar.find, QKeySequence.StandardKey.FindNext),
            self._action(edit, "Find Previous", lambda: self.find_bar.find(backward=True), QKeySequence.StandardKey.FindPrevious),
            self._action(edit, "Search Project…", self.show_search, "Ctrl+Shift+F"),
        ]

        insert = bar.addMenu("&Insert")
        for kind, label, shortcut in (
            (PROSE, "New Prose Document", "Ctrl+N"),
            (SCREENPLAY, "New Screenplay", "Ctrl+Alt+N"),
            (NOTE, "New Note", "Ctrl+Shift+J"),
            (BOARD, "New Board", "Ctrl+Alt+B"),
            (CHARACTER, "New Character", "Ctrl+Alt+C"),
            (LOCATION, "New Location", "Ctrl+Alt+L"),
            (FOLDER, "New Folder", "Ctrl+Shift+G"),
        ):
            self.project_actions.append(self._action(insert, label, lambda _=False, k=kind: self.binder.add(k), shortcut))
        insert.addSeparator()
        self.project_actions.append(self._action(insert, "Capture Idea…", self.capture_idea, "Ctrl+Shift+I"))

        fmt = bar.addMenu("F&ormat")
        self.element_actions = []
        for i, el in enumerate(screenplay.SETTABLE, start=1):
            action = self._action(fmt, EL_NAMES[el], lambda _=False, e=el: self._set_element(e), f"Ctrl+{i}")
            self.element_actions.append(action)

        view = bar.addMenu("&View")
        self.project_actions += [
            self._action(view, "Toggle Binder", self.toggle_binder, "Ctrl+\\"),
            self._action(view, "Toggle Side Panel", self.toggle_side, "Ctrl+Alt+\\"),
            self._action(view, "Outline", self.show_outline, "Ctrl+Shift+O"),
            self._action(view, "Corkboard", self.open_selected_corkboard, "Ctrl+Alt+K"),
            self._action(view, "Focus Mode", self.toggle_focus, "Ctrl+Shift+D"),
        ]
        view.addSeparator()
        self.project_actions.append(self._action(view, "Go to Document…", self.quick_open, "Ctrl+P"))
        next_tab = self._action(view, "Next Tab", lambda: self.tabs.next_tab(1))
        next_tab.setShortcuts([QKeySequence("Ctrl+Tab"), QKeySequence("Ctrl+PgDown")])
        prev_tab = self._action(view, "Previous Tab", lambda: self.tabs.next_tab(-1))
        prev_tab.setShortcuts([QKeySequence("Ctrl+Shift+Tab"), QKeySequence("Ctrl+PgUp")])
        go_to = view.addMenu("Go to Tab")
        tab_actions = [next_tab, prev_tab]
        for n in range(1, 10):
            tab_actions.append(self._action(go_to, "Last Tab" if n == 9 else f"Tab {n}", lambda _=False, n=n: self.tabs.go_to_tab(n), f"Alt+{n}"))
        view.addSeparator()
        split = [
            self._action(view, "Split Right", lambda: self.split(Qt.Orientation.Horizontal), "Ctrl+Alt+R"),
            self._action(view, "Split Down", lambda: self.split(Qt.Orientation.Vertical), "Ctrl+Alt+D"),
            self._action(view, "Move Tab to Other Side", self.tabs.move_to_other_pane, "Ctrl+Alt+M"),
            self._action(view, "Focus Other Side", self.tabs.focus_other_pane, "F6"),
            self._action(view, "Unsplit", self.tabs.unsplit, "Ctrl+Alt+W"),
        ]
        self.project_actions += tab_actions + split
        view.addSeparator()
        self.live_action = self._action(view, "Live Editing (see others type)", self._toggle_live)
        self.live_action.setCheckable(True)
        self.live_action.setChecked(self.settings.value("live_editing", True, type=bool))
        self.toolbar_action = self._action(view, "Formatting Toolbar", self._toggle_format_bar)
        self.toolbar_action.setCheckable(True)
        self.toolbar_action.setChecked(self.settings.value("format_bar", True, type=bool))
        self.hints_action = self._action(view, "Shortcut Hints (hold Ctrl or Alt)", self._toggle_shortcut_hints)
        self.hints_action.setCheckable(True)
        self.hints_action.setChecked(self.settings.value("shortcut_hints", True, type=bool))
        self._action(view, "Full Screen", self.toggle_fullscreen, "Ctrl+Meta+F")
        view.addSeparator()
        self.project_actions += [
            self._action(view, "Zoom In", lambda: self._zoom(1), QKeySequence.StandardKey.ZoomIn),
            self._action(view, "Zoom Out", lambda: self._zoom(-1), QKeySequence.StandardKey.ZoomOut),
        ]

        help_menu = bar.addMenu("&Help")
        self._action(help_menu, "Screenplay Keys", self.show_screenplay_help)
        self._action(help_menu, "Board Keys", self.show_board_help)
        help_menu.addSeparator()
        self._action(help_menu, "User Guide", lambda: QDesktopServices.openUrl(QUrl(f"{REPOSITORY}/blob/main/docs/user-guide.md")))
        self._action(help_menu, "Report a Problem…", lambda: QDesktopServices.openUrl(QUrl(f"{REPOSITORY}/issues")))
        about = self._action(help_menu, f"About {APP_NAME}", self.show_about)
        about.setMenuRole(QAction.MenuRole.AboutRole)  # lands in the app menu on macOS

    def _set_project_actions_enabled(self, enabled: bool) -> None:
        for action in self.project_actions:
            action.setEnabled(enabled)
        self._update_element_actions()

    def _update_element_actions(self) -> None:
        is_script = isinstance(self.tabs.currentWidget(), ScreenplayEditor)
        for action in self.element_actions:
            action.setEnabled(is_script)

    def _current_call(self, method: str) -> None:
        if editor := self.tabs.currentWidget():
            getattr(editor, method)()

    def _set_element(self, el) -> None:
        editor = self.tabs.currentWidget()
        if isinstance(editor, ScreenplayEditor):
            editor.set_element(el)
            self.format_bar.sync_element()

    # --- projects ---------------------------------------------------------------

    def new_project(self) -> None:
        name, ok = QInputDialog.getText(self, "New Project", "Project name:")
        if not ok or not name.strip():
            return
        parent = QFileDialog.getExistingDirectory(self, "Where should the project folder go?", str(Path.home() / "Documents"))
        if not parent:
            return
        path = Path(parent) / name.strip()
        if path.exists():
            QMessageBox.warning(self, "New Project", f"{path} already exists.")
            return
        self._activate(Project.create(path, name.strip()))

    def open_project_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Project Folder", str(Path.home() / "Documents"))
        if folder:
            self.open_project(Path(folder))

    def open_project(self, path: Path) -> None:
        if not Project.is_project(path):
            QMessageBox.warning(self, "Open Project", f"{path} is not a {APP_NAME} project (no project.json).")
            return
        self._activate(Project.open(path))

    def _activate(self, project: Project) -> None:
        self.close_project()
        self.project = project
        self.binder.load(project)
        self.history = ProjectHistory(project.path)
        self.history.person = self.person_name()
        self.session = people.new_session()
        self.history.save_point()  # whatever changed outside the app since last time
        self.history_timer.start()
        key = self.settings.value(f"sync/{project.id}")
        self.sync_target = self._make_target(key) if key else None
        self.stack.setCurrentWidget(self.splitter)
        self._set_project_actions_enabled(True)
        self.setWindowTitle(f"{project.name} — {self._app_title()}")
        self._remember(project.path)
        self._refresh_bible()
        self._update_conflicts_button()
        self.binder.set_unread(set(self.settings.value(f"unread/{project.id}", []) or []))
        self._refresh_updates()
        if self.sync_target:
            self._start_sync()
        for node_id in self.settings.value(f"open_tabs/{project.path}", []) or []:
            if project.find(node_id):
                self.open_document(node_id)

    def close_project(self) -> None:
        if self.project is None:
            return
        self.save_point()
        self.history_timer.stop()
        self.sync_timer.stop()
        if self.sync_target:
            self.live.leave()
            self.sync_now(quiet=True, reload=False)
            try:
                self.sync_target.leave(self.session)
            except (DriveError, TargetError, OSError):
                pass
        self.presence_timer.stop()
        self.quick_sync_timer.stop()
        self._clear_people()
        self.sync_target = None
        self.sync_label.clear()
        self.conflicts_button.hide()
        self.binder.set_unread(set())
        self.updates.set_updates([], self.person_name(), None)
        self.side.setTabText(self.side.indexOf(self.updates), "Updates")
        self.history.pack()
        self.history.close()
        self.history = None
        self.settings.setValue(f"open_tabs/{self.project.path}", self._open_tab_ids())
        while self.tabs.count():
            self._remove_tab(0)
        self.project = None
        self.binder.clear()
        self.stack.setCurrentWidget(self.welcome)
        self.welcome.set_recent(self._recent())
        self._set_project_actions_enabled(False)
        self.setWindowTitle(self._app_title())

    def _close_project_from_menu(self) -> None:
        self.settings.remove("last_project")  # don't reopen it on next launch
        self.close_project()

    def _recent(self) -> list[str]:
        return [p for p in (self.settings.value("recent", []) or []) if Project.is_project(Path(p))]

    def _remember(self, path: Path) -> None:
        recent = [str(path)] + [p for p in self._recent() if p != str(path)]
        self.settings.setValue("recent", recent[:MAX_RECENT])
        self.settings.setValue("last_project", str(path))

    def _save_structure(self) -> None:
        if self.project:
            self.project.root = self.binder.to_nodes()
            self.project.save()

    # --- documents --------------------------------------------------------------

    def open_document(self, node_id: str) -> None:
        if node_id in self.editors:
            self.tabs.setCurrentWidget(self.editors[node_id])
            return
        node = self.project.find(node_id)
        if node is None:
            return
        if node.kind == FOLDER:
            return self.open_corkboard(node_id)
        if node.kind == SCREENPLAY:
            editor = ScreenplayEditor()
            editor.bible_names = self._bible_names
            editor.bible_lookup = self._find_bible_entry
            editor.bible_index = self.bible_index
            editor.bibleRequested.connect(self.open_bible_entry)
            self._connect_bible_menu(editor)
        elif node.kind in BIBLE_KINDS:
            editor = BibleEditor(node.kind, self._scan_documents)
            editor.nameChanged.connect(lambda name, i=node_id: self._rename_from_editor(i, name))
            editor.openRequested.connect(self.open_at)
            editor.textChanged.connect(self.bible_timer.start)
            editor.notes.set_bible(self.bible_index)
            editor.notes.bibleOpenRequested.connect(self.open_document)
            self._connect_bible_menu(editor.notes)
        elif node.kind == BOARD:
            editor = BoardEditor(self._node_title)
            editor.openRequested.connect(self.open_document)
        else:
            editor = ProseEditor()
            editor.set_bible(self.bible_index)
            editor.bibleOpenRequested.connect(self.open_document)
            self._connect_bible_menu(editor)
        editor.node_id = node_id
        editor.set_text(self.project.read_text(node))
        editor.textChanged.connect(self.save_timer.start)
        editor.textChanged.connect(self._typed)
        editor.statsChanged.connect(lambda e=editor: self._update_stats(e))
        editor.textChanged.connect(lambda e=editor: self._schedule_outline(e))
        editor.cursorPositionChanged.connect(lambda e=editor: self._on_cursor_moved(e))
        if isinstance(editor, ScreenplayEditor):
            editor.elementChanged.connect(lambda name, e=editor: self._update_element(e, name))
        self.editors[node_id] = editor
        index = self.tabs.addTab(editor, node.title)  # no icon: the macOS style elides titles of tabs with icons
        self.tabs.setCurrentIndex(index)
        editor.setFocus()

    def save_all(self) -> None:
        if self.project is None:
            return
        for node_id, editor in self.editors.items():
            if editor.is_modified():
                node = self.project.find(node_id)
                if node:
                    self.project.write_text(node, editor.text())
                editor.mark_saved()

    # --- history ------------------------------------------------------------------

    def _current_node(self):
        """The document in the current tab (not a corkboard's folder)."""
        editor = self.tabs.currentWidget()
        node = self.project.find(editor.node_id) if editor and self.project else None
        return node if node is not None and node.is_document else None

    def _history_path(self, node) -> str:
        return f"docs/{self.project.doc_path(node).name}"

    @staticmethod
    def _node_id_for(path: str) -> str:
        return Path(path).name.split(".")[0]

    def save_point(self, name: str = ""):
        """Record the whole project in its history (no-op when unchanged, unless named)."""
        if self.project is None or self.history is None:
            return None
        self.save_all()
        self._save_structure()
        return self.history.save_point(name)

    def save_version(self, name: str | None = None) -> None:
        if self.project is None:
            return
        if name is None:
            name, ok = QInputDialog.getText(self, "Save Version", "Name this version (e.g. “Before Act 2 rewrite”):")
            if not ok or not name.strip():
                return
        self.save_point(name.strip())
        self.statusBar().showMessage(f"Saved version “{name.strip()}”", 3000)

    def _current_text_for(self, path: str) -> str | None:
        node = self.project.find(self._node_id_for(path)) if self.project else None
        return self._text_of(node) if node is not None and node.is_document else None

    @staticmethod
    def _readable(path: str, text: str) -> str:
        return board.search_text(text) if path.endswith(".board.json") else text

    def show_history(self, path: str | None = None) -> None:
        if self.project is None:
            return
        self.save_point()
        node = self.project.find(self._node_id_for(path)) if path else self._current_node()
        HistoryDialog(
            self.history,
            current_text=self._current_text_for,
            readable=self._readable,
            restore_document=self.restore_document_version,
            restore_project=self.restore_project_version,
            save_version=lambda name: self.save_version(name),
            focus_path=self._history_path(node) if node else None,
            focus_title=node.title if node else "",
            parent=self,
        ).exec()

    def restore_document_version(self, point_id: str, path: str) -> None:
        """Put one document back as it was at a save point (bringing it back if deleted)."""
        point = self.history.get(point_id)
        source = point_id
        data = self.history.file_at(point_id, path)
        if data is None and point.parents:  # deleted in that save point: the version just before
            source = point.parents[0]
            data = self.history.file_at(source, path)
        if data is None:
            return
        node_id = self._node_id_for(path)
        title = self.history.titles_at(source).get(path, (node_id, ""))[0]
        self.save_point(f"Before restoring “{title}”")
        text = data.decode("utf-8", "replace")
        node = self.project.find(node_id)
        if node is None:
            old, parent_id = self.history.node_at(source, node_id)
            if old is None:
                return
            old.children = []
            self.binder.insert_node(old, self.binder.find_item(parent_id) if parent_id else None)
            self._save_structure()
            node = self.project.find(node_id)
            self.project.write_text(node, text)
        elif editor := self.editors.get(node_id):
            editor.replace_all(text)  # undoable
            self.save_all()
        else:
            self.project.write_text(node, text)
        self.open_document(node_id)
        self._refresh_bible()
        self.statusBar().showMessage(f"Restored “{title}” from {point.time:%d %b %H:%M}", 4000)

    def restore_project_version(self, point_id: str) -> None:
        """Put the whole project back as it was at a save point."""
        self.save_point("Before restoring the whole project")
        tabs = self._open_tab_ids()
        while self.tabs.count():
            self._remove_tab(0)
        self.history.restore_files(point_id)
        self.project = Project.open(self.project.path)
        self.binder.load(self.project)
        self._refresh_bible()
        for node_id in tabs:
            if self.project.find(node_id):
                self.open_document(node_id)
        self.statusBar().showMessage(f"Restored the project to {self.history.get(point_id).time:%d %b %H:%M}", 4000)

    # --- sync & sharing ----------------------------------------------------------------

    def _periodic_save_point(self) -> None:
        if self.save_point() is not None and self.sync_target:
            self.sync_now(quiet=True)

    def _drive_client(self):
        return DriveClient(self.google_account) if self.google_account else None

    def _drive_cache(self) -> Path:
        return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / "google-drive"

    def _make_target(self, key: str):
        return target_from_key(key, self.project.id, self._drive_client(), self._drive_cache())

    def _set_target(self, target) -> None:
        self.sync_target = target
        self.settings.setValue(f"sync/{self.project.id}", target.key)
        self.settings.setValue(f"sync_local/{self.project.id}", str(self.project.path))

    def _start_sync(self) -> None:
        """On opening a synced project: bring it up to date and see who else is here."""
        self.sync_timer.start()
        if not self.sync_target.available():
            self.sync_label.setText("☁ Not syncing")
            self.sync_label.setToolTip(self.sync_target.unavailable_reason())
            return
        self.presence_timer.start()
        if self.sync_now(quiet=True) is not None and self.others:
            names = ", ".join(p.label(self.person_name()) for p in self.others)
            self.statusBar().showMessage(f"Also working on this project: {names}", 8000)

    def _check_cloud(self) -> None:
        """Every minute: pull if the cloud copy changed."""
        if not self.project or not self.sync_target or not self.sync_target.available():
            return
        try:
            changed = self.sync_target.changed()
        except (DriveError, TargetError, OSError) as e:
            self._sync_failed(e, quiet=True)
            return
        if changed:
            self.sync_now(quiet=True)

    def _sync_failed(self, error: Exception, quiet: bool) -> None:
        self.sync_label.setText("☁ Sync problem" if not isinstance(error, DriveError) else "☁ Can't reach Google Drive")
        self.sync_label.setToolTip(str(error))
        if not quiet:
            QMessageBox.warning(self, "Sync", str(error))

    def sync_now(self, quiet: bool = False, reload: bool = True):
        """Sync with the cloud copy; returns the SyncResult (or None)."""
        if not self.project or not self.sync_target:
            return None
        target = self.sync_target
        if not target.available():
            self.sync_label.setText("☁ Not syncing")
            self.sync_label.setToolTip(target.unavailable_reason())
            if not quiet:
                QMessageBox.warning(self, "Sync", target.unavailable_reason())
            return None
        self.save_point()
        before = self.history.head()
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        try:
            with target.exclusive(self.session):
                package = target.prepare(self.project)
                absorbed = []
                for copy in target.strays():  # a cloud app's "conflicted copy" of the project file
                    if (extra := cloud.absorb(self.history, self.project.id, copy)) is not None:
                        absorbed.append(extra)
                        target.retire(copy)
                result = cloud.sync(self.history, self.project.id, self.project.name, package)
                target.finish(result, self.project)
            for extra in absorbed:
                result.changed = sorted(set(result.changed) | set(extra.changed))
                result.conflicts += extra.conflicts
                if extra.changed and result.status in ("uploaded", "up-to-date"):
                    result.status, result.machine = "merged", extra.machine
        except (cloud.SyncError, DriveError, TargetError, OSError) as e:
            self._sync_failed(e, quiet)
            return None
        finally:
            QApplication.restoreOverrideCursor()
        if self.settings.value(f"sync/{self.project.id}") != target.key:
            self.settings.setValue(f"sync/{self.project.id}", target.key)  # Drive file id known now
        if reload and result.changed:
            self._reload_after_sync(result.changed)
        self.sync_label.setText(f"☁ Synced {datetime.now():%H:%M}")
        self.sync_label.setToolTip(target.describe())
        self._check_people()
        if result.status in ("downloaded", "merged"):
            self._note_incoming(result, arrived(self.history, before) or [result.machine])
        self._update_conflicts_button()
        if any(not c.copy_path for c in result.conflicts):
            self.statusBar().showMessage(
                f"{result.machine} changed the same paragraphs as you — review the conflicts", 8000)
            if not quiet:
                self.review_conflicts()
        if copies := [c for c in result.conflicts if c.copy_path]:
            names = "\n".join(f"• {c.title}" for c in copies)
            QMessageBox.information(
                self, "Changed on both computers",
                f"These were changed here and on {result.machine} since the last sync:\n\n{names}\n\n"
                f"Both versions are kept — {result.machine}'s is right below yours, marked “(from {result.machine})”. "
                "Copy what you need and delete the one you don't want.",
            )
        return result

    def _reload_after_sync(self, changed: list[str]) -> None:
        """Show what sync changed on disk: the binder, and any open documents."""
        if "project.json" in changed:
            self.project = Project.open(self.project.path)
            self.binder.load(self.project)
            for node_id in self._open_tab_ids():
                node = self.project.find(node_id)
                editor = self.editors[node_id]
                if node is None:
                    self._remove_tab(self.tabs.indexOf(editor))
                else:
                    self.tabs.setTabText(self.tabs.indexOf(editor), self._tab_title(editor, node.title))
            self.binder.structureChanged.emit()  # corkboards follow
        for path in changed:
            node = self.project.find(self._node_id_for(path))
            editor = self.editors.get(node.id) if node else None
            if isinstance(editor, (ProseEditor, ScreenplayEditor)):
                editor.apply_remote_text(self.project.read_text(node))  # keeps your cursor and scroll
                editor.mark_saved()
            elif editor is not None and not isinstance(editor, CorkboardView):
                editor.set_text(self.project.read_text(node))
        self._refresh_bible()
        self._refresh_outline()

    @staticmethod
    def _app_title() -> str:
        """"Screenwriter", or "Screenwriter (Anna)" for a second copy run with SCREENWRITER_PROFILE."""
        name = QApplication.applicationName()
        return name if name.startswith(APP_NAME) else APP_NAME

    # --- people ---------------------------------------------------------------------------

    def person_name(self) -> str:
        return self.settings.value("person/name", "") or people.default_name()

    def set_your_name(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Your Name",
            "Your name, shown to the people you share projects with\n(on your changes, and next to what you're working on):",
            text=self.person_name())
        if ok and name.strip():
            self.settings.setValue("person/name", name.strip())
            if self.history:
                self.history.person = name.strip()
            self._check_people()

    def _presence_here(self) -> people.Presence:
        editor = self.tabs.currentWidget()
        node = self.project.find(editor.node_id) if editor is not None and self.project else None
        return people.Presence(self.session, self.person_name(), self.history.machine,
                               node.id if node else "", node.title if node else "")

    def _check_people(self) -> None:
        """Tell the others where we are, and see where they are."""
        target = self.sync_target
        if not self.project or not target or not target.available():
            return self._clear_people()
        try:
            target.announce(self._presence_here())
            self.others = target.others(self.session)
        except (DriveError, TargetError, OSError):
            return
        self._show_people()

    def _typed(self) -> None:
        if self.sync_target and self.others:
            self.quick_sync_timer.start()

    def _clear_people(self) -> None:
        self.others = []
        self._show_people()

    def _show_people(self) -> None:
        me = self.person_name()
        dot = lambda p: f'<span style="color:{people.colour_for(p.person)}">●</span>'
        self.people_label.setText("  ".join(f"{dot(p)} {html.escape(p.label(me))}" for p in self.others))
        self.people_label.setToolTip("\n".join(
            f"{p.label(me)} — {p.doc_title or 'no document open'}" for p in self.others))
        where: dict[str, list[tuple[str, str]]] = {}
        for p in self.others:
            if p.doc_id:
                where.setdefault(p.doc_id, []).append((p.person, people.colour_for(p.person)))
        self.binder.set_presence(where)
        self._update_banner()
        interval = (15 if self.others else 60) * 1000
        if self.sync_timer.interval() != interval:
            self.sync_timer.setInterval(interval)

    def _update_banner(self) -> None:
        """Say so when someone else has the document in front of you open too."""
        editor = self.tabs.currentWidget()
        node_id = getattr(editor, "node_id", None)
        here = [p for p in self.others if node_id and p.doc_id == node_id]
        if not here:
            self.presence_banner.hide()
            return
        me = self.person_name()
        names = " and ".join(f'<b style="color:{people.colour_for(p.person)}">{html.escape(p.label(me))}</b>' for p in here)
        verb = "has" if len(here) == 1 else "have"
        if self.live.active() and isinstance(editor, (ProseEditor, ScreenplayEditor)):
            how = ("You'll see their typing as it happens; if you both change the same words at once, "
                   "you'll choose which version to keep.")
        else:
            how = ("Edits to different paragraphs merge when you sync; "
                   "if you both change the same words, you'll choose which version to keep.")
        self.presence_banner.setText(f"{names} {verb} this open too. {how}")
        self.presence_banner.show()

    # --- updates ----------------------------------------------------------------------------

    def _set_unread(self, ids: set[str]) -> None:
        self.binder.set_unread(ids)
        if self.project:
            self.settings.setValue(f"unread/{self.project.id}", sorted(ids))

    def _note_incoming(self, result, who: list[str]) -> None:
        """After a sync brought in someone's changes: say what, and mark those documents unread."""
        ids = {self._node_id_for(p) for p in result.changed if p.startswith("docs/")}
        nodes = [n for n in (self.project.find(i) for i in ids) if n is not None]
        current = getattr(self.tabs.currentWidget(), "node_id", None)
        self._set_unread(self.binder.unread | {n.id for n in nodes if n.id != current})
        and_list = lambda items: ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else "".join(items)
        titles = [n.title for n in nodes]
        what = and_list(titles[:3] + ([f"{len(titles) - 3} more"] if len(titles) > 3 else []))
        names = and_list(who)
        self.statusBar().showMessage(f"{names} changed {what}" if titles else f"Brought in changes from {names}", 8000)
        self._refresh_updates()

    def _refresh_updates(self) -> None:
        """Fill the Updates tab; looking at it counts as having seen them."""
        if self.project is None or self.history is None:
            return
        key = f"updates_seen/{self.project.id}"
        seen = self.settings.value(key)
        seen_time = datetime.fromisoformat(seen) if seen else None
        new = self.updates.set_updates(recent_updates(self.history, self.person_name(), self.history.machine),
                                       self.person_name(), seen_time)
        index = self.side.indexOf(self.updates)
        if self.side.currentWidget() is self.updates and not self.side.isHidden():
            self.settings.setValue(key, datetime.now().astimezone().isoformat(timespec="seconds"))
            self.side.setTabText(index, "Updates")
        else:
            self.side.setTabText(index, f"Updates ({new})" if new else "Updates")

    # --- conflicts ----------------------------------------------------------------------

    def _update_conflicts_button(self) -> None:
        count = len(merge.load_conflicts(self.project.path)) if self.project else 0
        self.conflicts_button.setText(f"⚠ {count} conflict{'s' if count != 1 else ''} to review")
        self.conflicts_button.setVisible(count > 0)

    def _conflict_title(self, record) -> str:
        node = self.project.find(self._node_id_for(record.path)) if self.project else None
        return node.title if node else record.path

    def review_conflicts(self) -> None:
        if self.project is None:
            return
        records = merge.load_conflicts(self.project.path)
        if not records:
            QMessageBox.information(self, "Review Conflicts", "Nothing to review — no one's changes clashed.")
            return
        ConflictDialog(records, self._conflict_title, self.resolve_conflict, self).exec()
        self._update_conflicts_button()

    def resolve_conflict(self, record, choice: str) -> bool:
        """Apply a choice to the document (undoably, if it's open) and forget the conflict."""
        node = self.project.find(self._node_id_for(record.path))
        if node is not None:
            text = self._text_of(node)
            new = merge.resolve(text, record, choice)
            if new is None:
                return False
            if new != text:
                if editor := self.editors.get(node.id):
                    editor.replace_all(new)
                    self.save_all()
                else:
                    self.project.write_text(node, new)
                self._refresh_bible()
        remaining = [r for r in merge.load_conflicts(self.project.path) if r.id != record.id]
        merge.save_conflicts(self.project.path, remaining)
        self._update_conflicts_button()
        return True

    def _stop_syncing(self) -> None:
        if self.sync_target:
            self.live.leave()
            try:
                self.sync_target.leave(self.session)
            except (DriveError, TargetError, OSError):
                pass
        self.settings.remove(f"sync/{self.project.id}")
        self.sync_target = None
        self.sync_timer.stop()
        self.presence_timer.stop()
        self._clear_people()
        self.sync_label.clear()

    def show_sync_settings(self) -> None:
        if self.project is None:
            return
        dialog = SyncDialog(
            self.project.name, self.project.path,
            self.sync_target.describe() if self.sync_target else None, self.sync_label.text(),
            google=("unavailable" if not self.google_config else "signed_in" if self.google_account else "signed_out"),
            google_email=self.google_account.email if self.google_account else "",
            parent=self,
        )
        if not dialog.exec() or dialog.chosen is None:
            return
        if dialog.chosen == "":
            self._stop_syncing()
            return
        if dialog.chosen == SIGN_OUT:
            self.sign_out_google()
            return
        if dialog.chosen == GDRIVE_PREFIX:
            if not self.ensure_google():
                return
            target = DriveTarget(self._drive_client(), self.project.id, None, self._drive_cache())
        else:
            package = Path(dialog.chosen)
            if package.exists():
                try:
                    manifest = cloud.read_manifest(package)
                except cloud.SyncError as e:
                    QMessageBox.warning(self, "Sync", str(e))
                    return
                if manifest.get("project_id") != self.project.id:
                    QMessageBox.warning(
                        self, "Sync",
                        f"{package.name} in that folder belongs to a different project ({manifest.get('name')}).\n"
                        "Rename this project or choose another folder.",
                    )
                    return
            target = FolderTarget(package)
        if self.sync_target:
            self._stop_syncing()
        self._set_target(target)
        if not self.settings.contains("person/name"):
            self.set_your_name()
        if self.sync_now() is not None:
            self.sync_timer.start()
            self.presence_timer.start()
            where = "Open from Google Drive…" if target.kind == "gdrive" else "Open Project File… and pick that file"
            QMessageBox.information(
                self, "Sync & Backup",
                f"“{self.project.name}” now syncs with\n{target.describe()}\n\n"
                f"On another computer, choose File → {where}.",
            )

    # --- Google account --------------------------------------------------------------------

    def ensure_google(self) -> bool:
        """Signed in with Google? If not, run the sign-in now."""
        if self.google_account:
            return True
        if not self.google_config:
            QMessageBox.information(self, "Google Drive", "Google sign-in isn't set up in this build of Screenwriter.")
            return False
        account = sign_in_with_google(self.google_config, self)
        if account is None:
            return False
        if not account.remember():
            self.statusBar().showMessage("Signed in — but this computer has no secure store, so you'll sign in again next time", 8000)
        self.google_account = account
        if self.sync_target and self.sync_target.kind == "gdrive":
            self.sync_target.client = self._drive_client()
        return True

    def sign_out_google(self) -> None:
        if self.google_account:
            self.google_account.sign_out()
        self.google_account = None
        if self.sync_target and self.sync_target.kind == "gdrive":
            self.sync_target.client = None
            self.sync_label.setText("☁ Not syncing")
            self.sync_label.setToolTip(self.sync_target.unavailable_reason())
        self.statusBar().showMessage("Signed out of Google", 4000)

    def open_from_google_drive(self, file_id: str | None = None, parent_folder: str | None = None) -> None:
        """Pick a project kept in Google Drive and set it up on this computer."""
        if not self.ensure_google():
            return
        client = self._drive_client()
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        try:
            projects = client.list_projects()
        except DriveError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Open from Google Drive", str(e))
            return
        QApplication.restoreOverrideCursor()
        if file_id is None:
            if not projects:
                QMessageBox.information(self, "Open from Google Drive",
                                        "No Screenwriter projects in your Google Drive yet.\n"
                                        "Turn on sync for a project with File → Sync & Backup….")
                return
            labels = [f"{p.name.removesuffix(cloud.PACKAGE_EXT)}   ({p.modified[:10]})" for p in projects]
            label, ok = QInputDialog.getItem(self, "Open from Google Drive", "Project:", labels, 0, False)
            if not ok:
                return
            chosen = projects[labels.index(label)]
        else:
            chosen = next((p for p in projects if p.id == file_id), None)
            if chosen is None:
                return
        known = self.settings.value(f"sync_local/{chosen.project_id}")
        if known and Project.is_project(Path(known)):
            self.open_project(Path(known))
            return
        if parent_folder is None:
            parent_folder = QFileDialog.getExistingDirectory(
                self, "Where should the project live on this computer?", str(Path.home() / "Documents"))
            if not parent_folder:
                return
        cache = self._drive_cache() / f"{chosen.project_id}{cloud.PACKAGE_EXT}"
        try:
            client.download(chosen.id, cache)
            path = cloud.open_package(cache, Path(parent_folder))
        except (DriveError, cloud.SyncError, OSError) as e:
            QMessageBox.warning(self, "Open from Google Drive", str(e))
            return
        project_id = Project.open(path).id
        self.settings.setValue(f"sync/{project_id}", GDRIVE_PREFIX + chosen.id)
        self.settings.setValue(f"sync_local/{project_id}", str(path))
        self.open_project(path)

    def share_copy(self) -> None:
        """Write a .screenwriter copy (with history) to send to someone."""
        if self.project is None:
            return
        self.save_point()
        suggested = str(Path.home() / "Documents" / cloud.package_name(self.project.name))
        path, _ = QFileDialog.getSaveFileName(self, "Share a Copy", suggested, "Screenwriter project (*.screenwriter)")
        if not path:
            return
        if not path.endswith(cloud.PACKAGE_EXT):
            path += cloud.PACKAGE_EXT
        cloud.share(self.history, self.project.id, self.project.name, Path(path))
        self.statusBar().showMessage(f"Saved a copy to {path}", 6000)

    def open_project_file(self, package: str | None = None, parent_folder: str | None = None, keep_synced: bool | None = None) -> None:
        """Open a .screenwriter file: set up a local copy (or reuse the one already synced with it)."""
        if package is None:
            package, _ = QFileDialog.getOpenFileName(self, "Open Project File", str(Path.home()), "Screenwriter project (*.screenwriter)")
            if not package:
                return
        package_path = Path(package)
        try:
            manifest = cloud.read_manifest(package_path)
        except cloud.SyncError as e:
            QMessageBox.warning(self, "Open Project File", str(e))
            return
        known = self.settings.value(f"sync_local/{manifest.get('project_id')}")
        if known and Project.is_project(Path(known)):
            self.open_project(Path(known))  # already on this computer
            return
        if parent_folder is None:
            parent_folder = QFileDialog.getExistingDirectory(
                self, "Where should the project live on this computer?", str(Path.home() / "Documents"))
            if not parent_folder:
                return
        if keep_synced is None:
            in_cloud = any(cloud.inside(package_path, folder) for _, folder in cloud.cloud_folders())
            keep_synced = QMessageBox.question(
                self, "Keep in sync?",
                f"Keep this project in sync with\n{package_path}?\n\n"
                "Yes if it's your own project in a cloud folder. No for a copy someone sent you.",
                defaultButton=QMessageBox.StandardButton.Yes if in_cloud else QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes
        try:
            path = cloud.open_package(package_path, Path(parent_folder))
        except (cloud.SyncError, OSError) as e:
            QMessageBox.warning(self, "Open Project File", str(e))
            return
        if keep_synced:
            project_id = Project.open(path).id
            self.settings.setValue(f"sync/{project_id}", str(package_path))
            self.settings.setValue(f"sync_local/{project_id}", str(path))
        self.open_project(path)

    def close_tab(self, index: int) -> None:
        if index >= 0:
            self.save_all()
            self._remove_tab(index)

    def _remove_tab(self, index: int) -> None:
        editor = self.tabs.widget(index)
        self.tabs.removeTab(index)
        self.editors.pop(editor.node_id, None)
        editor.deleteLater()

    def _open_tab_ids(self) -> list[str]:
        return [self.tabs.widget(i).node_id for i in range(self.tabs.count())]

    def _on_tab_changed(self, index: int) -> None:
        self.save_all()
        self._update_element_actions()
        editor = self.tabs.widget(index)
        self._update_format_bar()
        self._update_banner()
        if editor is not None and editor.node_id in self.binder.unread:
            self._set_unread(self.binder.unread - {editor.node_id})
        if self.sync_target:
            self.announce_timer.start()
        if editor is None:
            self.stats_label.clear()
            self.element_label.clear()
            return
        if editor.node_id in self.tab_history:
            self.tab_history.remove(editor.node_id)
        self.tab_history.insert(0, editor.node_id)
        self._update_stats(editor)
        self.element_label.setText("")
        self._refresh_outline()
        if isinstance(editor, BibleEditor):
            editor.refresh_appearances()
        elif isinstance(editor, CorkboardView):
            editor.refresh()  # word counts may have changed
        if item := self.binder.find_item(editor.node_id):
            self.binder.blockSignals(True)
            self.binder.setCurrentItem(item)
            self.binder.blockSignals(False)

    def _on_renamed(self, node_id: str, title: str) -> None:
        if editor := self.editors.get(node_id):
            self.tabs.setTabText(self.tabs.indexOf(editor), self._tab_title(editor, title))
            if isinstance(editor, BibleEditor):
                editor.set_name(title)

    @staticmethod
    def _tab_title(editor, title: str) -> str:
        return f"{title} — Corkboard" if isinstance(editor, CorkboardView) else title

    def open_corkboard(self, folder_id: str) -> None:
        if folder_id in self.editors:
            self.tabs.setCurrentWidget(self.editors[folder_id])
            return
        self._save_structure()
        node = self.project.find(folder_id)
        if node is None or node.kind != FOLDER:
            return
        view = CorkboardView(self.binder, folder_id, self._text_of)
        view.openRequested.connect(self.open_document)
        view.statsChanged.connect(lambda v=view: self._update_stats(v))
        view.statsChanged.connect(lambda v=view: self._schedule_outline(v))  # cards added, moved, renamed
        view.cursorPositionChanged.connect(lambda v=view: self._on_cursor_moved(v))
        self.binder.structureChanged.connect(view.refresh)
        self.editors[folder_id] = view
        self.tabs.setCurrentIndex(self.tabs.addTab(view, self._tab_title(view, node.title)))
        view.setFocus()

    def open_selected_corkboard(self) -> None:
        """Corkboard of the selected folder, or of the selected document's folder."""
        item = self.binder.currentItem()
        while item is not None and item.data(0, Qt.ItemDataRole.UserRole + 1) != FOLDER:
            item = item.parent()
        if item is not None:
            self.open_corkboard(item.data(0, Qt.ItemDataRole.UserRole))

    def _rename_from_editor(self, node_id: str, title: str) -> None:
        if title := title.strip():
            self.binder.rename(node_id, title)
            if editor := self.editors.get(node_id):
                self.tabs.setTabText(self.tabs.indexOf(editor), title)

    def _on_deleted(self, node_ids: list[str]) -> None:
        for node_id in node_ids:
            if editor := self.editors.get(node_id):
                editor.mark_saved()
                self._remove_tab(self.tabs.indexOf(editor))

    def _update_stats(self, editor) -> None:
        if editor is self.tabs.currentWidget():
            self.stats_label.setText(editor.stats())

    def _update_element(self, editor, name: str) -> None:
        if editor is self.tabs.currentWidget():
            self.element_label.setText(name)
            self.format_bar.sync_element()

    def _update_format_bar(self) -> None:
        """Point the formatting toolbar at the current tab; hide it where there's nothing to format."""
        editor = self.tabs.currentWidget()
        if isinstance(editor, BibleEditor):
            editor = editor.notes
        target = editor if isinstance(editor, (ScreenplayEditor, ProseEditor)) else None
        self.format_bar.set_editor(target)
        focused = self.tabs.tab_bars_hidden()
        self.format_bar.setVisible(target is not None and self.toolbar_action.isChecked() and not focused)

    def _toggle_live(self) -> None:
        self.settings.setValue("live_editing", self.live_action.isChecked())
        self.live.enabled = self.live_action.isChecked()
        if not self.live.enabled:
            self.live.leave()
        self._update_banner()

    def _toggle_shortcut_hints(self) -> None:
        self.settings.setValue("shortcut_hints", self.hints_action.isChecked())
        self.shortcut_hints.set_enabled(self.hints_action.isChecked())

    def _toggle_format_bar(self) -> None:
        self.settings.setValue("format_bar", self.toolbar_action.isChecked())
        self._update_format_bar()

    def export_current(self) -> None:
        """Export the item selected in the binder (or the current tab's document)."""
        self.save_all()
        self._save_structure()
        item = self.binder.currentItem()
        node_id = item.data(0, Qt.ItemDataRole.UserRole) if item else getattr(self.tabs.currentWidget(), "node_id", None)
        node = self.project.find(node_id) if node_id else None
        if node is None:
            return
        if path := run_export(self, self.project, node, self._text_of):
            self.statusBar().showMessage(f"Exported to {path}", 6000)

    def _text_of(self, node) -> str:
        editor = self.editors.get(node.id)
        return editor.text() if editor else self.project.read_text(node)

    def open_at(self, node_id: str, pos: int, length: int) -> None:
        self.open_document(node_id)
        if editor := self.editors.get(node_id):
            editor.reveal(pos, length)

    def _searchable_documents(self) -> list[tuple[str, str, str]]:
        if self.project is None:
            return []
        self.project.root = self.binder.to_nodes()
        trash = next(n for n in self.project.root if n.kind == TRASH)
        trashed = {n.id for n in walk(trash.children)}
        docs = []
        for node in walk(self.project.root):
            if node.kind in DOCUMENT_KINDS and node.id not in trashed:
                editor = self.editors.get(node.id)
                if editor:
                    text = editor.search_text()
                elif node.kind == BOARD:
                    text = board.search_text(self.project.read_text(node))
                else:
                    text = self.project.read_text(node)
                docs.append((node.id, node.title, text))
        return docs

    # --- outline ------------------------------------------------------------------

    def _schedule_outline(self, editor) -> None:
        if editor is self.tabs.currentWidget():
            self.outline_timer.start()

    def _refresh_outline(self) -> None:
        editor = self.tabs.currentWidget()
        self.outline.set_items(editor.outline() if editor else [])
        self._refresh_cast()
        if editor:
            self.outline.highlight_line(editor.current_line())

    def _on_cursor_moved(self, editor) -> None:
        if editor is self.tabs.currentWidget():
            self.outline.highlight_line(editor.current_line())
            if isinstance(editor, BoardEditor):
                self._refresh_outline()

    def _jump_to_line(self, line: int) -> None:
        if editor := self.tabs.currentWidget():
            editor.jump_to_line(line)

    def _current_text_editor(self):
        editor = self.tabs.currentWidget()
        if isinstance(editor, BibleEditor):
            return editor.notes
        return None if isinstance(editor, BoardEditor) else editor

    # --- story bible ----------------------------------------------------------------

    def _scan_documents(self) -> list[tuple[str, str, str, str]]:
        """Scripts and prose to look for bible entries in: (id, title, kind, text)."""
        if self.project is None:
            return []
        self.project.root = self.binder.to_nodes()
        return [
            (n.id, n.title, "screenplay" if n.kind == SCREENPLAY else "prose", self._text_of(n))
            for n in self.project.documents((SCREENPLAY, PROSE))
        ]

    def _bible_entries(self, kinds=BIBLE_KINDS):
        if self.project is None:
            return []
        self.project.root = self.binder.to_nodes()
        return [(n, self._text_of(n)) for n in self.project.documents(kinds)]

    def _bible_names(self) -> tuple[list[str], list[str]]:
        return bible.known_names([(n.kind, text) for n, text in self._bible_entries()])

    def _find_bible_entry(self, kind: str, name: str) -> str | None:
        for node, text in self._bible_entries((kind,)):
            fields, _ = bible.parse_entry(text)
            if name.upper() in bible.script_names(fields, kind):
                return node.id
        return None

    def open_bible_entry(self, kind: str, name: str) -> None:
        """Open the entry for a name (from a script or prose), creating it in the
        "Story Bible" folder if there isn't one."""
        known = self.bible_index.lookup(name)
        if node_id := self._find_bible_entry(kind, name) or (known.node_id if known and known.kind == kind else None):
            self.open_document(node_id)
            return
        title = name.title() if name.isupper() else name  # MARA → Mara; prose keeps its casing
        node_id = self.binder.add(kind, title, parent=self.binder.folder("Story Bible"), edit=False)
        editor = self.editors.get(node_id)
        if isinstance(editor, BibleEditor) and name.isupper() and title.upper() != name:
            editor.inputs["aliases"].setText(name)
            editor.textChanged.emit()
        self.save_all()
        self._refresh_bible()
        self.statusBar().showMessage(f"Added “{title}” to the Story Bible", 3000)

    def add_bible_alias(self, node_id: str, name: str) -> None:
        """Record another form of an entry's name, e.g. "Kacprowi" for Kacper."""
        node = self.project.find(node_id)
        if node is None:
            return
        editor = self.editors.get(node_id)
        if isinstance(editor, BibleEditor):
            field = editor.inputs["aliases"]
            existing = [a.strip() for a in field.text().split(",") if a.strip()]
            if name.lower() not in (a.lower() for a in existing):
                field.setText(", ".join(existing + [name]))
                editor.textChanged.emit()
            self.save_all()
        else:
            fields, notes = bible.parse_entry(self.project.read_text(node))
            existing = bible.aliases(fields)
            if name.lower() not in (a.lower() for a in existing):
                fields["aliases"] = ", ".join(existing + [name])
                self.project.write_text(node, bible.format_entry(fields, notes))
        self._refresh_bible()
        self.statusBar().showMessage(f"“{name}” is now another name for {node.title}", 4000)

    def _connect_bible_menu(self, editor) -> None:
        editor.bibleAddRequested.connect(self.open_bible_entry)
        editor.bibleAliasRequested.connect(self.add_bible_alias)

    def _refresh_bible(self) -> None:
        """Rebuild the name index and hand it to every editor and the cast panel."""
        entries = [(n.id, n.kind, text) for n, text in self._bible_entries()]
        self.bible_index = bible.BibleIndex(entries)
        for editor in self.editors.values():
            if isinstance(editor, ProseEditor):
                editor.set_bible(self.bible_index)
            elif isinstance(editor, BibleEditor):
                editor.notes.set_bible(self.bible_index)
            elif isinstance(editor, ScreenplayEditor):
                editor.bible_index = self.bible_index
        self._refresh_cast()

    def _refresh_cast(self) -> None:
        editor = self.tabs.currentWidget()
        text = editor.search_text() if editor is not None else ""
        self.cast.set_cast(self.bible_index.cast(text), bool(self.bible_index))

    def _node_title(self, node_id: str) -> str:
        item = self.binder.find_item(node_id)
        return item.text(0) if item else ""

    # --- ideas --------------------------------------------------------------------

    def capture_idea(self) -> None:
        if self.project is None:
            return
        self._save_structure()
        inbox, created = self.project.ensure_inbox()
        if created:
            self.binder.load(self.project)
        dialog = QuickCapture(inbox.title, self)
        if dialog.exec() and dialog.text():
            self.add_idea(dialog.text())

    def add_idea(self, text: str) -> None:
        self._save_structure()
        inbox, created = self.project.ensure_inbox()
        if created:
            self.binder.load(self.project)
        idea = format_idea(text)
        if editor := self.editors.get(inbox.id):
            cursor = editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.insertText(append_idea(editor.text(), idea))
            self.save_all()
        else:
            existing = self.project.read_text(inbox)
            self.project.write_text(inbox, existing + append_idea(existing, idea))
        self.statusBar().showMessage(f"Idea saved to “{inbox.title}”", 3000)

    # --- go to document / split view ------------------------------------------------

    def _quick_open_targets(self) -> list[Target]:
        """Everything Go to Document can open: open tabs (most recent first), then every
        document, folder and board card in binder order."""
        if self.project is None:
            return []
        self._save_structure()
        open_ids = set(self._open_tab_ids())
        targets: list[Target] = []

        def visit(nodes, path: str) -> None:
            for node in nodes:
                if node.kind == TRASH:
                    continue
                if node.kind == FOLDER:
                    targets.append(Target(node.title, f"{path} › Corkboard" if path else "Corkboard", FOLDER, node.id,
                                          is_open=node.id in open_ids))
                elif node.kind in DOCUMENT_KINDS:
                    targets.append(Target(node.title, path, node.kind, node.id, is_open=node.id in open_ids))
                    if node.kind == BOARD:
                        editor = self.editors.get(node.id)
                        cards = editor.search_text() if editor else board.search_text(self.project.read_text(node))
                        for i, card in enumerate(cards.split("\n") if cards else []):
                            if card.strip():
                                targets.append(Target(card.strip()[:80], f"Card on {node.title}", BOARD, node.id, line=i))
                visit(node.children, f"{path} › {node.title}" if path else node.title)

        visit(self.project.root, "")
        recent = {node_id: i for i, node_id in enumerate(self.tab_history)}
        opened = sorted((t for t in targets if t.is_open), key=lambda t: recent.get(t.node_id, len(recent)))
        return opened + [t for t in targets if not t.is_open]

    def quick_open(self) -> None:
        if self.project is None:
            return
        dialog = QuickOpen(self._quick_open_targets(), self.binder.icons, self)
        if dialog.exec() and dialog.chosen:
            self.go_to(dialog.chosen, beside=dialog.beside)

    def go_to(self, target: Target, beside: bool = False) -> None:
        self.open_document(target.node_id)
        editor = self.editors.get(target.node_id)
        if editor is None:
            return
        if beside:
            self.open_beside(editor)
        if target.line is not None:
            editor.jump_to_line(target.line)
        editor.setFocus()

    def open_beside(self, editor) -> None:
        """Show a tab in the other half of the view, splitting it if needed."""
        if not self.tabs.is_split():
            self.tabs.setCurrentWidget(editor)
            self.tabs.split(self.tabs.orientation())
        elif self.tabs.active.indexOf(editor) >= 0:
            self.tabs.move_to_other_pane(editor)
        else:
            self.tabs.setCurrentWidget(editor)

    def split(self, orientation) -> None:
        if self.tabs.count() < 2 and not self.tabs.is_split():
            self.statusBar().showMessage("Open another document to split the view — it goes on the other side", 4000)
        self.tabs.split(orientation)

    # --- view -------------------------------------------------------------------

    def toggle_binder(self) -> None:
        self.binder.setVisible(not self.binder.isVisible())

    def toggle_side(self) -> None:
        self.side.setVisible(not self.side.isVisible())

    def show_outline(self) -> None:
        self.side.show()
        self.side.setCurrentWidget(self.outline)

    def show_search(self) -> None:
        self.side.show()
        self.side.setCurrentWidget(self.search)
        editor = self.tabs.currentWidget()
        self.search.focus(editor.selected_text() if editor else "")

    def toggle_focus(self) -> None:
        focused = self.binder.isVisible()
        self.binder.setVisible(not focused)
        self.side.setVisible(not focused)
        self.statusBar().setVisible(not focused)
        self.tabs.set_tab_bars_visible(not focused)
        if focused:
            self.find_bar.hide()
        self._update_format_bar()

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _zoom(self, steps: int) -> None:
        if editor := self.tabs.currentWidget():
            editor.zoom(steps)

    def show_screenplay_help(self) -> None:
        QMessageBox.information(self, "Screenplay Keys", screenplay.__doc__.split("Keys:", 1)[1].strip("\n"))

    def show_about(self) -> None:
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion

        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Screenplays, books, notes and ideas.<br>Free and open source under the MIT License.</p>"
            f'<p><a href="{REPOSITORY}">{REPOSITORY}</a></p>'
            f"<p style='color:gray'>Built with Qt {qVersion()} and PySide6 {pyside_version} "
            "(LGPLv3, <a href='https://www.qt.io/licensing/open-source-lgpl-obligations'>qt.io</a>).</p>",
        )

    def show_board_help(self) -> None:
        from .editors import board as board_editor

        QMessageBox.information(self, "Board Keys", board_editor.__doc__.split("\n\n", 1)[1].strip("\n"))

    def closeEvent(self, event) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        self.close_project()
        QApplication.instance().removeEventFilter(self.shortcut_hints)
        QApplication.instance().removeEventFilter(self.double_shift)
        self.tabs.detach()
        # While Qt tears the window down it still emits signals (tab changes,
        # selection changes); don't let them reach half-destroyed Python objects.
        for timer in (self.save_timer, self.outline_timer, self.bible_timer, self.history_timer, self.sync_timer,
                      self.presence_timer, self.announce_timer, self.quick_sync_timer, self.live.timer):
            timer.stop()
        for widget in (self.tabs, self.binder, self.outline, self.search, self.cast, self.side):
            widget.blockSignals(True)
        super().closeEvent(event)
