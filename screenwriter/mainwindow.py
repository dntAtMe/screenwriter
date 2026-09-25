from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
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

from .binder import Binder
from .editors.prose import ProseEditor
from .editors.screenplay import ScreenplayEditor
from .editors import screenplay
from .project import FOLDER, NOTE, PROSE, SCREENPLAY, Project

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
        new_btn.clicked.connect(window.new_project)
        open_btn.clicked.connect(window.open_project_dialog)
        self.recent = QListWidget()
        self.recent.setMaximumHeight(180)
        self.recent.itemActivated.connect(lambda item: window.open_project(Path(item.text())))

        buttons = QHBoxLayout()
        buttons.addWidget(new_btn)
        buttons.addWidget(open_btn)
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

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.splitter = QSplitter()
        self.splitter.addWidget(self.binder)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([240, 960])

        self.welcome = Welcome(self)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.splitter)
        self.setCentralWidget(self.stack)

        self.stats_label = QLabel()
        self.element_label = QLabel()
        self.element_label.setStyleSheet("color: gray;")
        self.statusBar().addPermanentWidget(self.element_label)
        self.statusBar().addPermanentWidget(self.stats_label)

        # Autosave: shortly after typing stops, and always on tab switch / close.
        self.save_timer = QTimer(self, singleShot=True, interval=1500)
        self.save_timer.timeout.connect(self.save_all)

        self._build_menus()
        self._set_project_actions_enabled(False)
        self.welcome.set_recent(self._recent())
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        if geometry := self.settings.value("geometry"):
            self.restoreGeometry(geometry)

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
        file.addSeparator()
        self.project_actions = [
            self._action(file, "Save", self.save_all, QKeySequence.StandardKey.Save),
            self._action(file, "Close Tab", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W"),
            self._action(file, "Close Project", self._close_project_from_menu),
        ]

        insert = bar.addMenu("&Insert")
        for kind, label, shortcut in (
            (PROSE, "New Prose Document", "Ctrl+N"),
            (SCREENPLAY, "New Screenplay", "Ctrl+Alt+N"),
            (NOTE, "New Note", "Ctrl+Shift+J"),
            (FOLDER, "New Folder", "Ctrl+Shift+G"),
        ):
            self.project_actions.append(self._action(insert, label, lambda _=False, k=kind: self.binder.add(k), shortcut))

        view = bar.addMenu("&View")
        self.project_actions += [
            self._action(view, "Toggle Binder", self.toggle_binder, "Ctrl+\\"),
            self._action(view, "Focus Mode", self.toggle_focus, "Ctrl+Shift+F"),
        ]
        self._action(view, "Full Screen", self.toggle_fullscreen, "Ctrl+Meta+F")
        view.addSeparator()
        self.project_actions += [
            self._action(view, "Zoom In", lambda: self._zoom(1), QKeySequence.StandardKey.ZoomIn),
            self._action(view, "Zoom Out", lambda: self._zoom(-1), QKeySequence.StandardKey.ZoomOut),
        ]

        help_menu = bar.addMenu("&Help")
        self._action(help_menu, "Screenplay Keys", self.show_screenplay_help)

    def _set_project_actions_enabled(self, enabled: bool) -> None:
        for action in self.project_actions:
            action.setEnabled(enabled)

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
        self.stack.setCurrentWidget(self.splitter)
        self._set_project_actions_enabled(True)
        self.setWindowTitle(f"{project.name} — {APP_NAME}")
        self._remember(project.path)
        for node_id in self.settings.value(f"open_tabs/{project.path}", []) or []:
            if project.find(node_id):
                self.open_document(node_id)

    def close_project(self) -> None:
        if self.project is None:
            return
        self.save_all()
        self.settings.setValue(f"open_tabs/{self.project.path}", self._open_tab_ids())
        while self.tabs.count():
            self._remove_tab(0)
        self.project = None
        self.binder.clear()
        self.stack.setCurrentWidget(self.welcome)
        self.welcome.set_recent(self._recent())
        self._set_project_actions_enabled(False)
        self.setWindowTitle(APP_NAME)

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
        editor = ScreenplayEditor() if node.kind == SCREENPLAY else ProseEditor()
        editor.node_id = node_id
        editor.set_text(self.project.read_text(node))
        editor.textChanged.connect(self.save_timer.start)
        editor.statsChanged.connect(lambda e=editor: self._update_stats(e))
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
            if editor.document().isModified():
                node = self.project.find(node_id)
                if node:
                    self.project.write_text(node, editor.text())
                editor.document().setModified(False)

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
        editor = self.tabs.widget(index)
        if editor is None:
            self.stats_label.clear()
            self.element_label.clear()
            return
        self._update_stats(editor)
        self.element_label.setText("")
        if item := self.binder.find_item(editor.node_id):
            self.binder.blockSignals(True)
            self.binder.setCurrentItem(item)
            self.binder.blockSignals(False)

    def _on_renamed(self, node_id: str, title: str) -> None:
        if editor := self.editors.get(node_id):
            self.tabs.setTabText(self.tabs.indexOf(editor), title)

    def _on_deleted(self, node_ids: list[str]) -> None:
        for node_id in node_ids:
            if editor := self.editors.get(node_id):
                editor.document().setModified(False)
                self._remove_tab(self.tabs.indexOf(editor))

    def _update_stats(self, editor) -> None:
        if editor is self.tabs.currentWidget():
            self.stats_label.setText(editor.stats())

    def _update_element(self, editor, name: str) -> None:
        if editor is self.tabs.currentWidget():
            self.element_label.setText(name)

    # --- view -------------------------------------------------------------------

    def toggle_binder(self) -> None:
        self.binder.setVisible(not self.binder.isVisible())

    def toggle_focus(self) -> None:
        focused = self.binder.isVisible()
        self.binder.setVisible(not focused)
        self.statusBar().setVisible(not focused)
        self.tabs.tabBar().setVisible(not focused)

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _zoom(self, steps: int) -> None:
        if editor := self.tabs.currentWidget():
            editor.zoom(steps)

    def show_screenplay_help(self) -> None:
        QMessageBox.information(self, "Screenplay Keys", screenplay.__doc__.split("Keys:", 1)[1].strip("\n"))

    def closeEvent(self, event) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.close_project()
        super().closeEvent(event)
