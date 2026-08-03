"""Custom-painted controls matching the detector's console styling.

Qt's stock widgets cannot be pushed to this look with a stylesheet alone --
the neon-outlined buttons, the sliding toggle and the ringed radio group are
all painted directly.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from sdr.gui import theme


class GlyphButton(QtWidgets.QAbstractButton):
    """A borderless icon button driven by one of the theme's painters."""

    def __init__(
        self,
        painter_fn,
        colour: QtGui.QColor,
        size: int = 26,
        tooltip: str = "",
        framed: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self._painter_fn = painter_fn
        self._colour = colour
        self._framed = framed
        self.setFixedSize(size, size)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(3, 3, -3, -3)
        if self._framed:
            painter.setPen(QtGui.QPen(theme.BORDER, 1))
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#141a22")))
            painter.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
            rect = rect.adjusted(3, 3, -3, -3)
        colour = self._colour.lighter(125) if self.underMouse() else self._colour
        self._painter_fn(painter, rect, colour)
        painter.end()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class GlyphLabel(QtWidgets.QWidget):
    """Non-interactive glyph whose colour reflects an on/off state."""

    def __init__(
        self,
        painter_fn,
        on_colour: QtGui.QColor,
        size: int = 20,
        tooltip: str = "",
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self._painter_fn = painter_fn
        self._on_colour = on_colour
        self._active = False
        self.setFixedSize(size, size)
        if tooltip:
            self.setToolTip(tooltip)

    def set_active(self, active: bool) -> None:
        if active != self._active:
            self._active = active
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        colour = self._on_colour if self._active else theme.BORDER.lighter(140)
        self._painter_fn(painter, QtCore.QRectF(self.rect()).adjusted(2, 2, -2, -2), colour)
        painter.end()


class NeonButton(QtWidgets.QPushButton):
    """Wide rounded button with a coloured outline and tinted fill."""

    def __init__(
        self,
        text: str,
        outline: QtGui.QColor,
        text_colour: QtGui.QColor,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._outline = outline
        self._text_colour = text_colour
        self.setFixedHeight(38)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed
        )

    def set_text_colour(self, colour: QtGui.QColor) -> None:
        self._text_colour = colour
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)

        fill = QtGui.QColor(self._outline)
        fill.setAlpha(52 if self.isDown() else 30)
        painter.setBrush(QtGui.QBrush(fill))
        width = 2 if self.underMouse() else 1.4
        painter.setPen(QtGui.QPen(self._outline, width))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        font.setLetterSpacing(QtGui.QFont.SpacingType.AbsoluteSpacing, 1.0)
        painter.setFont(font)
        painter.setPen(self._text_colour)
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, self.text())
        painter.end()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class ToggleSwitch(QtWidgets.QAbstractButton):
    """Sliding on/off switch."""

    def __init__(
        self,
        on_colour: QtGui.QColor | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(44, 22)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._on_colour = on_colour or theme.GREEN

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)

        track = QtGui.QColor(self._on_colour) if self.isChecked() else QtGui.QColor("#28323d")
        if self.isChecked():
            track.setAlpha(150)
        painter.setBrush(QtGui.QBrush(track))
        painter.setPen(QtGui.QPen(theme.BORDER.lighter(130), 1))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        knob_r = rect.height() / 2 - 2.5
        knob_x = rect.right() - knob_r - 3 if self.isChecked() else rect.left() + knob_r + 3
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(
            QtGui.QBrush(self._on_colour if self.isChecked() else QtGui.QColor("#8b98a5"))
        )
        painter.drawEllipse(QtCore.QPointF(knob_x, rect.center().y()), knob_r, knob_r)
        painter.end()


class RadioPill(QtWidgets.QRadioButton):
    """Radio button with a filled-ring indicator."""

    def __init__(self, text: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(text, parent)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        centre = QtCore.QPointF(9.0, self.height() / 2)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(theme.BLUE if self.isChecked() else theme.TEXT_MUTED, 1.4))
        painter.drawEllipse(centre, 6.0, 6.0)
        if self.isChecked():
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QBrush(theme.BLUE))
            painter.drawEllipse(centre, 3.4, 3.4)

        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(theme.TEXT if self.isChecked() else theme.TEXT_MUTED)
        painter.drawText(
            QtCore.QRectF(20, 0, self.width() - 20, self.height()),
            int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
            self.text(),
        )
        painter.end()

    def sizeHint(self) -> QtCore.QSize:
        metrics = QtGui.QFontMetrics(self.font())
        return QtCore.QSize(26 + metrics.horizontalAdvance(self.text()), 24)


class OutlinedBox(QtWidgets.QFrame):
    """Thin rounded outline used to group the band selector."""

    def __init__(self, colour: QtGui.QColor | None = None, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._colour = colour or theme.BORDER.lighter(140)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(self._colour, 1.2))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6), 8, 8)
        painter.end()


class MapPill(QtWidgets.QAbstractButton):
    """Rounded status pill floated over the map ('NL Sources: OFF')."""

    def __init__(self, label: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._label = label
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self._refresh_width()

    def _refresh_width(self) -> None:
        metrics = QtGui.QFontMetrics(self.font())
        self.setFixedWidth(metrics.horizontalAdvance(self._text()) + 58)

    def _text(self) -> str:
        return f"{self._label}: {'ON' if self.isChecked() else 'OFF'}"

    def nextCheckState(self) -> None:
        super().nextCheckState()
        self._refresh_width()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        painter.setBrush(QtGui.QBrush(QtGui.QColor(18, 24, 31, 232)))
        painter.setPen(QtGui.QPen(theme.BORDER.lighter(130), 1))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        dot = QtCore.QPointF(rect.left() + 18, rect.center().y())
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(theme.GREEN if self.isChecked() else QtGui.QColor("#3c4a57")))
        painter.drawEllipse(dot, 8, 8)

        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(theme.TEXT)
        painter.drawText(
            QtCore.QRectF(rect.left() + 32, rect.top(), rect.width() - 40, rect.height()),
            int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter),
            self._text(),
        )
        painter.end()
