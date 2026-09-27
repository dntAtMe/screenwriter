"""File → Export: pick a format for the selected binder item and write it."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel, QMessageBox

from .board import Board
from .marks import strip_marks
from .export import Format
from .export import manuscript, screenplay
from .project import BOARD, FOLDER, NOTE, PROSE, SCREENPLAY, Node, Project, walk


def export_formats(project: Project, node: Node, text_of) -> tuple[str, list[Format]]:
    """(description, formats) for a binder node. text_of(node) returns its current text."""
    if node.kind == SCREENPLAY:
        text = text_of(node)
        return f"Screenplay “{node.title}”", [
            Format("PDF (screenplay format)", "pdf", True, lambda p, paper: screenplay.write_pdf(text, p, paper, node.title)),
            Format("Final Draft (.fdx)", "fdx", False, lambda p, paper: Path(p).write_text(screenplay.to_fdx(text), encoding="utf-8")),
            Format("Fountain (.fountain)", "fountain", False, lambda p, paper: Path(p).write_text(strip_marks(text), encoding="utf-8")),
        ]
    if node.kind == BOARD:
        text = text_of(node)

        def render(path, paper):
            from .editors.board import BoardEditor

            editor = BoardEditor()
            editor.set_text(text)
            editor.export_image(path)
            editor.deleteLater()

        return f"Board “{node.title}”", [
            Format("PNG image", "png", False, render),
            Format("PDF", "pdf", False, render),
        ]
    if node.kind == FOLDER:
        docs = [(n.title, text_of(n)) for n in walk(node.children) if n.kind == PROSE]
        what = f"Folder “{node.title}” ({len(docs)} prose document{'s' if len(docs) != 1 else ''}, compiled in binder order)"
    elif node.kind in (PROSE, NOTE):
        docs = [(node.title, text_of(node))]
        what = f"“{node.title}”"
    else:
        return "", []
    md = manuscript.compile_markdown(docs) if docs else ""
    if not md.strip():
        return what, []
    return what, [
        Format("PDF", "pdf", True, lambda p, paper: manuscript.write_pdf(md, p, paper, node.title)),
        Format("Word (.docx, manuscript format)", "docx", False, lambda p, paper: manuscript.write_docx(md, p, node.title)),
        Format("Markdown (.md)", "md", False, lambda p, paper: manuscript.write_markdown(md, p)),
    ]


class ExportDialog(QDialog):
    def __init__(self, what: str, formats: list[Format], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.formats = formats
        self.settings = QSettings()
        self.format_box = QComboBox()
        self.format_box.addItems([f.label for f in formats])
        self.paper_box = QComboBox()
        self.paper_box.addItems(["Letter", "A4"])
        self.paper_box.setCurrentText(self.settings.value("export/paper", "Letter"))
        self.format_box.currentIndexChanged.connect(self._on_format)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow(QLabel(what))
        form.addRow("Format", self.format_box)
        form.addRow("Paper", self.paper_box)
        form.addRow(buttons)
        self.paper_label = form.labelForField(self.paper_box)
        self._on_format()

    def _on_format(self) -> None:
        paper = self.format().paper
        self.paper_box.setVisible(paper)
        self.paper_label.setVisible(paper)

    def format(self) -> Format:
        return self.formats[self.format_box.currentIndex()]

    def paper(self) -> str:
        self.settings.setValue("export/paper", self.paper_box.currentText())
        return self.paper_box.currentText()


def run_export(parent, project: Project, node: Node, text_of) -> str | None:
    """Show the dialog, ask where to save, export. Returns the written path."""
    what, formats = export_formats(project, node, text_of)
    if not formats:
        QMessageBox.information(parent, "Export", f"Nothing to export in {what or 'this item'}.\n"
                                "Select a screenplay, a prose document, a board or a folder of chapters.")
        return None
    dialog = ExportDialog(what, formats, parent)
    if not dialog.exec():
        return None
    fmt, paper = dialog.format(), dialog.paper()
    settings = QSettings()
    folder = settings.value("export/folder", str(Path.home() / "Documents"))
    suggested = str(Path(folder) / f"{node.title}.{fmt.extension}")
    path, _ = QFileDialog.getSaveFileName(parent, "Export", suggested, f"{fmt.label} (*.{fmt.extension})")
    if not path:
        return None
    if not path.lower().endswith("." + fmt.extension):
        path += "." + fmt.extension
    settings.setValue("export/folder", str(Path(path).parent))
    try:
        fmt.run(path, paper)
    except Exception as e:  # report, don't crash the app
        QMessageBox.warning(parent, "Export failed", f"Could not export to {path}:\n{e}")
        return None
    return path
