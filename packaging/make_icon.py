"""Draw the app icon (screenwriter/resources/icon.png, 1024×1024).

Run after changing the design:  uv run python packaging/make_icon.py
PyInstaller converts the PNG to .icns / .ico at build time (needs Pillow).
"""

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

SIZE = 1024
OUT = Path(__file__).resolve().parent.parent / "screenwriter" / "resources" / "icon.png"


def pen(color: str, width: float) -> QPen:
    result = QPen(QColor(color), width)
    result.setCapStyle(Qt.PenCapStyle.RoundCap)
    return result


def draw() -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # background: deep ink-blue rounded square (macOS icon grid: 824px body, 100px margin)
    body = QRectF(100, 100, 824, 824)
    gradient = QLinearGradient(body.topLeft(), body.bottomRight())
    gradient.setColorAt(0, QColor("#2c4a6e"))
    gradient.setColorAt(1, QColor("#15263d"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(gradient)
    p.drawRoundedRect(body, 185, 185)

    # a page with a folded corner
    page = QPainterPath()
    left, top, right, bottom, fold = 290, 230, 734, 800, 120
    page.moveTo(left, top)
    page.lineTo(right - fold, top)
    page.lineTo(right, top + fold)
    page.lineTo(right, bottom)
    page.lineTo(left, bottom)
    page.closeSubpath()
    p.setBrush(QColor(0, 0, 0, 70))
    p.drawPath(page.translated(10, 16))
    p.setBrush(QColor("#fbf7ec"))
    p.drawPath(page)
    corner = QPainterPath()
    corner.moveTo(right - fold, top)
    corner.lineTo(right - fold, top + fold)
    corner.lineTo(right, top + fold)
    corner.closeSubpath()
    p.setBrush(QColor("#e2dccb"))
    p.drawPath(corner)

    # index-card rule and script-like lines: a heading, action, a centred cue and dialogue
    p.setPen(pen("#e0663f", 14))
    p.drawLine(QPointF(left + 40, 390), QPointF(right - 40, 390))
    ink = pen("#9aa3ad", 22)
    p.setPen(ink)
    for y, x1, x2 in ((320, 340, 560), (460, 340, 690), (510, 340, 640), (590, 450, 580), (640, 400, 630), (690, 400, 600)):
        p.drawLine(QPointF(x1, y), QPointF(x2, y))

    # pen nib, bottom right, over the page
    nib = QPainterPath()
    nib.moveTo(0, -150)
    nib.cubicTo(62, -95, 70, -20, 34, 70)
    nib.lineTo(0, 150)
    nib.lineTo(-34, 70)
    nib.cubicTo(-70, -20, -62, -95, 0, -150)
    p.save()
    p.translate(700, 690)
    p.rotate(38)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 80))
    p.drawPath(nib.translated(8, 12))
    nib_gradient = QLinearGradient(-60, 0, 60, 0)
    nib_gradient.setColorAt(0, QColor("#f2c14e"))
    nib_gradient.setColorAt(1, QColor("#c98a1b"))
    p.setBrush(nib_gradient)
    p.drawPath(nib)
    p.setPen(pen("#6b4a10", 9))
    p.drawLine(QPointF(0, 10), QPointF(0, 140))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#6b4a10"))
    p.drawEllipse(QPointF(0, 0), 17, 17)
    p.restore()
    p.end()
    return image


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    draw().save(str(OUT))
    print(f"wrote {OUT}")
