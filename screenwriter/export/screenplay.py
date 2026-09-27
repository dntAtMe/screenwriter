"""Screenplay export: paginated industry-standard PDF and Final Draft (.fdx).

Layout follows the usual US spec: Courier 12pt (10 characters and 6 lines per
inch), 1.5" left margin, 1" right/top/bottom, page numbers top right from page 2.
Scene headings are kept with what follows; dialogue split across pages gets
(MORE) and (CONT'D); long action paragraphs may break between lines.
**Bold**, *italic* and _underline_ print as such (and are kept in .fdx).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

from ..marks import strip_marks
from ..fountain import EXTENSION_RE, El, parse, title_page

# (indent, width) in characters from the left margin, on a 60-character line
COLUMNS = {
    El.SCENE: (0, 60),
    El.ACTION: (0, 60),
    El.CHARACTER: (22, 38),
    El.PARENTHETICAL: (16, 25),
    El.DIALOGUE: (10, 35),
    El.TRANSITION: (0, 60),
    El.CENTERED: (0, 60),
}
PRINTED = set(COLUMNS)
DIALOGUE_PARTS = (El.PARENTHETICAL, El.DIALOGUE)
MORE = "(MORE)"

EMPHASIS_RE = re.compile(r"(?<!\\)(\*{1,3}|_)(?=\S)(.+?)(?<=[^\s\\])\1")  # \* and \_ are literal
NOTE_RE = re.compile(r"\[\[.*?\]\]")


BOLD, ITALIC, UNDERLINE = 1, 2, 4
MARK_STYLES = {"*": ITALIC, "**": BOLD, "***": BOLD | ITALIC, "_": UNDERLINE}


class Styled(str):
    """Printable text that remembers each character's style (BOLD | ITALIC | UNDERLINE bits).
    Slicing, stripping and upper() keep the styles; other str methods return plain str."""

    styles: tuple[int, ...]

    def __new__(cls, text: str, styles=None):
        obj = super().__new__(cls, text)
        obj.styles = tuple(styles) if styles is not None and len(styles) == len(text) else (0,) * len(text)
        return obj

    def __getitem__(self, key):
        if isinstance(key, slice) and key.step in (None, 1):
            start, stop, _ = key.indices(len(self))
            return Styled(str.__getitem__(self, key), self.styles[start:max(start, stop)])
        return str.__getitem__(self, key)

    def lstrip(self, chars=None):
        return self[len(self) - len(str.lstrip(self, chars)):]

    def rstrip(self, chars=None):
        return self[: len(str.rstrip(self, chars))]

    def strip(self, chars=None):
        return self.lstrip(chars).rstrip(chars)

    def upper(self):
        return Styled(str.upper(self), self.styles)  # styles dropped if the length changes (ß → SS)


def runs(s: str) -> list[tuple[int, str, int]]:
    """(offset, text, style) for each stretch of one style; plain text is one run."""
    styles = getattr(s, "styles", None) or (0,) * len(s)
    out: list[tuple[int, str, int]] = []
    for i, (ch, style) in enumerate(zip(s, styles)):
        if out and out[-1][2] == style:
            out[-1] = (out[-1][0], out[-1][1] + ch, style)
        else:
            out.append((i, ch, style))
    return out


def emphasis(text: str) -> Styled:
    """Take out **bold**, *italic* and _underline_ marks (nested ones too), remembering what they covered."""
    chars, styles = list(text), [0] * len(text)
    while m := EMPHASIS_RE.search("".join(chars)):
        mark, (a, b) = m.group(1), m.span()
        for i in range(a + len(mark), b - len(mark)):
            styles[i] |= MARK_STYLES[mark]
        del chars[b - len(mark):b], styles[b - len(mark):b]
        del chars[a:a + len(mark)], styles[a:a + len(mark)]
    i = 0
    while i < len(chars) - 1:  # \* and \_ print as themselves
        if chars[i] == "\\" and chars[i + 1] in "*_":
            del chars[i], styles[i]
        i += 1
    return Styled("".join(chars), styles)


def clean(text: str, el: El) -> Styled:
    """Printable text for one line: no notes, emphasis marks or forcing marks."""
    s = emphasis(strip_marks(NOTE_RE.sub("", text)).strip())  # marks print as their phrase
    if el == El.CENTERED:
        s = s.lstrip(">").rstrip("<").strip()
    elif s[:1] in ".!@>" and not s.startswith("..") and el in (El.SCENE, El.ACTION, El.CHARACTER, El.TRANSITION):
        s = s[1:].lstrip()
    if el in (El.SCENE, El.TRANSITION):
        s = s.upper()
    if el == El.CHARACTER:
        s = s.rstrip("^ ").strip()
    return s


@dataclass
class Block:
    """One printed element: a scene heading, an action paragraph, a whole speech…"""
    kind: El
    lines: list[tuple[El, str]] = field(default_factory=list)  # (element, source text) before wrapping


def blocks(text: str) -> tuple[dict[str, str], list[Block]]:
    lines = parse(text)
    out: list[Block] = []
    prev = None
    for source, el in lines:
        if el not in PRINTED:
            prev = el
            continue
        s = clean(source, el)
        if not s:
            prev = el
            continue
        joins_speech = el in DIALOGUE_PARTS and out and out[-1].kind == El.CHARACTER and prev in (El.CHARACTER,) + DIALOGUE_PARTS
        joins_action = el == El.ACTION and prev == El.ACTION and out and out[-1].kind == El.ACTION
        if joins_speech or joins_action:
            out[-1].lines.append((el, s))
        else:
            out.append(Block(el, [(el, s)]))
        prev = el
    return title_page(lines), out


def wrap_line(s: str, width: int) -> list[str]:
    """Break a line into pieces of at most `width` characters with textwrap's algorithm
    (textwrap.wrap(break_on_hyphens=False)), but by slicing `s`, so a Styled line stays styled."""
    chunks = [list(m.span()) for m in re.finditer(r"\s+|\S+", s)][::-1]  # words and spaces, next one last
    is_space = lambda c: not str.strip(s[c[0]:c[1]])
    out = []
    while chunks:
        line, used = [], 0
        if out and is_space(chunks[-1]):
            chunks.pop()  # no spaces at the start of a line after the first
        while chunks and used + chunks[-1][1] - chunks[-1][0] <= width:
            line.append(chunks.pop())
            used += line[-1][1] - line[-1][0]
        if chunks and chunks[-1][1] - chunks[-1][0] > width:  # a word longer than a line fills this one
            cut = chunks[-1][0] + (width - used if width >= 1 else 1)
            if cut > chunks[-1][0]:  # no empty piece: older textwraps kept a trailing space that way
                line.append([chunks[-1][0], cut])
                chunks[-1][0] = cut
        if line and is_space(line[-1]):
            line.pop()
        if line:
            out.append(s[line[0][0]:line[-1][1]])
    return out


def wrap(block: Block) -> list[tuple[El, str]]:
    printed = []
    for el, s in block.lines:
        _, width = COLUMNS[el]
        printed += [(el, line) for line in wrap_line(s, width) or [s[:0]]]
    return printed


def paginate(text: str, lines_per_page: int = 54) -> tuple[dict[str, str], list[list[tuple[El, str] | None]]]:
    """Pages of printed lines; None is a blank line."""
    fields, script = blocks(text)
    pages: list[list] = [[]]

    def room() -> int:
        return lines_per_page - len(pages[-1])

    def new_page() -> None:
        pages.append([])

    def put(lines: list, gap: bool) -> None:
        if gap and pages[-1]:
            pages[-1].append(None)
        pages[-1].extend(lines)

    for i, block in enumerate(script):
        lines = wrap(block)
        while lines:
            gap = 1 if pages[-1] else 0
            need = gap + len(lines)
            if block.kind == El.SCENE and i + 1 < len(script):
                need += 1 + min(2, len(wrap(script[i + 1])))  # keep with the next element
            if need <= room() or (not pages[-1] and len(lines) <= lines_per_page):
                put(lines, gap)
                break
            avail = room() - gap
            if block.kind == El.ACTION and avail >= 2 and len(lines) - avail >= 2:
                put(lines[:avail], gap)
                lines = lines[avail:]
                new_page()
                continue
            if block.kind == El.CHARACTER and avail >= 4 and len(lines) > avail:
                cut = avail - 1  # leave a line for (MORE)
                while cut > 2 and lines[cut - 1][0] == El.PARENTHETICAL:
                    cut -= 1  # never end a page on a parenthetical
                if cut >= 2:
                    cue = lines[0][1]
                    name = EXTENSION_RE.sub("", cue).strip()
                    put(lines[:cut] + [(El.CHARACTER, MORE)], gap)
                    lines = [(El.CHARACTER, f"{name} (CONT'D)")] + lines[cut:]
                    new_page()
                    continue
            if not pages[-1]:  # taller than a page: hard split
                put(lines[:lines_per_page], False)
                lines = lines[lines_per_page:]
            new_page()
    if not pages[-1] and len(pages) > 1:
        pages.pop()
    return fields, pages


# --- PDF ------------------------------------------------------------------------------


def write_pdf(text: str, path: str, paper: str = "Letter", fallback_title: str = "") -> int:
    """Write the script as a PDF; returns the number of script pages."""
    from PySide6.QtCore import QMarginsF, QPointF
    from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPainter, QPdfWriter

    from ..editors.common import first_available_font

    size = QPageSize(QPageSize.PageSizeId.A4 if paper == "A4" else QPageSize.PageSizeId.Letter)
    height_pt = size.sizePoints().height()
    lines_per_page = int((height_pt - 144) // 12)
    fields, pages = paginate(text, lines_per_page)

    writer = QPdfWriter(path)
    writer.setPageLayout(QPageLayout(size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))
    writer.setResolution(72)  # one unit = one point
    writer.setTitle(fields.get("title", "").replace("\n", " ") or fallback_title)
    writer.setCreator("Screenwriter")

    painter = QPainter(writer)
    font = QFont(first_available_font("Courier Prime", "Courier New", "Courier"))
    font.setPointSizeF(12)
    painter.setFont(font)
    ascent = painter.fontMetrics().ascent()
    left, top, cw, lh = 108.0, 72.0, 7.2, 12.0
    page_width = size.sizePoints().width()
    fonts: dict[int, QFont] = {}

    def font_for(style: int) -> QFont:
        if style not in fonts:
            fonts[style] = styled = QFont(font)
            styled.setBold(bool(style & BOLD))
            styled.setItalic(bool(style & ITALIC))
            styled.setUnderline(bool(style & UNDERLINE))
        return fonts[style]

    def draw(x: float, y: float, s: str) -> None:
        # each run at its own column, so a bold or italic face can't shift the monospaced layout
        for offset, text, style in runs(s):
            painter.setFont(font_for(style))
            painter.drawText(QPointF(x + offset * cw, y + ascent), text)

    if fields:
        _draw_title_page(fields, draw, left, cw, lh, page_width, height_pt)
        writer.newPage()

    for number, page in enumerate(pages, start=1):
        if number > 1:
            writer.newPage()
            num = f"{number}."
            draw(page_width - 72 - len(num) * cw, 36, num)
        y = top
        for line in page:
            if line is not None:
                el, s = line
                indent, _ = COLUMNS[el]
                if el == El.TRANSITION:
                    x = left + (60 - len(s)) * cw
                elif el == El.CENTERED:
                    x = left + (60 - len(s)) / 2 * cw
                else:
                    x = left + indent * cw
                draw(x, y, s)
            y += lh
    painter.end()
    return len(pages)


def _draw_title_page(fields, draw, left, cw, lh, page_width, page_height) -> None:
    center = lambda s: (page_width - len(s) * cw) / 2
    y = page_height * 0.35
    for key in ("title", "credit", "author", "authors", "source"):
        if key not in fields:
            continue
        for s in fields[key].splitlines():
            s = s.upper() if key == "title" else s
            s = EMPHASIS_RE.sub(r"\2", s)
            draw(center(s), y, s)
            y += lh
        y += lh * (2 if key == "title" else 1)
    bottom = page_height - 72 - lh * 4
    for key, align_right in (("contact", False), ("draft date", True), ("date", True), ("copyright", False)):
        if key in fields:
            for j, s in enumerate(fields[key].splitlines()):
                x = page_width - 72 - len(s) * cw if align_right else left
                draw(x, bottom + j * lh, s)


# --- Final Draft ----------------------------------------------------------------------------

FDX_TYPES = {
    El.SCENE: "Scene Heading",
    El.ACTION: "Action",
    El.CHARACTER: "Character",
    El.PARENTHETICAL: "Parenthetical",
    El.DIALOGUE: "Dialogue",
    El.TRANSITION: "Transition",
    El.CENTERED: "Action",
}


def fdx_text(s: str) -> str:
    """<Text> elements for a line, one per stretch of one style (Style="Bold+Underline")."""
    parts = []
    for _, text, style in runs(s):
        names = "+".join(name for flag, name in ((BOLD, "Bold"), (ITALIC, "Italic"), (UNDERLINE, "Underline")) if style & flag)
        parts.append(f"<Text{' Style=' + quoteattr(names) if names else ''}>{escape(text)}</Text>")
    return "".join(parts) or "<Text></Text>"


def to_fdx(text: str) -> str:
    fields, script = blocks(text)
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="no" ?>',
           '<FinalDraft DocumentType="Script" Template="No" Version="5">', "  <Content>"]
    for block in script:
        for el, s in block.lines:
            align = ' Alignment="Center"' if el == El.CENTERED else ""
            out.append(f"    <Paragraph Type={quoteattr(FDX_TYPES[el])}{align}>{fdx_text(s)}</Paragraph>")
    out.append("  </Content>")
    if fields:
        out += ["  <TitlePage>", "    <Content>"]
        for key in ("title", "credit", "author", "authors", "source", "draft date", "contact"):
            for s in fields.get(key, "").splitlines():
                out.append(f'      <Paragraph Alignment="Center"><Text>{escape(s)}</Text></Paragraph>')
        out += ["    </Content>", "  </TitlePage>"]
    out.append("</FinalDraft>")
    return "\n".join(out) + "\n"
