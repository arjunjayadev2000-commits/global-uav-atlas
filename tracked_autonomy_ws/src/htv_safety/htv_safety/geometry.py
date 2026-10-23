"""Planar geometry for footprints and geofences."""

from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]


def transform_polygon(polygon: Sequence[Point], x: float, y: float, yaw: float) -> list[Point]:
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c * px - s * py, y + s * px + c * py) for px, py in polygon]


def polygon_area(polygon: Sequence[Point]) -> float:
    n = len(polygon)
    return 0.5 * sum(
        polygon[i][0] * polygon[(i + 1) % n][1] - polygon[(i + 1) % n][0] * polygon[i][1] for i in range(n)
    )


def inflate_convex_polygon(polygon: Sequence[Point], margin: float) -> list[Point]:
    """Offset a convex polygon outward by ``margin`` (mitred corners)."""
    if margin == 0.0:
        return list(polygon)
    n = len(polygon)
    orientation = 1.0 if polygon_area(polygon) > 0 else -1.0
    lines = []
    for k in range(n):
        (x1, y1), (x2, y2) = polygon[k], polygon[(k + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        # Outward normal: right-hand normal for CCW polygons.
        nx, ny = orientation * dy / length, -orientation * dx / length
        lines.append(((x1 + nx * margin, y1 + ny * margin), (dx, dy)))
    out = []
    for k in range(n):
        (p1, d1), (p2, d2) = lines[k - 1], lines[k]
        denom = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(denom) < 1e-12:
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / denom
        out.append((p1[0] + t * d1[0], p1[1] + t * d1[1]))
    return out


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def _segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_to_boundary(point: Point, polygon: Sequence[Point]) -> float:
    """Signed distance to polygon edge: positive inside, negative outside."""
    n = len(polygon)
    d = min(_segment_distance(point, polygon[i], polygon[(i + 1) % n]) for i in range(n))
    return d if point_in_polygon(point, polygon) else -d


def footprint_clearance(footprint_world: Sequence[Point], fence: Sequence[Point]) -> float:
    """Minimum signed clearance of all footprint vertices to the fence boundary."""
    return min(distance_to_boundary(p, fence) for p in footprint_world)


def parse_polygon(flat: Sequence[float]) -> list[Point]:
    if len(flat) < 6 or len(flat) % 2:
        raise ValueError("polygon needs an even number of values describing >= 3 points")
    return [(float(flat[i]), float(flat[i + 1])) for i in range(0, len(flat), 2)]
