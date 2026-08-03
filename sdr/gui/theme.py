"""Palette, stylesheet and vector glyphs for the detector UI.

Every icon is painted with QPainter rather than loaded from a file, so the
application ships as pure Python with no binary assets to lose or scale
badly on a HiDPI panel.
"""

from __future__ import annotations

import math

from PyQt6 import QtCore, QtGui

# -- palette -----------------------------------------------------------

BACKGROUND = QtGui.QColor("#0b0e12")
PANEL = QtGui.QColor("#0e1218")
BORDER = QtGui.QColor("#1d2530")

GOLD = QtGui.QColor("#f2c230")
GOLD_DIM = QtGui.QColor("#c9a227")
GREEN = QtGui.QColor("#25e06d")
RED = QtGui.QColor("#ef4444")
RED_DEEP = QtGui.QColor("#7f1d1d")
BLUE = QtGui.QColor("#2f81f7")
PURPLE = QtGui.QColor("#a855f7")
TEXT = QtGui.QColor("#dfe7ec")
TEXT_MUTED = QtGui.QColor("#78889a")

# map overlay colours
RING_OUTER = QtGui.QColor("#3346c8")
RING_INNER = QtGui.QColor("#a01b1b")
RING_EDGE = QtGui.QColor("#2f8f5b")
WEDGE_FILL = QtGui.QColor(126, 116, 224, 96)
WEDGE_EDGE = QtGui.QColor(150, 140, 240, 190)
WEDGE_GHOST = QtGui.QColor(200, 150, 60, 30)
SENSOR = QtGui.QColor("#3b9dff")

STYLESHEET = f"""
QWidget {{
    background-color: {BACKGROUND.name()};
    color: {TEXT.name()};
    font-family: "DejaVu Sans", "Segoe UI", sans-serif;
    font-size: 12px;
}}
QLabel#sectionHeading {{
    color: {GREEN.name()};
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 1px;
}}
QLabel#goldHeading {{
    color: {GOLD.name()};
    font-size: 13px;
    font-weight: bold;
}}
QLabel#mapHeading {{
    color: {TEXT.name()};
    font-size: 13px;
    letter-spacing: 1px;
}}
QLabel#placeholder {{
    color: {TEXT_MUTED.name()};
    font-size: 11px;
}}
QLabel#titleText {{
    color: {GOLD.name()};
    font-size: 24px;
    font-weight: bold;
    letter-spacing: 2px;
}}
QToolTip {{
    background-color: {PANEL.name()};
    color: {TEXT.name()};
    border: 1px solid {BORDER.name()};
    padding: 4px;
}}
QTableWidget {{
    background-color: {BACKGROUND.name()};
    gridline-color: {BORDER.name()};
    border: 1px solid {GOLD_DIM.name()};
    font-size: 11px;
}}
QHeaderView::section {{
    background-color: {BACKGROUND.name()};
    color: {GOLD.name()};
    border: 1px solid {GOLD_DIM.name()};
    padding: 5px;
    font-weight: bold;
    font-size: 11px;
}}
QTableWidget::item {{ padding: 3px; }}
QScrollBar:vertical {{ background: {BACKGROUND.name()}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER.name()}; border-radius: 5px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QMenuBar {{ background: {BACKGROUND.name()}; color: {TEXT_MUTED.name()}; }}
QMenuBar::item:selected {{ background: {PANEL.name()}; }}
QMenu {{ background: {PANEL.name()}; border: 1px solid {BORDER.name()}; }}
QMenu::item:selected {{ background: {BORDER.name()}; }}
QStatusBar {{ color: {TEXT_MUTED.name()}; border-top: 1px solid {BORDER.name()}; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background-color: #121820;
    border: 1px solid {BORDER.name()};
    border-radius: 3px;
    padding: 3px 5px;
}}
QComboBox::drop-down {{ border: 0; width: 16px; }}
QDialog {{ background-color: {BACKGROUND.name()}; }}
QGroupBox {{
    border: 1px solid {BORDER.name()};
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 8px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {GOLD.name()}; }}
QCheckBox {{ spacing: 6px; }}
"""


# -- vector glyphs -----------------------------------------------------


def draw_bluetooth(painter: QtGui.QPainter, rect: QtCore.QRectF, colour: QtGui.QColor) -> None:
    """The bluetooth rune, drawn as its two crossed chevrons."""
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(colour, max(rect.width() * 0.11, 1.2))
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    cx, top, bottom = rect.center().x(), rect.top(), rect.bottom()
    half = rect.width() * 0.32
    quarter_y = rect.top() + rect.height() * 0.27
    three_q_y = rect.top() + rect.height() * 0.73

    path = QtGui.QPainterPath()
    path.moveTo(cx - half, quarter_y)
    path.lineTo(cx + half, three_q_y)
    path.lineTo(cx, bottom)
    path.lineTo(cx, top)
    path.lineTo(cx + half, quarter_y)
    path.lineTo(cx - half, three_q_y)
    painter.drawPath(path)
    painter.restore()


def draw_wifi(painter: QtGui.QPainter, rect: QtCore.QRectF, colour: QtGui.QColor) -> None:
    """Three arcs over a dot."""
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(colour, max(rect.width() * 0.10, 1.2))
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

    origin = QtCore.QPointF(rect.center().x(), rect.bottom() - rect.height() * 0.12)
    for i, scale in enumerate((0.94, 0.62, 0.30)):
        r = rect.width() * 0.5 * scale
        arc = QtCore.QRectF(origin.x() - r, origin.y() - r, 2 * r, 2 * r)
        painter.drawArc(arc, 35 * 16, 110 * 16)
        if i == 2:
            break
    painter.setBrush(QtGui.QBrush(colour))
    painter.drawEllipse(origin, rect.width() * 0.075, rect.width() * 0.075)
    painter.restore()


def draw_gear(painter: QtGui.QPainter, rect: QtCore.QRectF, colour: QtGui.QColor) -> None:
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(QtGui.QPen(colour, max(rect.width() * 0.09, 1.2)))
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

    centre = rect.center()
    outer = rect.width() * 0.42
    inner = rect.width() * 0.30
    for i in range(8):
        angle = math.radians(i * 45)
        painter.drawLine(
            QtCore.QPointF(centre.x() + inner * math.cos(angle),
                           centre.y() + inner * math.sin(angle)),
            QtCore.QPointF(centre.x() + outer * math.cos(angle),
                           centre.y() + outer * math.sin(angle)),
        )
    painter.drawEllipse(centre, inner * 0.82, inner * 0.82)
    painter.drawEllipse(centre, rect.width() * 0.11, rect.width() * 0.11)
    painter.restore()


def draw_crosshair(painter: QtGui.QPainter, rect: QtCore.QRectF, colour: QtGui.QColor) -> None:
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(QtGui.QPen(colour, max(rect.width() * 0.08, 1.2)))
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    centre = rect.center()
    r = rect.width() * 0.30
    painter.drawEllipse(centre, r, r)
    reach = rect.width() * 0.46
    painter.drawLine(QtCore.QPointF(centre.x(), centre.y() - reach),
                     QtCore.QPointF(centre.x(), centre.y() - r * 0.55))
    painter.drawLine(QtCore.QPointF(centre.x(), centre.y() + r * 0.55),
                     QtCore.QPointF(centre.x(), centre.y() + reach))
    painter.drawLine(QtCore.QPointF(centre.x() - reach, centre.y()),
                     QtCore.QPointF(centre.x() - r * 0.55, centre.y()))
    painter.drawLine(QtCore.QPointF(centre.x() + r * 0.55, centre.y()),
                     QtCore.QPointF(centre.x() + reach, centre.y()))
    painter.restore()


def draw_locate(painter: QtGui.QPainter, rect: QtCore.QRectF, colour: QtGui.QColor) -> None:
    """A filled centre dot inside a ring: 'recentre on sensor'."""
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    centre = rect.center()
    painter.setPen(QtGui.QPen(colour, max(rect.width() * 0.08, 1.2)))
    painter.drawEllipse(centre, rect.width() * 0.34, rect.width() * 0.34)
    painter.setBrush(QtGui.QBrush(colour))
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.drawEllipse(centre, rect.width() * 0.14, rect.width() * 0.14)
    painter.restore()


def draw_drone_mark(painter: QtGui.QPainter, rect: QtCore.QRectF, colour: QtGui.QColor) -> None:
    """Application mark: a swept delta silhouette."""
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QBrush(colour))

    w, h = rect.width(), rect.height()
    x, y = rect.left(), rect.top()
    body = QtGui.QPainterPath()
    body.moveTo(x + w * 0.50, y + h * 0.08)
    body.cubicTo(x + w * 0.86, y + h * 0.26, x + w * 0.96, y + h * 0.58, x + w * 0.78, y + h * 0.90)
    body.cubicTo(x + w * 0.62, y + h * 0.70, x + w * 0.52, y + h * 0.56, x + w * 0.50, y + h * 0.36)
    body.cubicTo(x + w * 0.48, y + h * 0.56, x + w * 0.38, y + h * 0.70, x + w * 0.22, y + h * 0.90)
    body.cubicTo(x + w * 0.04, y + h * 0.58, x + w * 0.14, y + h * 0.26, x + w * 0.50, y + h * 0.08)
    painter.drawPath(body)
    painter.restore()


def draw_spiral(painter: QtGui.QPainter, rect: QtCore.QRectF, colour: QtGui.QColor) -> None:
    """Decorative corner mark."""
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(colour, max(rect.width() * 0.09, 1.2))
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

    centre = rect.center()
    path = QtGui.QPainterPath()
    steps = 90
    for i in range(steps + 1):
        angle = i / steps * math.pi * 3.1
        radius = rect.width() * 0.46 * (i / steps) ** 0.85
        point = QtCore.QPointF(
            centre.x() + radius * math.cos(angle), centre.y() + radius * math.sin(angle)
        )
        path.moveTo(point) if i == 0 else path.lineTo(point)
    painter.drawPath(path)
    painter.restore()
