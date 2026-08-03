"""Web-Mercator tile maths and an asynchronous tile loader.

Tiles are fetched through Qt's own network stack so requests never block the
paint loop, and cached on disk so a restart in the field does not re-fetch
everything. When no tile server is reachable the map degrades to an offline
grid rather than failing -- a bearing display is still useful without a
basemap, and a fielded sensor often has no connectivity.

Respect your tile provider's usage policy. The OpenStreetMap default below
is fine for light interactive use with the identifying User-Agent set here;
anything heavier wants your own tile server or a commercial key.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtNetwork

TILE_SIZE = 256
DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = b"uav-sdr-tracker/1.0 (+https://github.com/topics/software-defined-radio)"
EARTH_CIRCUMFERENCE_M = 40_075_016.686


# -- projection --------------------------------------------------------


def lonlat_to_world(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Longitude/latitude to absolute pixel coordinates at a zoom level."""
    lat = max(min(lat, 85.05112878), -85.05112878)
    scale = TILE_SIZE * (2**zoom)
    x = (lon + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


def world_to_lonlat(x: float, y: float, zoom: int) -> tuple[float, float]:
    scale = TILE_SIZE * (2**zoom)
    lon = x / scale * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * y / scale
    lat = math.degrees(math.atan(math.sinh(n)))
    return lon, lat


def metres_per_pixel(lat: float, zoom: int) -> float:
    return EARTH_CIRCUMFERENCE_M * math.cos(math.radians(lat)) / (TILE_SIZE * 2**zoom)


def offset_lonlat(lon: float, lat: float, bearing_deg: float, distance_m: float):
    """Point `distance_m` from (lon, lat) along a compass bearing."""
    radius = 6_371_000.0
    angular = distance_m / radius
    bearing = math.radians(bearing_deg)
    lat1, lon1 = math.radians(lat), math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lon2), math.degrees(lat2)


# -- loader ------------------------------------------------------------


class TileLoader(QtCore.QObject):
    """Fetches and caches map tiles, emitting when new ones become available."""

    tileReady = QtCore.pyqtSignal()

    def __init__(
        self,
        url_template: str = DEFAULT_TILE_URL,
        cache_dir: Path | None = None,
        max_concurrent: int = 6,
        parent: QtCore.QObject | None = None,
    ):
        super().__init__(parent)
        self.url_template = url_template
        self.cache_dir = cache_dir or (
            Path(QtCore.QStandardPaths.writableLocation(
                QtCore.QStandardPaths.StandardLocation.CacheLocation
            )) / "tiles"
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.enabled = True
        #: Set once a request fails, so the widget can explain itself instead
        #: of silently showing an empty map.
        self.last_error: str | None = None

        self._manager = QtNetwork.QNetworkAccessManager(self)
        self._memory: dict[tuple[int, int, int], QtGui.QPixmap] = {}
        self._inflight: set[tuple[int, int, int]] = set()
        self._max_concurrent = max_concurrent

    # -- cache paths ---------------------------------------------------

    def _cache_path(self, z: int, x: int, y: int) -> Path:
        digest = hashlib.sha256(self.url_template.encode()).hexdigest()[:8]
        return self.cache_dir / digest / str(z) / str(x) / f"{y}.png"

    # -- lookup --------------------------------------------------------

    def tile(self, z: int, x: int, y: int) -> QtGui.QPixmap | None:
        """Return a tile if held, otherwise start fetching it and return None."""
        key = (z, x, y)
        if key in self._memory:
            return self._memory[key]

        path = self._cache_path(z, x, y)
        if path.exists():
            pixmap = QtGui.QPixmap(str(path))
            if not pixmap.isNull():
                self._memory[key] = pixmap
                return pixmap

        if self.enabled:
            self._request(key)
        return None

    def _request(self, key: tuple[int, int, int]) -> None:
        if key in self._inflight or len(self._inflight) >= self._max_concurrent:
            return
        z, x, y = key
        limit = 2**z
        if not (0 <= x < limit and 0 <= y < limit):
            return

        url = self.url_template.format(z=z, x=x, y=y)
        request = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        request.setRawHeader(b"User-Agent", USER_AGENT)
        request.setAttribute(
            QtNetwork.QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QtNetwork.QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        reply = self._manager.get(request)
        self._inflight.add(key)
        reply.finished.connect(lambda r=reply, k=key: self._on_finished(r, k))

    def _on_finished(self, reply: QtNetwork.QNetworkReply, key: tuple[int, int, int]) -> None:
        self._inflight.discard(key)
        try:
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
                self.last_error = reply.errorString()
                return
            data = reply.readAll()
            pixmap = QtGui.QPixmap()
            if not pixmap.loadFromData(data):
                self.last_error = "tile server returned data that is not an image"
                return

            self._memory[key] = pixmap
            self.last_error = None
            path = self._cache_path(*key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bytes(data))
            self.tileReady.emit()
        finally:
            reply.deleteLater()

    def clear_memory(self) -> None:
        self._memory.clear()
