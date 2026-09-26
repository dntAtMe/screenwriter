from datetime import datetime

from screenwriter.capture import append_idea, format_idea
from screenwriter.project import NOTE, Project
from screenwriter.search import find_hits

WHEN = datetime(2026, 9, 26, 14, 3)


def test_format_idea():
    assert format_idea("A ghost ship\nseen only in fog", WHEN) == "- A ghost ship _(26 Sep 2026, 14:03)_\n  seen only in fog"


def test_append_idea_continues_list():
    assert append_idea("# Ideas\n\n- one\n", "- two") == "- two\n"
    assert append_idea("# Ideas\n\n- one", "- two") == "\n- two\n"


def test_append_idea_after_heading():
    assert append_idea("# Ideas\n", "- one") == "\n- one\n"
    assert append_idea("# Ideas\n\n", "- one") == "- one\n"
    assert append_idea("", "- one") == "- one\n"


def test_find_hits():
    text = "The fog came.\nFog again, and more fog.\n"
    hits = find_hits(text, "fog")
    assert [(h.line, h.pos) for h in hits] == [(0, 4), (1, 14), (1, 34)]
    assert hits[1].snippet == "Fog again, and more fog."
    assert [h.line for h in find_hits(text, "Fog", case_sensitive=True)] == [1]


def test_ensure_inbox(tmp_path):
    project = Project.create(tmp_path / "P", "P")
    inbox, created = project.ensure_inbox()
    assert created and inbox.kind == NOTE and project.root[-2] is inbox
    again, created = project.ensure_inbox()
    assert again.id == inbox.id and not created
    assert Project.open(tmp_path / "P").inbox_id == inbox.id
