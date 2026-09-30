"""The app's icons, drawn in code: crisp at any size and in any colour.

Outline icons on a 24-unit grid (the style of Lucide / Feather), so they can follow
the light or dark theme and each document kind can have its own colour.

    icon("search")                      # theme's muted ink
    icon("prose", "#4f7cac")            # a colour of its own
    icon_file("chevron-down", "#888")  # a PNG path, for stylesheets
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

STROKE = 1.8
Draw = Callable[[QPainter], None]
_DRAWINGS: dict[str, Draw] = {}


def drawing(name: str):
    def register(fn: Draw) -> Draw:
        _DRAWINGS[name] = fn
        return fn

    return register


def names() -> list[str]:
    return sorted(_DRAWINGS)


def _path(*points: tuple[float, float], close: bool = False) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for p in points[1:]:
        path.lineTo(QPointF(*p))
    if close:
        path.closeSubpath()
    return path


def _round_rect(p: QPainter, x, y, w, h, r) -> None:
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


# --- document kinds -----------------------------------------------------------------------


@drawing("prose")
def _prose(p: QPainter) -> None:  # a page with lines of text
    p.drawPath(_path((6, 3), (14, 3), (19, 8), (19, 21), (6, 21), close=True))
    p.drawPath(_path((14, 3), (14, 8), (19, 8)))
    for y, x2 in ((12, 16), (15, 16), (18, 13)):
        p.drawLine(QPointF(9, y), QPointF(x2, y))


@drawing("screenplay")
def _screenplay(p: QPainter) -> None:  # a clapperboard
    _round_rect(p, 3, 9, 18, 12, 2)
    p.drawPath(_path((3, 9), (4.2, 4.2), (19.8, 4.2), (21, 9)))
    p.drawLine(QPointF(8.5, 4.4), QPointF(7, 8.8))
    p.drawLine(QPointF(14, 4.4), QPointF(12.5, 8.8))


@drawing("note")
def _note(p: QPainter) -> None:  # a sticky note with a folded corner
    p.drawPath(_path((4, 4), (20, 4), (20, 15), (15, 20), (4, 20), close=True))
    p.drawPath(_path((20, 15), (15, 15), (15, 20)))


@drawing("board")
def _board(p: QPainter) -> None:  # three linked cards
    _round_rect(p, 2.5, 9, 7, 6, 1.5)
    _round_rect(p, 14.5, 3.5, 7, 6, 1.5)
    _round_rect(p, 14.5, 14.5, 7, 6, 1.5)
    path = QPainterPath(QPointF(9.5, 12))
    path.cubicTo(QPointF(12, 12), QPointF(12, 6.5), QPointF(14.5, 6.5))
    path.moveTo(9.5, 12)
    path.cubicTo(QPointF(12, 12), QPointF(12, 17.5), QPointF(14.5, 17.5))
    p.drawPath(path)


@drawing("character")
def _character(p: QPainter) -> None:  # a person
    p.drawEllipse(QPointF(12, 8), 4, 4)
    path = QPainterPath(QPointF(4.5, 21))
    path.cubicTo(QPointF(4.5, 15.5), QPointF(8, 13.5), QPointF(12, 13.5))
    path.cubicTo(QPointF(16, 13.5), QPointF(19.5, 15.5), QPointF(19.5, 21))
    p.drawPath(path)


@drawing("location")
def _location(p: QPainter) -> None:  # a map pin
    path = QPainterPath(QPointF(12, 21.5))
    path.cubicTo(QPointF(12, 21.5), QPointF(4.5, 14.5), QPointF(4.5, 9.5))
    path.arcTo(QRectF(4.5, 2, 15, 15), 180, -180)
    path.cubicTo(QPointF(19.5, 14.5), QPointF(12, 21.5), QPointF(12, 21.5))
    p.drawPath(path)
    p.drawEllipse(QPointF(12, 9.5), 2.6, 2.6)


@drawing("faction")
def _faction(p: QPainter) -> None:  # a banner on a pole
    p.drawLine(QPointF(5, 21), QPointF(5, 3))
    p.drawPath(_path((5, 4), (19, 4), (16, 8.5), (19, 13), (5, 13)))


@drawing("item")
def _item(p: QPainter) -> None:  # a cut gem
    p.drawPath(_path((7, 4), (17, 4), (21, 9), (12, 20.5), (3, 9), close=True))
    p.drawLine(QPointF(3, 9), QPointF(21, 9))
    p.drawPath(_path((9.5, 4), (8, 9), (12, 20.5), (16, 9), (14.5, 4)))


@drawing("folder")
def _folder(p: QPainter) -> None:
    p.drawPath(_path((3, 6.5), (3, 19), (21, 19), (21, 8.5), (12.5, 8.5), (10.5, 5.5), (4, 5.5), (3, 6.5), close=True))


@drawing("trash")
def _trash(p: QPainter) -> None:
    p.drawLine(QPointF(3.5, 6.5), QPointF(20.5, 6.5))
    p.drawPath(_path((9, 6.5), (9, 3.5), (15, 3.5), (15, 6.5)))
    p.drawPath(_path((5.5, 6.5), (6.8, 20.5), (17.2, 20.5), (18.5, 6.5)))
    p.drawLine(QPointF(10, 10.5), QPointF(10, 16.5))
    p.drawLine(QPointF(14, 10.5), QPointF(14, 16.5))


# --- toolbar and UI -------------------------------------------------------------------------------


@drawing("plus")
def _plus(p: QPainter) -> None:
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


@drawing("search")
def _search(p: QPainter) -> None:
    p.drawEllipse(QPointF(10.5, 10.5), 6.5, 6.5)
    p.drawLine(QPointF(15.3, 15.3), QPointF(20.5, 20.5))


@drawing("history")
def _history(p: QPainter) -> None:  # a clock with a counter-clockwise arrow
    path = QPainterPath()
    path.arcMoveTo(QRectF(3.5, 3.5, 17, 17), 160)
    path.arcTo(QRectF(3.5, 3.5, 17, 17), 160, -330)
    p.drawPath(path)
    p.drawPath(_path((3.2, 5.6), (3.6, 9.6), (7.4, 8.8)))
    p.drawPath(_path((12, 7.5), (12, 12), (15, 14)))


@drawing("cloud")
def _cloud(p: QPainter) -> None:
    path = QPainterPath(QPointF(7, 19))
    path.cubicTo(QPointF(3.5, 19), QPointF(2, 16.5), QPointF(2.5, 14))
    path.cubicTo(QPointF(3, 11.5), QPointF(5.5, 10.2), QPointF(7.5, 10.6))
    path.cubicTo(QPointF(8.5, 6.5), QPointF(12, 5), QPointF(15, 6))
    path.cubicTo(QPointF(18, 7), QPointF(19.3, 9.6), QPointF(19, 12))
    path.cubicTo(QPointF(21.5, 12.5), QPointF(22.5, 15), QPointF(21.5, 17))
    path.cubicTo(QPointF(20.8, 18.4), QPointF(19.5, 19), QPointF(18, 19))
    path.closeSubpath()
    p.drawPath(path)


@drawing("sidebar-left")
def _sidebar_left(p: QPainter) -> None:
    _round_rect(p, 3, 4, 18, 16, 2.5)
    p.drawLine(QPointF(9, 4), QPointF(9, 20))


@drawing("sidebar-right")
def _sidebar_right(p: QPainter) -> None:
    _round_rect(p, 3, 4, 18, 16, 2.5)
    p.drawLine(QPointF(15, 4), QPointF(15, 20))


@drawing("focus")
def _focus(p: QPainter) -> None:  # four corners pulling outward
    for a, b, c in (((3, 8.5), (3, 3), (8.5, 3)), ((15.5, 3), (21, 3), (21, 8.5)),
                    ((21, 15.5), (21, 21), (15.5, 21)), ((8.5, 21), (3, 21), (3, 15.5))):
        p.drawPath(_path(a, b, c))


@drawing("share")
def _share(p: QPainter) -> None:  # a box with an arrow up
    p.drawPath(_path((8, 10), (5, 10), (5, 21), (19, 21), (19, 10), (16, 10)))
    p.drawLine(QPointF(12, 3), QPointF(12, 15))
    p.drawPath(_path((8, 7), (12, 3), (16, 7)))


@drawing("comment")
def _comment(p: QPainter) -> None:
    p.drawPath(_path((4, 5), (20, 5), (20, 16), (11, 16), (6.5, 20), (6.5, 16), (4, 16), close=True))


@drawing("outline")
def _outline(p: QPainter) -> None:  # a bulleted list
    for y in (6, 12, 18):
        p.drawPoint(QPointF(4.5, y))
        p.drawLine(QPointF(9, y), QPointF(20, y))


@drawing("cast")
def _cast(p: QPainter) -> None:  # two people
    p.drawEllipse(QPointF(9, 8), 3.4, 3.4)
    path = QPainterPath(QPointF(2.5, 20))
    path.cubicTo(QPointF(2.5, 15.5), QPointF(5.5, 13.5), QPointF(9, 13.5))
    path.cubicTo(QPointF(12.5, 13.5), QPointF(15.5, 15.5), QPointF(15.5, 20))
    p.drawPath(path)
    arc = QPainterPath(QPointF(15.2, 4.9))
    arc.cubicTo(QPointF(17.5, 4.3), QPointF(19.3, 6.2), QPointF(18.8, 8.4))
    arc.cubicTo(QPointF(18.5, 9.9), QPointF(17.2, 11), QPointF(15.8, 11.1))
    arc.moveTo(17.5, 13.9)
    arc.cubicTo(QPointF(20, 14.6), QPointF(21.5, 16.8), QPointF(21.5, 20))
    p.drawPath(arc)


@drawing("updates")
def _updates(p: QPainter) -> None:  # a bell
    path = QPainterPath(QPointF(5, 17))
    path.lineTo(19, 17)
    path.cubicTo(QPointF(17.5, 15.5), QPointF(17.5, 13.5), QPointF(17.5, 11))
    path.cubicTo(QPointF(17.5, 7.5), QPointF(15, 4.5), QPointF(12, 4.5))
    path.cubicTo(QPointF(9, 4.5), QPointF(6.5, 7.5), QPointF(6.5, 11))
    path.cubicTo(QPointF(6.5, 13.5), QPointF(6.5, 15.5), QPointF(5, 17))
    p.drawPath(path)
    p.drawPath(_path((10, 20), (14, 20)))


@drawing("close")
def _close(p: QPainter) -> None:
    p.drawLine(QPointF(6.5, 6.5), QPointF(17.5, 17.5))
    p.drawLine(QPointF(17.5, 6.5), QPointF(6.5, 17.5))


@drawing("chevron-down")
def _chevron_down(p: QPainter) -> None:
    p.drawPath(_path((6.5, 9.5), (12, 15), (17.5, 9.5)))


@drawing("chevron-right")
def _chevron_right(p: QPainter) -> None:
    p.drawPath(_path((9.5, 6.5), (15, 12), (9.5, 17.5)))


@drawing("check")
def _check(p: QPainter) -> None:
    p.drawPath(_path((5, 12.5), (10, 17.5), (19.5, 7)))


@drawing("open")
def _open(p: QPainter) -> None:  # an open folder
    p.drawPath(_path((3, 18.5), (3, 5.5), (9.5, 5.5), (11.5, 8.5), (18.5, 8.5), (18.5, 11)))
    p.drawPath(_path((3, 18.5), (6, 11), (21.5, 11), (18.5, 18.5), close=True))


# --- rendering --------------------------------------------------------------------------------------


def _muted() -> QColor:
    app = QGuiApplication.instance()
    if app is None:
        return QColor("#6b6f76")
    from . import theme

    return QColor(theme.tokens()["icon"])


def pixmap(name: str, color: str | QColor | None = None, size: int = 16, ratio: float | None = None) -> QPixmap:
    if ratio is None:  # at least 2x, so icons stay crisp on every screen
        app = QGuiApplication.instance()
        ratio = max(app.devicePixelRatio() if app else 2.0, 2.0)
    image = QImage(int(size * ratio), int(size * ratio), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * ratio / 24, size * ratio / 24)
    pen = QPen(QColor(color) if color is not None else _muted(), STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _DRAWINGS[name](p)
    p.end()
    result = QPixmap.fromImage(image)
    result.setDevicePixelRatio(ratio)
    return result


def icon(name: str, color: str | QColor | None = None) -> QIcon:
    result = QIcon()
    for size in (16, 20, 24, 32):
        result.addPixmap(pixmap(name, color, size))
    return result


_FILES = Path(tempfile.gettempdir()) / "screenwriter-icons"


def icon_file(name: str, color: str, size: int = 16) -> str:
    """A PNG of the icon for a stylesheet's url(...), cached by name and colour.
    An @2x copy sits next to it, which Qt picks on high-resolution screens."""
    key = hashlib.sha1(f"{name}{color}{size}".encode()).hexdigest()[:10]
    path = _FILES / f"{name}-{key}.png"
    if not path.exists():
        _FILES.mkdir(parents=True, exist_ok=True)
        pixmap(name, color, size, 1.0).toImage().save(str(path))
        pixmap(name, color, size, 2.0).toImage().save(str(path.with_name(f"{name}-{key}@2x.png")))
    return path.as_posix()
