"""Plan-position indicator: the tactical bearing/range display.

Compass convention throughout: 0 degrees is North and points up, angles
increase clockwise. Screen position is therefore
``x = cx + r*sin(theta)``, ``y = cy - r*cos(theta)``.

The one thing this display refuses to do is imply more certainty than the
physics allows. A track whose bearing has not been resolved is drawn with
*every* bearing its phase is consistent with, because at this array's
spacing that is genuinely where the emitter might be -- showing only the
best guess would be a lie that looks identical to a confirmed track.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque

from PyQt6 import QtCore, QtGui, QtWidgets

from sdr.multi_drone_tracker import Detection

BACKGROUND = QtGui.QColor(10, 16, 20)
GRID = QtGui.QColor(40, 70, 80)
GRID_TEXT = QtGui.QColor(110, 150, 160)
CONFIRMED = QtGui.QColor(80, 240, 170)
AMBIGUOUS = QtGui.QColor(240, 180, 70)
GHOST = QtGui.QColor(240, 180, 70, 70)
TRAIL = QtGui.QColor(80, 240, 170, 90)


class PPIWidget(QtWidgets.QWidget):
    """Polar bearing/range scope."""

    TRAIL_LENGTH = 40

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(420, 420)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding
        )
        self._tracks: dict[int, Detection] = {}
        self._trails: dict[int, deque[tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=self.TRAIL_LENGTH)
        )
        self._max_range_m = 100.0
        self._auto_range = True
        self._show_ghosts = True

    # -- public API ----------------------------------------------------

    def set_detections(self, detections: list[Detection]) -> None:
        """Merge a batch of detections, keeping the newest per track."""
        for det in detections:
            self._tracks[det.track_id] = det
            if not det.bearing_ambiguous:
                self._trails[det.track_id].append((det.bearing_degrees, det.distance_meters))
        self.update()

    def prune(self, live_track_ids: set[int]) -> None:
        for tid in list(self._tracks):
            if tid not in live_track_ids:
                self._tracks.pop(tid, None)
                self._trails.pop(tid, None)
        self.update()

    def clear(self) -> None:
        self._tracks.clear()
        self._trails.clear()
        self.update()

    def set_auto_range(self, enabled: bool) -> None:
        self._auto_range = enabled
        self.update()

    def set_max_range(self, metres: float) -> None:
        self._max_range_m = max(float(metres), 1.0)
        self._auto_range = False
        self.update()

    def set_show_ghosts(self, enabled: bool) -> None:
        self._show_ghosts = enabled
        self.update()

    # -- painting ------------------------------------------------------

    def _effective_range(self) -> float:
        if not self._auto_range:
            return self._max_range_m
        ranges = [d.distance_meters for d in self._tracks.values() if d.distance_meters > 0]
        if not ranges:
            return self._max_range_m
        # round up to something readable
        target = max(ranges) * 1.25
        magnitude = 10 ** math.floor(math.log10(target))
        return float(math.ceil(target / magnitude) * magnitude)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), BACKGROUND)

        side = min(self.width(), self.height())
        cx, cy = self.width() / 2, self.height() / 2
        radius = side / 2 - 34
        if radius <= 10:
            painter.end()
            return

        max_range = self._effective_range()
        self._draw_grid(painter, cx, cy, radius, max_range)

        for det in self._tracks.values():
            self._draw_track(painter, cx, cy, radius, max_range, det)

        self._draw_legend(painter)
        painter.end()

    def _draw_grid(
        self, painter: QtGui.QPainter, cx: float, cy: float, radius: float, max_range: float
    ) -> None:
        painter.setPen(QtGui.QPen(GRID, 1))
        rings = 4
        for i in range(1, rings + 1):
            r = radius * i / rings
            painter.drawEllipse(QtCore.QPointF(cx, cy), r, r)

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(GRID_TEXT)
        for i in range(1, rings + 1):
            r = radius * i / rings
            label = f"{max_range * i / rings:.0f} m"
            painter.drawText(QtCore.QPointF(cx + 4, cy - r - 3), label)

        # bearing spokes
        for angle in range(0, 360, 30):
            rad = math.radians(angle)
            sx, sy = cx + radius * math.sin(rad), cy - radius * math.cos(rad)
            painter.setPen(QtGui.QPen(GRID, 1, QtCore.Qt.PenStyle.DotLine))
            painter.drawLine(QtCore.QPointF(cx, cy), QtCore.QPointF(sx, sy))

            painter.setPen(GRID_TEXT)
            label = {0: "N", 90: "E", 180: "S", 270: "W"}.get(angle, str(angle))
            lx, ly = cx + (radius + 18) * math.sin(rad), cy - (radius + 18) * math.cos(rad)
            rect = QtCore.QRectF(lx - 16, ly - 9, 32, 18)
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)

    def _position(
        self, cx: float, cy: float, radius: float, max_range: float, bearing: float, rng: float
    ) -> QtCore.QPointF:
        # An uncalibrated or zero range would collapse every track onto the
        # centre, so unknown ranges are parked on the outer ring instead.
        fraction = 0.92 if rng <= 0 else min(rng / max_range, 1.0)
        rad = math.radians(bearing)
        return QtCore.QPointF(
            cx + radius * fraction * math.sin(rad), cy - radius * fraction * math.cos(rad)
        )

    def _draw_track(
        self,
        painter: QtGui.QPainter,
        cx: float,
        cy: float,
        radius: float,
        max_range: float,
        det: Detection,
    ) -> None:
        confirmed = not det.bearing_ambiguous
        colour = CONFIRMED if confirmed else AMBIGUOUS

        # Unresolved: draw every bearing the phase permits, so the display
        # never implies a precision the measurement does not have.
        if not confirmed and self._show_ghosts:
            painter.setPen(QtGui.QPen(GHOST, 1, QtCore.Qt.PenStyle.DashLine))
            for bearing in det.candidate_bearings:
                point = self._position(cx, cy, radius, max_range, bearing, det.distance_meters)
                painter.drawLine(QtCore.QPointF(cx, cy), point)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawEllipse(point, 4, 4)

        trail = self._trails.get(det.track_id)
        if trail and len(trail) > 1:
            painter.setPen(QtGui.QPen(TRAIL, 1.5))
            path = QtGui.QPainterPath()
            for i, (bearing, rng) in enumerate(trail):
                point = self._position(cx, cy, radius, max_range, bearing, rng)
                path.moveTo(point) if i == 0 else path.lineTo(point)
            painter.drawPath(path)

        point = self._position(cx, cy, radius, max_range, det.bearing_degrees, det.distance_meters)
        painter.setPen(QtGui.QPen(colour, 2))
        painter.setBrush(QtGui.QBrush(colour) if confirmed else QtCore.Qt.BrushStyle.NoBrush)
        painter.drawEllipse(point, 6, 6)

        if confirmed:
            painter.setPen(QtGui.QPen(QtGui.QColor(colour).darker(160), 1))
            painter.drawLine(QtCore.QPointF(cx, cy), point)

        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(colour)
        text = f"T{det.track_id}  {det.bearing_degrees:.1f}°"
        if not confirmed:
            text += "  ?"
        painter.drawText(QtCore.QPointF(point.x() + 10, point.y() - 6), text)

        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(GRID_TEXT)
        painter.drawText(
            QtCore.QPointF(point.x() + 10, point.y() + 7),
            f"{det.frequency_ghz:.4f} GHz  {det.signal_strength_dbm:.0f} dBm",
        )

    def _draw_legend(self, painter: QtGui.QPainter) -> None:
        font = painter.font()
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        entries = [
            (CONFIRMED, "bearing resolved"),
            (AMBIGUOUS, "unresolved - all candidates shown"),
        ]
        for i, (colour, label) in enumerate(entries):
            y = 16 + i * 16
            painter.setPen(QtGui.QPen(colour, 2))
            painter.setBrush(QtGui.QBrush(colour))
            painter.drawEllipse(QtCore.QPointF(16, y), 4, 4)
            painter.setPen(GRID_TEXT)
            painter.drawText(QtCore.QPointF(28, y + 4), label)
