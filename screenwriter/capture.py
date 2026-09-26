"""Quick capture: jot an idea into the project's Idea Inbox from anywhere."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout


def format_idea(text: str, when: datetime | None = None) -> str:
    """A Markdown list item; extra lines are indented under it."""
    when = when or datetime.now()
    first, *rest = text.strip().splitlines()
    stamp = when.strftime("%d %b %Y, %H:%M")
    lines = [f"- {first} _({stamp})_"] + [f"  {line}" if line.strip() else "" for line in rest]
    return "\n".join(lines)


def append_idea(existing: str, idea: str) -> str:
    """The text to append to `existing` so the idea joins the list at its end,
    or starts a new list after a blank line."""
    if not existing.strip():
        return idea + "\n"
    last = existing.rstrip("\n").splitlines()[-1]
    if last.startswith(("- ", "  ")):
        sep = "" if existing.endswith("\n") else "\n"
    else:
        sep = "\n" * (2 - (len(existing) - len(existing.rstrip("\n"))))
    return sep + idea + "\n"


class QuickCapture(QDialog):
    def __init__(self, inbox_title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capture Idea")
        self.setMinimumWidth(460)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("What's the idea?")
        self.edit.setFixedHeight(110)
        hint = QLabel(f"Saved to “{inbox_title}” · Ctrl+Enter to save · Esc to cancel")
        hint.setStyleSheet("color: gray;")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.edit)
        layout.addWidget(hint)
        layout.addWidget(buttons)
        self.edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        if (
            obj is self.edit
            and event.type() == event.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
        ):
            self.accept()
            return True
        return super().eventFilter(obj, event)

    def text(self) -> str:
        return self.edit.toPlainText().strip()
