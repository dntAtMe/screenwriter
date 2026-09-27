from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QInputDialog, QMessageBox

from conftest import dispose
from screenwriter import comments as notes
from screenwriter.comments import Comment, Reply

TEXT = "The boat came. The boat left. Mara watched the boat."


def test_finding_the_words_again():
    start = TEXT.index("The boat left")
    c = Comment.new("ch1", TEXT, start, start + len("The boat"), "Anna", "Which boat?")
    assert c.quote == "The boat" and c.find(TEXT) == (start, start + 8)  # the second of two identical quotes
    edited = "Rain.\n\n" + TEXT.replace("came", "arrived")
    shift = edited.index("The boat left")
    assert c.find(edited) == (shift, shift + 8)
    assert c.find(TEXT.replace("The boat left", "It left")) != (start, start + 8)  # falls back to another "The boat"
    assert c.find("Nothing like it.") is None


def _dump(*comments):
    return notes.dump(list(comments))


def test_merging_two_peoples_comments():
    base_c = Comment("c1", "ch1", "boat", "Anna", "Which boat?", "2026-01-01T10:00:00+00:00")
    ours = Comment.from_dict(base_c.to_dict())
    ours.replies.append(Reply("r1", "Ben", "The supply boat.", "2026-01-01T10:05:00+00:00"))
    theirs = Comment.from_dict(base_c.to_dict())
    theirs.replies.append(Reply("r2", "Anna", "Ah.", "2026-01-01T10:06:00+00:00"))
    theirs.resolved, theirs.resolved_by = True, "Anna"
    new_theirs = Comment("c2", "ch1", "Mara", "Anna", "Older?", "2026-01-01T11:00:00+00:00")
    gone = Comment("c3", "ch1", "left", "Ben", "Cut?", "2026-01-01T09:00:00+00:00")

    merged = {c.id: c for c in notes.parse(notes.merge(_dump(base_c, gone), _dump(ours, gone), _dump(theirs, new_theirs)))}
    assert set(merged) == {"c1", "c2"}  # they deleted c3 (untouched here): gone for both
    assert [r.id for r in merged["c1"].replies] == ["r1", "r2"]  # both replies kept, in order
    assert merged["c1"].resolved and merged["c1"].resolved_by == "Anna"  # resolved on one side


def test_comments_in_the_window(qapp, sample_project, monkeypatch):
    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.person_name = lambda: "Anna"
    w.open_project(sample_project)
    w.open_document("ch01")
    ed = w.editors["ch01"]
    start = ed.text().index("Skerry Rock")
    cursor = ed.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(start + len("Skerry Rock"), QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(cursor)
    monkeypatch.setattr(QInputDialog, "getMultiLineText", staticmethod(lambda *a, **k: ("Real place?", True)))
    w.add_comment()

    [c] = notes.load(sample_project)
    assert (c.quote, c.text, c.author, c.doc) == ("Skerry Rock", "Real place?", "Anna", "ch01")
    assert ed.comment_spans() == [(start, start + 11, c.id)]
    styles = [r.format.background().color().alpha() for r in ed.document().findBlock(start).layout().formats()
              if r.start <= start - ed.document().findBlock(start).position() < r.start + r.length]
    assert any(a > 0 for a in styles)  # tinted
    assert w.side.currentWidget() is w.comments_panel and w.comments_panel.cards.count() == 2  # card + stretch

    # the comment follows its words as the text around them changes
    c0 = ed.textCursor()
    c0.setPosition(0)
    c0.insertText("Prologue.\n\n")
    w.save_all()
    [c] = notes.load(sample_project)
    assert c.pos == start + len("Prologue.\n\n") and c.quote == "Skerry Rock"

    w.reply_to_comment(c.id, "Yes, off Shetland.")
    assert notes.load(sample_project)[0].replies[0].text == "Yes, off Shetland."
    w.resolve_comment(c.id, True)
    assert notes.load(sample_project)[0].resolved and ed.comment_spans() == []  # resolved: no tint, hidden
    assert w.comments_panel.cards.count() == 1  # (just the stretch)
    w.comments_panel.show_resolved.setChecked(True)
    assert w.comments_panel.cards.count() == 2
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    w.delete_comment(c.id)
    assert notes.load(sample_project) == [] and not (sample_project / notes.COMMENTS_FILE).exists()
    dispose(w)


def test_comments_arrive_by_sync(qapp, tmp_path, monkeypatch):
    import shutil

    from conftest import SAMPLE
    from test_mainwindow import MainWindow, _two_live_windows

    QSettings().clear()
    shutil.copytree(SAMPLE, tmp_path / "anna", ignore=shutil.ignore_patterns("snapshots", "*.tmp"))
    anna = MainWindow()
    anna.open_project(tmp_path / "anna")
    anna, ben = _two_live_windows(anna, tmp_path, monkeypatch)
    for w in (anna, ben):
        w.live.enabled = False  # comments come by sync, not live editing
    b = ben.editors["ch01"]
    start = b.text().index("Thursday")
    cursor = b.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(start + 8, QTextCursor.MoveMode.KeepAnchor)
    b.setTextCursor(cursor)
    monkeypatch.setattr(QInputDialog, "getMultiLineText", staticmethod(lambda *a, **k: ("Why Thursday?", True)))
    ben.add_comment()
    ben.sync_now(quiet=True)
    anna.sync_now(quiet=True)
    [c] = anna.comments
    assert c.author == "Ben" and "New comment from Ben" in anna.statusBar().currentMessage()
    assert [i for _, _, i in anna.editors["ch01"].comment_spans()] == [c.id]
    anna.reply_to_comment(c.id, "It's the plot.")
    anna.sync_now(quiet=True)
    ben.sync_now(quiet=True)
    assert [r.text for r in ben.comments[0].replies] == ["It's the plot."]
    dispose(ben)
    dispose(anna)
