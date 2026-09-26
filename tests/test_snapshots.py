from datetime import date, datetime

from screenwriter.snapshots import AUTO_NAME, SnapshotStore, diff_html


def test_store(tmp_path):
    store = SnapshotStore(tmp_path)
    assert store.list("doc") == []
    first = store.take("doc", "one", ".md", when=datetime(2026, 9, 25, 10, 0, 0))
    named = store.take("doc", "two", ".md", "Before rewrite", when=datetime(2026, 9, 26, 9, 30, 0))
    same_second = store.take("doc", "three", ".md", when=datetime(2026, 9, 26, 9, 30, 0))
    snaps = store.list("doc")
    assert [s.text() for s in snaps] == ["three", "two", "one"]
    assert snaps[1].label == "Before rewrite — 26 Sep 2026, 09:30"
    assert same_second.path.name == "20260926-093000-1.md"
    assert store.has_snapshot_on("doc", date(2026, 9, 26)) and not store.has_snapshot_on("doc", date(2026, 9, 24))
    store.delete("doc", named)
    assert [s.text() for s in store.list("doc")] == ["three", "one"]
    store.delete_all("doc")
    assert store.list("doc") == [] and first.path.parent.exists() is False


def test_diff_html():
    old = "# Chapter\n\nShe walked to the sea.\nThe end."
    new = "# Chapter\n\nShe ran to the sea.\nThe end.\nA new line."
    out = diff_html(old, new)
    assert '<span class="del">walked</span><span class="ins">ran</span>' in out
    assert '<span class="ins">A new line.</span>' in out
    assert "&lt;" not in diff_html("a", "a") and "No changes" in diff_html("a", "a")
    assert "&lt;b&gt;" in diff_html("x", "<b>")


def test_diff_skips_unchanged_stretches():
    old = "\n".join(f"line {i}" for i in range(50))
    new = old.replace("line 5\n", "line five\n").replace("line 45", "line forty-five")
    out = diff_html(old, new)
    assert "⋯" in out and "line 25" not in out
