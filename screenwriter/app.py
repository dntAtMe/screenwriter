import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from .mainwindow import APP_NAME, MainWindow
from .project import Project


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    window = MainWindow()
    window.show()

    # Open a project folder given on the command line, else the last one used.
    if len(sys.argv) > 1:
        window.open_project(Path(sys.argv[1]).expanduser().resolve())
    elif (last := QSettings().value("last_project")) and Project.is_project(Path(last)):
        window.open_project(Path(last))

    sys.exit(app.exec())
