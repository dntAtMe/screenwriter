"""View → Fonts…: pick the script, prose and screenplay-PDF fonts, with a live preview."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from . import fonts

SAMPLES = {
    "script": "INT. ZAMEK — NOC\n\n              XARDAS\n        Czekałem na ciebie.",
    "prose": "Zakapturzona postać zgasiła świecę. „Czekałem”, rzekł cicho, nie odwracając się od okna.",
}
LABELS = {"script": "Scripts", "prose": "Prose and notes", "script_pdf": "Screenplay PDF"}


class FontDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fonts")
        self.combos: dict[str, QComboBox] = {}
        form = QFormLayout()
        for kind in fonts.KINDS:
            combo = QComboBox()
            for choice in fonts.choices(kind):
                combo.addItem(f"{choice.family} — {choice.note}", choice.family)
                item_font = QFont(choice.family)
                item_font.setPointSizeF(combo.font().pointSizeF() * 1.1)
                combo.setItemData(combo.count() - 1, item_font, Qt.ItemDataRole.FontRole)
            combo.setCurrentIndex(max(0, combo.findData(fonts.family(kind))))
            combo.currentIndexChanged.connect(self._preview)
            self.combos[kind] = combo
            form.addRow(LABELS[kind], combo)
        pdf_note = QLabel("A screenplay PDF keeps Courier's page layout, so only fonts with "
                          "letters all of one width (10 per inch) are offered for it.")
        pdf_note.setWordWrap(True)
        pdf_note.setStyleSheet("color: gray;")
        form.addRow("", pdf_note)
        self.smooth = QCheckBox("Smooth letters (softer, less pixel-snapped)")
        self.smooth.setChecked(fonts.smooth())
        self.smooth.toggled.connect(self._preview)
        form.addRow("", self.smooth)

        self.previews = {kind: QLabel(text) for kind, text in SAMPLES.items()}
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        for kind, label in self.previews.items():
            label.setWordWrap(True)
            label.setStyleSheet("background: palette(base); padding: 10px; border-radius: 4px;")
            layout.addWidget(QLabel(f"<b>{LABELS[kind]}</b>"))
            layout.addWidget(label)
        layout.addWidget(buttons)
        self._preview()

    def _preview(self) -> None:
        for kind, label in self.previews.items():
            f = QFont(self.combos[kind].currentData())
            f.setPointSizeF(13)
            if self.smooth.isChecked():
                f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
                f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            label.setFont(f)

    def save(self) -> None:
        for kind, combo in self.combos.items():
            fonts.set_family(kind, combo.currentData())
        fonts.set_smooth(self.smooth.isChecked())
