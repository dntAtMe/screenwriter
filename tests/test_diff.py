from screenwriter.diff import diff_html


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
