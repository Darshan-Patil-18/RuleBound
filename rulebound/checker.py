"""Deterministic constraint checker.

Every function here takes a layout (list of placements) plus the room and
catalog data, and returns violation dicts shaped for violation.schema.json.
Nothing here fixes anything — detection only. The arbiter (arbiter.py) is
the only place violations get acted on.
"""
from __future__ import annotations

from typing import Any

from . import geometry as geo


def _item_footprint(placement: dict, catalog_by_sku: dict) -> geo.Rect:
    item = catalog_by_sku[placement["sku"]]
    dims = item["dimensions_mm"]
    return geo.footprint(placement["x_mm"], placement["y_mm"], dims["width"], dims["depth"], placement["rotation_deg"])


def detect_inside_room_boundary(placements: list[dict], room: dict, catalog_by_sku: dict) -> list[dict]:
    violations = []
    polygon = room["boundary_mm"]
    for p in placements:
        rect = _item_footprint(p, catalog_by_sku)
        if not geo.rect_inside_polygon(rect, polygon):
            violations.append({
                "rule_id": "RB-GEO-007",
                "message": f"Placement {p['placement_id']} footprint is not fully inside the room boundary.",
                "affected_placement_ids": [p["placement_id"]],
                "measured": {"x_min": rect.x_min, "y_min": rect.y_min, "x_max": rect.x_max, "y_max": rect.y_max},
                "required": {"inside_polygon": True},
            })
    return violations


def detect_min_wall_offset(placements: list[dict], room: dict, catalog_by_sku: dict, min_mm: float) -> list[dict]:
    violations = []
    polygon = room["boundary_mm"]
    for p in placements:
        rect = _item_footprint(p, catalog_by_sku)
        dist = geo.rect_min_distance_to_walls(rect, polygon)
        if dist < min_mm:
            violations.append({
                "rule_id": "RB-GEO-005",
                "message": f"Placement {p['placement_id']} is {round(dist, 1)} mm from the nearest wall (minimum {min_mm} mm).",
                "affected_placement_ids": [p["placement_id"]],
                "measured": {"distance_mm": round(dist, 1)},
                "required": {"min_distance_mm": min_mm},
            })
    return violations


def detect_no_overlap(placements: list[dict], catalog_by_sku: dict) -> list[dict]:
    violations = []
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            a, b = placements[i], placements[j]
            ra = _item_footprint(a, catalog_by_sku)
            rb = _item_footprint(b, catalog_by_sku)
            area = geo.overlap_area(ra, rb)
            if area > 0:
                violations.append({
                    "rule_id": "RB-GEO-006",
                    "message": f"Placements {a['placement_id']} and {b['placement_id']} overlap ({round(area)} mm^2).",
                    "affected_placement_ids": [a["placement_id"], b["placement_id"]],
                    "measured": {"overlap_area_mm2": round(area)},
                    "required": {"overlap_area_mm2": 0},
                })
    return violations


def detect_door_swing_clearance(placements: list[dict], room: dict, catalog_by_sku: dict, zone_mm: float) -> list[dict]:
    violations = []
    polygon = room["boundary_mm"]
    for door in room.get("doors", []):
        zone = geo.door_swing_zone(door, polygon, zone_mm)
        if zone is None:
            continue
        for p in placements:
            rect = _item_footprint(p, catalog_by_sku)
            if geo.rects_overlap(rect, zone):
                violations.append({
                    "rule_id": "RB-GEO-003",
                    "message": f"Placement {p['placement_id']} enters the swing clearance zone of door {door['door_id']}.",
                    "affected_placement_ids": [p["placement_id"]],
                    "measured": {"door_id": door["door_id"]},
                    "required": {"clearance_mm": zone_mm},
                })
    return violations


def detect_egress_clearance(placements: list[dict], room: dict, catalog_by_sku: dict) -> list[dict]:
    violations = []
    egress = room.get("egress")
    if not egress:
        return violations
    polygon = room["boundary_mm"]
    doors_by_id = {d["door_id"]: d for d in room.get("doors", [])}
    door = doors_by_id.get(egress["from_door_id"])
    if door is None:
        return violations
    ax, ay = geo.door_anchor_point(door, polygon)
    bx, by = egress["to_point_mm"]
    min_width = egress["min_width_mm"]
    for p in placements:
        rect = _item_footprint(p, catalog_by_sku)
        dist = geo.rect_to_segment_distance(rect, ax, ay, bx, by)
        if dist < min_width / 2:
            violations.append({
                "rule_id": "RB-GEO-002",
                "message": f"Placement {p['placement_id']} encroaches on the marked egress path (minimum {min_width} mm clear width).",
                "affected_placement_ids": [p["placement_id"]],
                "measured": {"distance_to_path_mm": round(dist, 1)},
                "required": {"min_half_width_mm": min_width / 2},
            })
    return violations


def detect_walkway_clearance(placements: list[dict], catalog_by_sku: dict, min_mm: float, min_facing_mm: float = 200.0) -> list[dict]:
    """RB-GEO-001 is the one rule in the pack with no explicit walkway zone
    given anywhere in the room spec (unlike doors and egress, which have
    exact coordinates). Our operational definition, stated plainly: any two
    placements whose footprints face each other — their projections
    overlap by at least min_facing_mm along one axis, and they do not
    overlap along the other axis — must have at least min_mm of clear gap
    between them along the facing axis. This models a person walking in a
    straight line between two rows of furniture. Placements from the same
    desk+chair group are treated as complementary, not two rows facing
    each other, so a desk and its own chair are excluded from this check
    (handled by the caller via `group_id`).
    """
    violations = []
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            a, b = placements[i], placements[j]
            if a.get("group_id") is not None and a.get("group_id") == b.get("group_id"):
                continue
            ra = _item_footprint(a, catalog_by_sku)
            rb = _item_footprint(b, catalog_by_sku)
            result = geo.axis_gap(ra, rb)
            if result is None:
                continue
            axis, gap = result
            facing = (min(ra.y_max, rb.y_max) - max(ra.y_min, rb.y_min)) if axis == "y" else (min(ra.x_max, rb.x_max) - max(ra.x_min, rb.x_min))
            if facing >= min_facing_mm and 0 < gap < min_mm:
                violations.append({
                    "rule_id": "RB-GEO-001",
                    "message": f"Gap between {a['placement_id']} and {b['placement_id']} is {round(gap, 1)} mm (minimum {min_mm} mm walkway).",
                    "affected_placement_ids": [a["placement_id"], b["placement_id"]],
                    "measured": {"gap_mm": round(gap, 1), "axis": axis},
                    "required": {"min_gap_mm": min_mm},
                })
    return violations


def detect_family_rear_clearance(placements: list[dict], catalog_by_sku: dict, family: str, min_mm: float, rule_id: str) -> list[dict]:
    """A family item requires clear space behind it (the direction the user
    sits into / pulls out from). We treat "behind" as the +Y direction from
    the item's own footprint at rotation_deg == 0, rotated consistently
    with the item's own rotation, and require no other placement to
    encroach on that rectangle."""
    violations = []
    family_placements = [p for p in placements if catalog_by_sku[p["sku"]]["family"] == family]
    for p in family_placements:
        item = catalog_by_sku[p["sku"]]
        dims = item["dimensions_mm"]
        rect = _item_footprint(p, catalog_by_sku)
        rot = p["rotation_deg"]
        if rot == 0:
            rear = geo.Rect(rect.x_min, rect.y_max, rect.x_max, rect.y_max + min_mm)
        elif rot == 180:
            rear = geo.Rect(rect.x_min, rect.y_min - min_mm, rect.x_max, rect.y_min)
        elif rot == 90:
            rear = geo.Rect(rect.x_max, rect.y_min, rect.x_max + min_mm, rect.y_max)
        else:
            rear = geo.Rect(rect.x_min - min_mm, rect.y_min, rect.x_min, rect.y_max)
        for other in placements:
            if other["placement_id"] == p["placement_id"]:
                continue
            if other.get("group_id") is not None and other.get("group_id") == p.get("group_id"):
                continue
            other_rect = _item_footprint(other, catalog_by_sku)
            if geo.rects_overlap(rear, other_rect):
                violations.append({
                    "rule_id": rule_id,
                    "message": f"{family.capitalize()} {p['placement_id']} rear clearance ({min_mm} mm) is obstructed by {other['placement_id']}.",
                    "affected_placement_ids": [p["placement_id"], other["placement_id"]],
                    "measured": {"required_rear_mm": min_mm},
                    "required": {"clear": True},
                })
    return violations


def detect_unpriced_or_incompatible(placements: list[dict], catalog_by_sku: dict, finishes_by_id: dict) -> list[dict]:
    violations = []
    for p in placements:
        item = catalog_by_sku.get(p["sku"])
        if item is None:
            violations.append({
                "rule_id": "RB-PRC-013",
                "message": f"Placement {p['placement_id']} references unknown SKU '{p['sku']}'.",
                "affected_placement_ids": [p["placement_id"]],
                "measured": {}, "required": {},
            })
            continue
        finish = finishes_by_id.get(p["finish_id"])
        if finish is None:
            violations.append({
                "rule_id": "RB-PRC-013",
                "message": f"Placement {p['placement_id']} references unknown finish_id '{p['finish_id']}'.",
                "affected_placement_ids": [p["placement_id"]],
                "measured": {}, "required": {},
            })
            continue
        if item["family"] not in finish.get("compatible_families", []):
            violations.append({
                "rule_id": "RB-PRC-013",
                "message": f"Finish {p['finish_id']} is not compatible with family '{item['family']}' (placement {p['placement_id']}).",
                "affected_placement_ids": [p["placement_id"]],
                "measured": {}, "required": {},
            })
    return violations


def validate_layout(placements: list[dict], room: dict, pack) -> list[dict]:
    """Run every detector and return the combined, deterministically
    ordered violation list. This is the single entry point the arbiter and
    the runner both call."""
    rules_by_id = pack.rules_by_id
    catalog_by_sku = pack.catalog_by_sku
    finishes_by_id = pack.finishes_by_id

    violations: list[dict] = []
    violations += detect_inside_room_boundary(placements, room, catalog_by_sku)
    violations += detect_min_wall_offset(placements, room, catalog_by_sku, rules_by_id["RB-GEO-005"]["value_mm"])
    violations += detect_no_overlap(placements, catalog_by_sku)
    violations += detect_door_swing_clearance(placements, room, catalog_by_sku, rules_by_id["RB-GEO-003"]["value_mm"])
    violations += detect_egress_clearance(placements, room, catalog_by_sku)
    violations += detect_walkway_clearance(placements, catalog_by_sku, rules_by_id["RB-GEO-001"]["value_mm"])
    violations += detect_family_rear_clearance(placements, catalog_by_sku, "desk", rules_by_id["RB-GEO-004"]["value_mm"], "RB-GEO-004")
    violations += detect_family_rear_clearance(placements, catalog_by_sku, "chair", rules_by_id["RB-GEO-008"]["value_mm"], "RB-GEO-008")
    violations += detect_unpriced_or_incompatible(placements, catalog_by_sku, finishes_by_id)

    # Deterministic ordering + stable IDs: sort by (rule_id, first affected
    # placement_id), then assign violation_id V001, V002, ... in that order.
    violations.sort(key=lambda v: (v["rule_id"], v["affected_placement_ids"][0] if v["affected_placement_ids"] else ""))
    for idx, v in enumerate(violations, start=1):
        v["violation_id"] = f"V{idx:03d}"
        v.setdefault("repair_options", [])
    return violations
