import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    # Headless Qt on Windows finds no fonts by itself; without them PDFs hold empty boxes, not text.
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("ScreenwriterTests")
    app.setApplicationName("ScreenwriterTests")
    return app


SAMPLE = __import__("pathlib").Path(__file__).parent.parent / "examples" / "The Lighthouse"


@pytest.fixture
def sample_project(tmp_path):
    """A fresh copy of the sample project, without history left by running the app on it."""
    import shutil

    dest = tmp_path / "sample"
    shutil.copytree(SAMPLE, dest, ignore=shutil.ignore_patterns("snapshots", "*.tmp"))
    return dest


def dispose(*widgets) -> None:
    """Close and really delete widgets now, rather than whenever Python collects them."""
    from PySide6.QtCore import QCoreApplication, QEvent

    for widget in widgets:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
