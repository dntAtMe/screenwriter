"""A readable word-level diff of two texts, as HTML (History and the history dialog use it)."""

from __future__ import annotations

import difflib
import html
import re

TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]")


def _words(old: str, new: str) -> str:
    a, b = TOKEN_RE.findall(old), TOKEN_RE.findall(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(html.escape("".join(a[i1:i2])))
        if op in ("delete", "replace"):
            out.append(f'<span class="del">{html.escape("".join(a[i1:i2]))}</span>')
        if op in ("insert", "replace"):
            out.append(f'<span class="ins">{html.escape("".join(b[j1:j2]))}</span>')
    return "".join(out)


def diff_html(old: str, new: str, context: int = 2) -> str:
    """Changes from old to new as HTML: changed lines with word-level
    <span class="del">/<span class="ins">,
    a little unchanged context around them, and '⋯' for skipped stretches."""
    if old == new:
        return '<p class="same">No changes.</p>'
    a, b = old.splitlines(), new.splitlines()
    rows: list[str] = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for group in matcher.get_grouped_opcodes(context):
        if rows:
            rows.append('<p class="gap">⋯</p>')
        for op, i1, i2, j1, j2 in group:
            if op == "equal":
                rows += [f'<p class="same">{html.escape(line) or "&nbsp;"}</p>' for line in a[i1:i2]]
            elif op == "replace" and i2 - i1 == j2 - j1:
                rows += [f'<p class="changed">{_words(x, y) or "&nbsp;"}</p>' for x, y in zip(a[i1:i2], b[j1:j2])]
            elif op == "replace":
                rows.append(f'<p class="changed">{_words(chr(10).join(a[i1:i2]), chr(10).join(b[j1:j2])).replace(chr(10), "<br>")}</p>')
            elif op == "delete":
                rows += [f'<p class="changed"><span class="del">{html.escape(line) or "&nbsp;"}</span></p>' for line in a[i1:i2]]
            elif op == "insert":
                rows += [f'<p class="changed"><span class="ins">{html.escape(line) or "&nbsp;"}</span></p>' for line in b[j1:j2]]
    return "\n".join(rows)


DIFF_CSS = """
p { margin: 0 0 6px 0; }
p.same { color: gray; }
p.gap { color: gray; text-align: center; }
.del { background-color: #f6c9c9; color: #7a1c1c; text-decoration: line-through; }
.ins { background-color: #c9ecc9; color: #1b5a1b; }
"""
