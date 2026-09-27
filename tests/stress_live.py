"""Stress test for live editing: two windows typing into one document at once.

Two real main windows (one process, offscreen) share a project through a folder, both
open the same document, and type numbered words ("a1 a2…" and "b1 b2…") at random spots,
a few characters at a time, with live ticks, autosaves and syncs in between in random
order. Afterwards both copies must be identical, every typed character must be there
exactly once, and (unless SIM_SPOT=1 lets them type into the very same spot) every word
must be intact.

    uv run python tests/stress_live.py [document id] [runs] [steps]
    SIM_SYNC=0   live editing only, no syncs in between
    SIM_SPOT=1   allow typing at the very spot the other is typing (checks characters only)

Not part of the normal test run: it takes a few minutes.
"""

import os
import random
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication([])
app.setOrganizationName("LiveSim")
app.setApplicationName(f"LiveSim{os.getpid()}")  # own settings per process
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)

from screenwriter.mainwindow import MainWindow
from screenwriter.sync import package_name
from screenwriter.synctargets import FolderTarget

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "The Lighthouse"
SYNC = os.environ.get("SIM_SYNC", "1") == "1"
TRACE = os.environ.get("SIM_TRACE") == "1"
SPOT = os.environ.get("SIM_SPOT") == "1"  # allow typing at the very spot the other is typing
WORD = re.compile(r"(?<![A-Za-z0-9])([ab])(\d+)(?!\d)")  # a typed word, even with text right after it


def run(seed: int, steps: int, doc: str, verbose=False):
    rng = random.Random(seed)
    root = Path(tempfile.mkdtemp())
    shutil.copytree(SAMPLE, root / "anna", ignore=shutil.ignore_patterns(".history"))
    (root / "net").mkdir()
    QSettings().clear()
    anna = MainWindow()
    anna.person_name = lambda: "Anna"
    anna.open_project(root / "anna")
    anna.history.person = "Anna"
    package = root / "net" / package_name(anna.project.name)
    anna._set_target(FolderTarget(package))
    anna.sync_now(quiet=True)
    anna.settings.remove(f"sync_local/{anna.project.id}")
    ben = MainWindow()
    ben.person_name = lambda: "Ben"
    ben.open_project_file(str(package), str(root / "ben"), keep_synced=True)
    ben.history.person = "Ben"
    windows = {"a": anna, "b": ben}
    for w in windows.values():
        for t in (w.live.timer, w.sync_timer, w.presence_timer, w.save_timer, w.quick_sync_timer, w.history_timer):
            t.stop()
        w.open_document(doc)
    for w in (anna, ben, anna):
        w._check_people()
    counter = {"a": 0, "b": 0}
    log = []
    initial = Counter(anna.editors[doc].text())
    typed_chars = Counter()
    chunks = []

    def type_word(key):
        w = windows[key]
        e = w.editors[doc]
        text = e.text()
        counter[key] += 1
        word = f"{key}{counter[key]}"
        c = e.textCursor()
        r = rng.random()
        if r < 0.5:  # keep typing where the cursor is
            pos = c.position()
        elif r < 0.8:  # end of a random paragraph
            ends = [m.start() for m in re.finditer(r"\n", text)] + [len(text)]
            pos = rng.choice(ends)
        else:  # a new paragraph somewhere
            ends = [m.start() for m in re.finditer(r"\n", text)] + [len(text)]
            pos = rng.choice(ends)
            word = "\n\n" + word
        if not SPOT:  # people type in different places: not on the line the other is on
            other = windows["b" if key == "a" else "a"].editors[doc]
            other_line = other.textCursor().block().text()
            p0 = min(pos, len(text))
            line_start = text.rfind("\n", 0, p0) + 1
            line_end = text.find("\n", p0)
            line = text[line_start:line_end if line_end >= 0 else len(text)]
            if line == other_line:
                pos = len(text)
                if not word.startswith("\n"):
                    word = "\n\n" + word
        c.setPosition(min(pos, len(text)))
        e.setTextCursor(c)
        # type it a few characters at a time, like a person
        chunk = " " + word if not word.startswith("\n") else word
        typed_chars.update(chunk)
        chunks.append((key, chunk))
        i = 0
        while i < len(chunk):
            n = rng.randint(1, 3)
            before = e.text()
            typing = e.textCursor()
            typing.insertText(chunk[i:i + n])
            e.setTextCursor(typing)  # like a keyboard: the cursor moves on
            if TRACE:
                grew = len(e.text()) - len(before)
                if grew != len(chunk[i:i + n]):
                    print(f"    !!! {key} typed {chunk[i:i+n]!r} but text grew by {grew}: {before[:40]!r} -> {e.text()[:40]!r}")
            i += n
            if rng.random() < 0.3:
                event(rng.choice("ab"), typing=True)
        log.append(f"{key} typed {word!r}")
        if TRACE:
            print(f"  {key} typed {word!r}; in own text: {bool(re.search(rf'{word.strip()}', e.text()))}")

    def event(key, typing=False):
        w = windows[key]
        r = rng.random()
        if r < 0.55:
            if TRACE: print(f"    tick {key}")
            w.live.tick()
        elif r < 0.75:
            w.save_all()
        elif r < 0.88 and not typing and SYNC:
            w.sync_now(quiet=True)
        elif r < 0.95:
            w._check_people()
        elif SYNC:
            w._check_cloud()

    for _ in range(steps):
        if rng.random() < 0.45:
            type_word(rng.choice("ab"))
        else:
            event(rng.choice("ab"))

    # settle: live ticks and syncs until both agree
    for _ in range(12):
        for w in (anna, ben):
            w.live.tick()
        for w in (anna, ben):
            w.live.tick()
    for _ in range(3 if SYNC else 0):
        for w in (anna, ben):
            w.sync_now(quiet=True)
            w.live.tick()
    ta, tb = anna.editors[doc].text(), ben.editors[doc].text()
    problems = []
    if ta != tb:
        problems.append("DIVERGED")
    for name, text in (("anna", ta), ("ben", tb)):
        counts = Counter(m.group(0) for m in WORD.finditer(text))
        dups = sorted(k for k, v in counts.items() if v > 1)
        typed = {f"{k}{i}" for k in "ab" for i in range(1, counter[k] + 1)}
        missing = sorted(typed - set(counts))
        if dups:
            problems.append(f"{name} DUPLICATES {dups}")
        if missing:
            problems.append(f"{name} MISSING {missing}")
    extra = Counter(ta) - initial
    if typed_chars - extra:
        problems.append(f"LOST CHARS {dict(typed_chars - extra)}")
        problems.append("CHUNKS NOT INTACT " + repr([c for k, c in chunks if c not in ta]))
    if extra - typed_chars:
        problems.append(f"EXTRA CHARS {dict(extra - typed_chars)}")
    if SPOT:  # interleaving at the very same spot is allowed there; every character must be there once
        problems = [p for p in problems if "MISSING" not in p and "DUPLICATES" not in p]
    conflicts = len(__import__("screenwriter.merge", fromlist=["x"]).load_conflicts(anna.project.path))
    for w in (anna, ben):
        w.close()
    shutil.rmtree(root, ignore_errors=True)
    return problems, conflicts, counter, (ta, tb) if problems and verbose else None


if __name__ == "__main__":
    doc = sys.argv[1] if len(sys.argv) > 1 else "ch01"
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    bad = 0
    for seed in range(seeds):
        problems, conflicts, counter, texts = run(seed, steps, doc, verbose=True)
        status = "OK " if not problems else "BAD"
        bad += bool(problems)
        print(f"{status} seed={seed} typed={counter} conflicts={conflicts} {'; '.join(problems)}", flush=True)
        if texts and bad <= 2:
            print("  ANNA:", repr(texts[0][-400:]))
            print("  BEN: ", repr(texts[1][-400:]))
    print(f"{bad}/{seeds} bad")
