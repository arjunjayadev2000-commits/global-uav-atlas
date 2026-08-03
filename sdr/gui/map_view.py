"""Geographic map overlay: range rings, sensor marker and bearing wedges.

A detected bearing is a *ray*, not a point. Range from RSSI is the weakest
number the tracker produces -- it depends on transmit power, antenna
pattern and multipath -- so plotting a drone as a dot at a computed distance
would state something the measurement cannot support. Every contact is
therefore drawn as a wedge: narrow in bearing, where the array is genuinely
precise, and extended in range, where it is not.

Unresolved tracks get one faint wedge per candidate bearing, for the same
reason the scope does: at this array's spacing those are real alternatives,
not display noise.
"""

from __future__ import annotations

import math

from PyQt6 import QtCore, QtGui, QtWidgets

from sdr.gui import theme
from sdr.gui.tiles import TILE_SIZE, TileLoader, lonlat_to_world, metres_per_pixel, world_to_lonlat
from sdr.multi_drone_tracker import Detection


class MapView(QtWidgets.QWidget):
    """Slippy map with tactical overlays, pannable and zoomable."""

    def __init__(
        self,
        latitude: float = 30.7333,
        longitude: float = 76.7794,
        zoom: int = 13,
        loader: TileLoader | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.setMinimumSize(420, 360)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

        self.sensor_lat = latitude
        self.sensor_lon = longitude
        self.center_lat = latitude
        self.center_lon = longitude
        self.zoom = zoom

        self.inner_ring_m = 1500.0
        self.outer_ring_m = 3000.0
        self.edge_ring_m = 6000.0
        self.wedge_width_deg = 6.0
        self.show_candidates = True

        self._tracks: dict[int, Detection] = {}
        self._drag_origin: QtCore.QPoint | None = None

        self.loader = loader or TileLoader(parent=self)
        self.loader.tileReady.connect(self.update)

    # -- public API ----------------------------------------------------

    def set_detections(self, detections: list[Detection]) -> None:
        for det in detections:
            self._tracks[det.track_id] = det
        self.update()

    def prune(self, live_track_ids: set[int]) -> None:
        for tid in list(self._tracks):
            if tid not in live_track_ids:
                del self._tracks[tid]
        self.update()

    def clear(self) -> None:
        self._tracks.clear()
        self.update()

    def set_sensor_position(self, lat: float, lon: float) -> None:
        self.sensor_lat, self.sensor_lon = lat, lon
        self.recenter()

    def set_rings(self, inner_m: float, outer_m: float) -> None:
        self.inner_ring_m, self.outer_ring_m = inner_m, outer_m
        self.edge_ring_m = outer_m * 2
        self.update()

    def set_show_candidates(self, enabled: bool) -> None:
        self.show_candidates = enabled
        self.update()

    def recenter(self) -> None:
        self.center_lat, self.center_lon = self.sensor_lat, self.sensor_lon
        self.update()

    def zoom_by(self, delta: int) -> None:
        self.zoom = max(3, min(18, self.zoom + delta))
        self.update()

    def fit_rings(self) -> None:
        """Pick the zoom at which the outer ring nearly fills the view."""
        if self.width() <= 0:
            return
        target_px = min(self.width(), self.height()) * 0.40
        for zoom in range(18, 2, -1):
            if self.outer_ring_m / metres_per_pixel(self.sensor_lat, zoom) <= target_px:
                self.zoom = zoom
                break
        self.recenter()

    # -- interaction ---------------------------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_origin = event.pos()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_origin is None:
            return
        delta = event.pos() - self._drag_origin
        self._drag_origin = event.pos()
        cx, cy = lonlat_to_world(self.center_lon, self.center_lat, self.zoom)
        self.center_lon, self.center_lat = world_to_lonlat(
            cx - delta.x(), cy - delta.y(), self.zoom
        )
        self.update()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_origin = None
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        self.zoom_by(1 if event.angleDelta().y() > 0 else -1)

    # -- painting ------------------------------------------------------

    def _screen_of(self, lon: float, lat: float) -> QtCore.QPointF:
        cx, cy = lonlat_to_world(self.center_lon, self.center_lat, self.zoom)
        px, py = lonlat_to_world(lon, lat, self.zoom)
        return QtCore.QPointF(
            self.width() / 2 + (px - cx), self.height() / 2 + (py - cy)
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("#0a0f14"))

        covered = self._draw_tiles(painter)
        if not covered:
            self._draw_offline_grid(painter)

        self._draw_rings(painter)
        for det in self._tracks.values():
            self._draw_contact(painter, det)
        self._draw_sensor(painter)
        self._draw_scale_bar(painter)
        painter.end()

    def _draw_tiles(self, painter: QtGui.QPainter) -> bool:
        cx, cy = lonlat_to_world(self.center_lon, self.center_lat, self.zoom)
        left = cx - self.width() / 2
        top = cy - self.height() / 2
        first_x, first_y = int(left // TILE_SIZE), int(top // TILE_SIZE)
        drawn = 0
        needed = 0

        for tx in range(first_x, int((left + self.width()) // TILE_SIZE) + 1):
            for ty in range(first_y, int((top + self.height()) // TILE_SIZE) + 1):
                needed += 1
                pixmap = self.loader.tile(self.zoom, tx, ty)
                if pixmap is None:
                    continue
                painter.drawPixmap(
                    QtCore.QPointF(tx * TILE_SIZE - left, ty * TILE_SIZE - top), pixmap
                )
                drawn += 1

        if drawn and drawn < needed:
            return True  # partial cover is still a map; missing tiles fill in
        return drawn > 0

    def _draw_offline_grid(self, painter: QtGui.QPainter) -> None:
        """Graticule stand-in when no basemap is available."""
        painter.save()
        painter.setPen(QtGui.QPen(QtGui.QColor("#16202a"), 1))
        step = 48
        for x in range(0, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            painter.drawLine(0, y, self.width(), y)

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(theme.TEXT_MUTED)
        reason = self.loader.last_error or "no tile server reachable"
        painter.drawText(
            QtCore.QRectF(12, 8, self.width() - 24, 16),
            int(QtCore.Qt.AlignmentFlag.AlignLeft),
            f"OFFLINE GRID — {reason}",
        )
        painter.restore()

    def _draw_rings(self, painter: QtGui.QPainter) -> None:
        centre = self._screen_of(self.sensor_lon, self.sensor_lat)
        mpp = metres_per_pixel(self.sensor_lat, self.zoom)
        painter.save()
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        for metres, colour in (
            (self.inner_ring_m, theme.RING_INNER),
            (self.outer_ring_m, theme.RING_OUTER),
            (self.edge_ring_m, theme.RING_EDGE),
        ):
            radius = metres / mpp
            if radius < 6 or radius > max(self.width(), self.height()) * 4:
                continue
            painter.setPen(QtGui.QPen(colour, 1.6))
            painter.drawEllipse(centre, radius, radius)
            label = f"{metres / 1000:g}km"
            painter.setPen(colour.lighter(150))
            painter.drawText(
                QtCore.QRectF(centre.x() - 40, centre.y() - radius - 15, 80, 14),
                int(QtCore.Qt.AlignmentFlag.AlignCenter),
                label,
            )
        painter.restore()

    def _wedge_path(self, bearing: float, span: float, reach_px: float) -> QtGui.QPainterPath:
        centre = self._screen_of(self.sensor_lon, self.sensor_lat)
        path = QtGui.QPainterPath(centre)
        # Qt angles run counter-clockwise from east; compass bearings run
        # clockwise from north, hence the 90 - bearing conversion.
        start = 90.0 - (bearing + span / 2)
        rect = QtCore.QRectF(
            centre.x() - reach_px, centre.y() - reach_px, reach_px * 2, reach_px * 2
        )
        path.arcTo(rect, start, span)
        path.closeSubpath()
        return path

    def _draw_contact(self, painter: QtGui.QPainter, det: Detection) -> None:
        mpp = metres_per_pixel(self.sensor_lat, self.zoom)
        reach = self.outer_ring_m / mpp
        resolved = not det.bearing_ambiguous

        if not resolved and self.show_candidates:
            # Kept deliberately faint and short. They must be visible enough
            # to say "the bearing is not pinned down", without a dozen of
            # them per contact swamping the resolved tracks that matter.
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QBrush(theme.WEDGE_GHOST))
            for bearing in det.candidate_bearings:
                painter.drawPath(
                    self._wedge_path(bearing, self.wedge_width_deg * 0.7, reach * 0.55)
                )

        painter.setPen(QtGui.QPen(theme.WEDGE_EDGE if resolved else theme.GOLD_DIM, 1.2))
        painter.setBrush(
            QtGui.QBrush(theme.WEDGE_FILL if resolved else QtGui.QColor(230, 170, 60, 70))
        )
        painter.drawPath(self._wedge_path(det.bearing_degrees, self.wedge_width_deg, reach))

        centre = self._screen_of(self.sensor_lon, self.sensor_lat)
        angle = math.radians(det.bearing_degrees)
        label_at = QtCore.QPointF(
            centre.x() + (reach + 14) * math.sin(angle),
            centre.y() - (reach + 14) * math.cos(angle),
        )
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(theme.GREEN if resolved else theme.GOLD)
        text = f"T{det.track_id} {det.bearing_degrees:.0f}°" + ("" if resolved else " ?")
        painter.drawText(
            QtCore.QRectF(label_at.x() - 48, label_at.y() - 9, 96, 18),
            int(QtCore.Qt.AlignmentFlag.AlignCenter),
            text,
        )

    def _draw_sensor(self, painter: QtGui.QPainter) -> None:
        centre = self._screen_of(self.sensor_lon, self.sensor_lat)
        painter.save()
        painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1.6))
        painter.setBrush(QtGui.QBrush(theme.SENSOR))
        painter.drawEllipse(centre, 6, 6)
        painter.setPen(QtGui.QPen(theme.SENSOR.lighter(140), 1.2))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawEllipse(centre, 11, 11)
        painter.restore()

    def _draw_scale_bar(self, painter: QtGui.QPainter) -> None:
        mpp = metres_per_pixel(self.sensor_lat, self.zoom)
        target_px = 90
        raw = mpp * target_px
        magnitude = 10 ** math.floor(math.log10(raw))
        nice = min((1, 2, 5, 10), key=lambda m: abs(m * magnitude - raw)) * magnitude
        width = nice / mpp

        x, y = 14, self.height() - 18
        painter.save()
        painter.setPen(QtGui.QPen(theme.TEXT_MUTED, 1.4))
        painter.drawLine(QtCore.QPointF(x, y), QtCore.QPointF(x + width, y))
        painter.drawLine(QtCore.QPointF(x, y - 4), QtCore.QPointF(x, y + 4))
        painter.drawLine(QtCore.QPointF(x + width, y - 4), QtCore.QPointF(x + width, y + 4))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        label = f"{nice / 1000:g} km" if nice >= 1000 else f"{nice:g} m"
        painter.drawText(QtCore.QPointF(x + width + 8, y + 4), label)
        painter.restore()
