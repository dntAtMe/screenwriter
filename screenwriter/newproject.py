"""New Project: a name, and what kind of project to start with."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)

BLANK, CAMPAIGN = "blank", "campaign"
TEMPLATES = [
    (BLANK, "Writing project", "An empty binder for a screenplay, a novel, notes — or all of them."),
    (CAMPAIGN, "Tabletop campaign",
     "For game masters: folders for sessions, adventures, NPCs, locations, factions and items, "
     "a campaign overview, random tables and a first session to prep."),
]


class NewProjectDialog(QDialog):
    def __init__(self, parent=None, template: str = BLANK):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setMinimumWidth(420)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Project name")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Name:"))
        layout.addWidget(self.name)
        layout.addSpacing(8)
        layout.addWidget(QLabel("Start with:"))
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QRadioButton] = {}
        for key, label, detail in TEMPLATES:
            button = QRadioButton(label)
            button.setChecked(key == template)
            self.group.addButton(button)
            self.buttons[key] = button
            hint = QLabel(detail)
            hint.setWordWrap(True)
            hint.setObjectName("Hint")
            hint.setStyleSheet("color: gray; margin-left: 22px;")
            layout.addWidget(button)
            layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Choose Folder…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addSpacing(8)
        layout.addWidget(buttons)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.name.textChanged.connect(lambda t: self.ok.setEnabled(bool(t.strip())))
        self.ok.setEnabled(False)

    def template(self) -> str:
        return next(key for key, button in self.buttons.items() if button.isChecked())

    def project_name(self) -> str:
        return self.name.text().strip()
