"""Regenerate the screenshots in docs/images from the sample project.

    uv run python packaging/screenshots.py            # all of them
    uv run python packaging/screenshots.py prose      # just one

Works on a fresh copy of examples/The Lighthouse (plus a few Story Bible entries),
in the dark colour scheme, with its own settings so your own recent projects,
window layout and tabs are left alone. Images are 1600 x 978, like the ones on the
website.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SIZE = QSize(1600, 978)
SCALE = 1.25  # the window is 1280 x 782, drawn at 125% like a typical laptop screen
OUT = Path(os.environ.get("SCREENSHOTS_OUT", ROOT / "docs" / "images"))  # e.g. to preview elsewhere
APPEARANCE = os.environ.get("SCREENSHOTS_APPEARANCE", "dark")  # "dark" or "light"

BIBLE = [
    ("character", "Mara Quinn", {"aliases": "MARA, the keeper", "role": "Lighthouse keeper", "age": "40s",
                                 "description": "Has kept the light on Skerry Rock for eleven winters. Unhurried; notices everything."},
     "## Backstory\n\nTook over the light from her father. Writes the weather in the log at dawn, in his hand.\n"),
    ("character", "Owen", {"aliases": "OWEN", "role": "Supply-boat skipper", "age": "60s",
                           "description": "Brings the supplies on the first Monday of every month. Never late."}, ""),
    ("location", "Skerry Rock", {"aliases": "SKERRY ROCK LIGHTHOUSE, the Rock",
                                 "description": "A bare rock with a lighthouse, an hour out by boat."}, ""),
]


def settle(app) -> None:
    for _ in range(30):
        app.processEvents()


def main(wanted: set[str]) -> None:
    os.environ["QT_SCALE_FACTOR"] = str(SCALE)
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("ScreenwriterScreenshots")
    app.setApplicationName("ScreenwriterScreenshots")
    QSettings().clear()
    QSettings().setValue("appearance", APPEARANCE)
    from screenwriter import theme

    theme.apply()  # the app's own look, as users see it

    from screenwriter import bible
    from screenwriter.mainwindow import MainWindow
    from screenwriter.project import CHARACTER, LOCATION

    work = Path(tempfile.mkdtemp())
    project_path = work / "The Lighthouse"
    sample = Path(os.environ.get("SCREENSHOTS_SAMPLE", ROOT / "examples" / "The Lighthouse"))
    shutil.copytree(sample, project_path, ignore=shutil.ignore_patterns(".history", "*.tmp"))

    window = MainWindow()
    window.resize(SIZE / SCALE)
    window.show()
    window.open_project(project_path)
    folder = window.binder.folder("Story Bible")
    ids = {}
    for kind, name, fields, notes in BIBLE:
        node_id = window.binder.add(CHARACTER if kind == "character" else LOCATION, name, parent=folder, edit=False, open_it=False)
        window.project.root = window.binder.to_nodes()
        window.project.write_text(window.project.find(node_id), bible.format_entry({"name": name, **fields}, notes))
        ids[name] = node_id
    window.binder.set_synopsis("ch01", "Mara keeps the light, as she has for eleven winters. The boat comes on the wrong day.")
    window.binder.set_synopsis("ch02", "Fog closes over the Rock and the stranger starts asking questions.")
    window._save_structure()
    window._refresh_bible()
    window.binder.setCurrentItem(None)
    window.splitter.setSizes([213, 811, 256])

    def shoot(name: str, setup) -> None:
        if wanted and name not in wanted:
            return
        window.side.show()
        window.tabs.unsplit()
        while window.tabs.count():
            window.close_tab(0)
        setup()
        settle(app)
        image = window.grab().toImage().scaled(SIZE, Qt.AspectRatioMode.IgnoreAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
        image.save(str(OUT / f"{name}.png"))
        print(OUT / f"{name}.png")

    def screenplay():
        for node_id in ("pilot", "ch01", "storymap", ids["Mara Quinn"]):
            window.open_document(node_id)
        window.open_document("pilot")
        window.editors["pilot"].jump_to_line(22)
        window.show_outline()

    def prose():
        window.open_document("ch01")
        window.editors["ch01"].jump_to_line(2)
        window.side.setCurrentWidget(window.cast)
        window._refresh_cast()

    def story_bible():
        window.open_document(ids["Mara Quinn"])
        window.editors[ids["Mara Quinn"]].refresh_appearances()
        window.editors[ids["Mara Quinn"]].inputs["description"].setCursorPosition(0)

    def board():
        window.side.hide()  # a mind map wants the room
        window.open_document("storymap")
        settle(app)  # the board fits itself to the view when first shown; zoom in after that
        board = window.editors["storymap"]
        settle(app)
        board.centerOn(board.scene().itemsBoundingRect().center())

    def corkboard():
        window.open_corkboard("manuscript")

    def split():
        window.open_document("ch01")
        window.open_document("pilot")
        window.open_document(ids["Mara Quinn"])
        window.split(Qt.Orientation.Horizontal)
        window.editors[ids["Mara Quinn"]].inputs["description"].setCursorPosition(0)
        window.tabs.setCurrentWidget(window.editors["pilot"])
        window.editors["pilot"].jump_to_line(14)
        window.show_outline()

    shoot("screenplay", screenplay)
    shoot("prose", prose)
    shoot("story-bible", story_bible)
    shoot("board", board)
    shoot("corkboard", corkboard)
    shoot("split", split)

    window.close()
    QSettings().clear()
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main(set(sys.argv[1:]))
