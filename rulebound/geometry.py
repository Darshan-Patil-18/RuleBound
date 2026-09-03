"""Pure geometry helpers. No randomness, no I/O — every function here is a
plain deterministic function of its inputs, which is what the whole system's
byte-identical-output guarantee ultimately rests on.

All furniture rotations are restricted to 0/90/180/270 degrees, so every
placed footprint stays an axis-aligned rectangle (a 90-degree turn just
swaps width and depth). That single design choice is why this file never
needs a general-purpose polygon/rectangle intersection routine.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in room millimetre coordinates."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def depth(self) -> float:
        return self.y_max - self.y_min


def footprint(x_mm: float, y_mm: float, width_mm: float, depth_mm: float, rotation_deg: int) -> Rect:
    """Footprint of an item whose *front-left* corner sits at (x_mm, y_mm)
    before rotation. rotation_deg must be one of 0/90/180/270.
    """
    if rotation_deg in (90, 270):
        width_mm, depth_mm = depth_mm, width_mm
    return Rect(x_mm, y_mm, x_mm + width_mm, y_mm + depth_mm)


def rects_overlap(a: Rect, b: Rect) -> bool:
    return a.x_min < b.x_max and b.x_min < a.x_max and a.y_min < b.y_max and b.y_min < a.y_max


def overlap_area(a: Rect, b: Rect) -> float:
    if not rects_overlap(a, b):
        return 0.0
    ox = min(a.x_max, b.x_max) - max(a.x_min, b.x_min)
    oy = min(a.y_max, b.y_max) - max(a.y_min, b.y_min)
    return max(0.0, ox) * max(0.0, oy)


def axis_gap(a: Rect, b: Rect) -> tuple[str, float] | None:
    """If two rectangles face each other along one axis (their projections
    overlap on the other axis), return (axis, gap_mm) — the empty space
    between them along the facing axis. Returns None if they don't face
    each other in this simple sense (e.g. diagonal to one another), which
    is deliberately conservative: we only flag a walkway/aisle gap where a
    person would plausibly walk in a straight line between the two items.
    """
    x_overlap = min(a.x_max, b.x_max) - max(a.x_min, b.x_min)
    y_overlap = min(a.y_max, b.y_max) - max(a.y_min, b.y_min)
    if x_overlap > 0 and a.y_max <= b.y_min:
        return ("y", b.y_min - a.y_max)
    if x_overlap > 0 and b.y_max <= a.y_min:
        return ("y", a.y_min - b.y_max)
    if y_overlap > 0 and a.x_max <= b.x_min:
        return ("x", b.x_min - a.x_max)
    if y_overlap > 0 and b.x_max <= a.x_min:
        return ("x", a.x_min - b.x_max)
    return None


def point_in_polygon(px: float, py: float, polygon: list[list[float]]) -> bool:
    """Standard ray-casting test. Works for any simple polygon, convex or
    not (ROOM-03 in the released pack is an L-shape, so this matters)."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            x_intersect = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < x_intersect:
                inside = not inside
    return inside


def rect_inside_polygon(rect: Rect, polygon: list[list[float]], sample_step_mm: float = 50.0) -> bool:
    """A rectangle counts as inside the room only if every sampled point on
    its boundary and interior is inside the polygon. Sampling (rather than
    a pure corner check) is required because the room boundary can be
    non-convex — a rectangle can have all 4 corners inside an L-shaped room
    while still crossing the notch."""
    corners = [(rect.x_min, rect.y_min), (rect.x_max, rect.y_min), (rect.x_max, rect.y_max), (rect.x_min, rect.y_max)]
    for cx, cy in corners:
        if not point_in_polygon(cx, cy, polygon):
            return False
    x = rect.x_min
    while x <= rect.x_max:
        y = rect.y_min
        while y <= rect.y_max:
            if not point_in_polygon(x, y, polygon):
                return False
            y += sample_step_mm
        x += sample_step_mm
    return True


def polygon_edges(polygon: list[list[float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    n = len(polygon)
    return [(tuple(polygon[i]), tuple(polygon[(i + 1) % n])) for i in range(n)]


def point_to_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    proj_x, proj_y = ax + t * dx, ay + t * dy
    return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5


def rect_to_segment_distance(rect: Rect, ax: float, ay: float, bx: float, by: float) -> float:
    """Minimum distance from a rectangle's boundary to a line segment."""
    corners = [(rect.x_min, rect.y_min), (rect.x_max, rect.y_min), (rect.x_max, rect.y_max), (rect.x_min, rect.y_max)]
    return min(point_to_segment_distance(cx, cy, ax, ay, bx, by) for cx, cy in corners)


def rect_min_distance_to_walls(rect: Rect, polygon: list[list[float]]) -> float:
    return min(rect_to_segment_distance(rect, ax, ay, bx, by) for (ax, ay), (bx, by) in polygon_edges(polygon))


def door_anchor_point(door: dict, polygon: list[list[float]]) -> tuple[float, float]:
    """The interior point where a door opening meets the room, derived from
    the door's declared wall + offset_mm, matched against the room's actual
    edges (so this works for any room shape, not just a plain rectangle)."""
    wall = door["wall"]
    offset = door["offset_mm"]
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    x_min, x_max, y_min, y_max = min(xs), max(xs), min(ys), max(ys)
    if wall == "south":
        return (x_min + offset, y_min)
    if wall == "north":
        return (x_min + offset, y_max)
    if wall == "west":
        return (x_min, y_min + offset)
    if wall == "east":
        return (x_max, y_min + offset)
    return (x_min, y_min)


def door_swing_zone(door: dict, polygon: list[list[float]], zone_size_mm: float) -> Rect | None:
    """Approximate the door swing clearance zone as a square of side
    zone_size_mm, anchored at the door opening and extending into the room
    on the side implied by the swing direction. Doors that swing *outward*
    open away from the room interior, so they place no clearance demand on
    interior furniture and this returns None.
    """
    swing = door.get("swing", "")
    if swing.startswith("outward"):
        return None
    ax, ay = door_anchor_point(door, polygon)
    width = door.get("width_mm", zone_size_mm)
    wall = door["wall"]
    if wall == "south":
        x0, x1 = ax, ax + width if "right" in swing else ax - zone_size_mm
        return Rect(min(x0, x1), ay, min(x0, x1) + zone_size_mm, ay + zone_size_mm)
    if wall == "north":
        x0 = ax if "right" in swing else ax - zone_size_mm
        return Rect(x0, ay - zone_size_mm, x0 + zone_size_mm, ay)
    if wall == "west":
        y0 = ay if "right" in swing else ay - zone_size_mm
        return Rect(ax, y0, ax + zone_size_mm, y0 + zone_size_mm)
    if wall == "east":
        y0 = ay if "right" in swing else ay - zone_size_mm
        return Rect(ax - zone_size_mm, y0, ax, y0 + zone_size_mm)
    return None
