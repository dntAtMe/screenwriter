"""File → Sync & Backup: choose the cloud folder a project syncs through."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .sync import cloud_folders, inside, package_name

SUBFOLDER = "Screenwriter"
GDRIVE = "gdrive:"
SIGN_OUT = "sign-out"


def short_path(path: Path, limit: int = 48) -> str:
    """~/…/My Drive/Screenwriter — readable in a button; the full path goes in the tooltip."""
    try:
        text = "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        text = path.as_posix()
    if len(text) > limit:
        text = "…/" + "/".join(path.parts[-3:])
    return text


class SyncDialog(QDialog):
    """Returns (via .chosen) the package path to sync with, "" to stop syncing, or None."""

    def __init__(self, project_name: str, project_path: Path, current: str | None, status: str,
                 google: str = "unavailable", google_email: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sync & Backup")
        self.setMinimumWidth(560)
        self.setMaximumWidth(720)
        self.project_name = project_name
        self.chosen: str | None = None

        intro = QLabel(
            "<p>Keep this project in a <b>cloud folder</b> — Google Drive, Dropbox, iCloud Drive or OneDrive — "
            "to back it up and to work on it from other computers.</p>"
            f"<p>Screenwriter keeps it there as a single file, <b>{package_name(project_name)}</b>, with the "
            "project's whole history. It syncs when you open and close the project and every few minutes "
            "while you write. If two computers change the same document, both versions are kept.</p>"
            "<p style='color:gray'>On another computer: File → Open Project File… and pick that file.</p>"
        )
        intro.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)

        if current:
            shown = short_path(Path(current), 70) if not current.startswith("Google Drive") else current
            now = QLabel(f"<b>Syncing with</b><br>{shown}<br><span style='color:gray'>{status}</span>")
            now.setToolTip(str(current))
            now.setWordWrap(True)
            layout.addWidget(now)

        folders = cloud_folders()
        for label, folder in folders:
            if inside(project_path, folder):
                warning = QLabel(
                    f"<span style='color:#c0392b'>This project's folder is already inside {label}. "
                    "Syncing through a file works better: move the project folder out of it (for example to "
                    "Documents) and turn sync on here.</span>"
                )
                warning.setWordWrap(True)
                layout.addWidget(warning)
                break

        layout.addWidget(QLabel("<b>Sync through</b>" if not current else "<b>Switch to</b>"))
        if google != "unavailable":
            label = "Google Drive — signed in as " + google_email if google == "signed_in" and google_email else \
                "Google Drive — signed in" if google == "signed_in" else "Google Drive — Sign in with Google…"
            drive = QPushButton(label)
            drive.setToolTip("Keeps the project in My Drive/Screenwriter. No Google Drive app needed; "
                             "Screenwriter can only see the files it creates.")
            drive.clicked.connect(lambda: self._finish(GDRIVE))
            layout.addWidget(drive)
            layout.addWidget(QLabel("<span style='color:gray'>…or a folder that your cloud app keeps in sync:</span>"))
        for label, folder in folders:
            target = folder / SUBFOLDER / package_name(project_name)
            button = QPushButton(f"{label}   ({short_path(folder / SUBFOLDER)})")
            button.setToolTip(str(target))
            button.clicked.connect(lambda _=False, t=target: self._choose(t))
            layout.addWidget(button)
        if not folders:
            none = QLabel("<span style='color:gray'>No cloud folders found on this computer. Install Google Drive "
                          "for desktop (or Dropbox, OneDrive…), or choose any folder — a USB drive works as a backup too.</span>")
            none.setWordWrap(True)
            layout.addWidget(none)
        other = QPushButton("Choose Another Folder…")
        other.clicked.connect(self._choose_folder)
        layout.addWidget(other)

        bottom = QHBoxLayout()
        if google == "signed_in":
            sign_out = QPushButton("Sign Out of Google")
            sign_out.clicked.connect(lambda: self._finish(SIGN_OUT))
            bottom.addWidget(sign_out)
        if current:
            stop = QPushButton("Stop Syncing")
            stop.setToolTip("The project stays on this computer and the file in the cloud folder is left as it is.")
            stop.clicked.connect(lambda: self._finish(""))
            bottom.addWidget(stop)
        bottom.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        layout.addLayout(bottom)

    def _choose(self, target: Path) -> None:
        self._finish(str(target))

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Sync this project through which folder?", str(Path.home()))
        if folder:
            self._finish(str(Path(folder) / package_name(self.project_name)))

    def _finish(self, value: str) -> None:
        self.chosen = value
        self.accept()
