import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import __version__, fonts, theme
from .mainwindow import APP_NAME, MainWindow
from .project import Project

ICON = Path(__file__).resolve().parent / "resources" / "icon.png"


def log(message: str) -> None:
    """print() for smoke tests; windowed Windows builds have no stdout."""
    try:
        if sys.stdout is not None:
            print(message, flush=True)
    except OSError:  # closed pipe
        pass


def main() -> None:
    # SCREENWRITER_PROFILE=Anna runs a second copy with its own settings (name, recent projects,
    # sync) — for trying out writing together on one computer.
    profile = os.environ.get("SCREENWRITER_PROFILE", "").strip()
    name = f"{APP_NAME} ({profile})" if profile else APP_NAME
    QApplication.setOrganizationName(APP_NAME)
    QApplication.setApplicationName(name)
    if sys.platform == "win32" and "QT_QPA_PLATFORM" not in os.environ and fonts.smooth():
        # Windows' own text rendering (ClearType) is crisp and pixel-snapped; FreeType draws
        # the softer, grayscale letters of View → Fonts → Smooth letters. Chosen at startup.
        os.environ["QT_QPA_PLATFORM"] = "windows:fontengine=freetype"
    app = QApplication(sys.argv)
    app.setApplicationName(name)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    theme.apply()
    if ICON.exists():
        app.setWindowIcon(QIcon(str(ICON)))

    window = MainWindow()
    window.show()

    # Open a project folder given on the command line, else the last one used.
    # (Apps started from Finder may get extra arguments such as -psn_…; ignore them.)
    folders = [Path(a).expanduser().resolve() for a in sys.argv[1:] if not a.startswith("-")]
    if folders:
        window.open_project(folders[0])
    elif (last := QSettings().value("last_project")) and Project.is_project(Path(last)):
        window.open_project(Path(last))

    if not os.environ.get("SCREENWRITER_SMOKE_TEST"):
        QTimer.singleShot(4000, window.check_for_updates)  # a new version? (at most once a day; Help menu)

    if os.environ.get("SCREENWRITER_SMOKE_TEST"):
        # CI: prove the packaged app starts (and can open a project), then quit.
        def report():
            try:
                log(f"{APP_NAME} {__version__} started; project: {window.project.name if window.project else None}")
                if (folder := os.environ.get("SCREENWRITER_SMOKE_EXPORT")) and window.project:
                    smoke_export(window, Path(folder))
                if url := os.environ.get("SCREENWRITER_SMOKE_HTTPS"):
                    smoke_https(url)
            except Exception as e:  # fail loudly, but never hang
                log(f"smoke test failed: {e!r}")
                app.exit(1)
                return
            app.quit()

        QTimer.singleShot(1500, report)

    sys.exit(app.exec())


def smoke_https(url: str) -> None:
    """Prove the packaged app can make a verified HTTPS request (update check, Google Drive)."""
    import urllib.request

    from . import net

    with net.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as response:
        log(f"https ok: {url} → {response.status}")


def smoke_export(window: MainWindow, folder: Path) -> None:
    """Export every document of the open project in every format (CI check of a packaged build)."""
    from .exportdialog import export_formats
    from .project import walk

    folder.mkdir(parents=True, exist_ok=True)
    project = window.project
    for node in walk(project.root):
        _, formats = export_formats(project, node, project.read_text)
        for fmt in formats:
            path = folder / f"{node.id}-{fmt.label.split()[0].lower()}.{fmt.extension}"
            fmt.run(str(path), "Letter")
            log(f"exported {path.name} ({path.stat().st_size} bytes)")
