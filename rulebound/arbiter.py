"""The arbitration layer — the seam between the generative proposal and the
deterministic rule engine.

Contract (see ARCHITECTURE.md "Arbitration" section for the full answer):
  - Inbound object: a `layout proposal` (list of placement dicts) from
    generator.py. Nothing here ever calls the generator again or asks it
    for a new idea — once a proposal crosses into this file, all further
    changes are made by this file's own deterministic repair moves.
  - Outbound object: a `(placements, violations, status)` tuple. `status`
    is "valid" (zero violations) or "unsatisfiable" (violations remain
    after the bounded loop below terminates).
  - The model / generator never runs again inside this loop. Repairs are
    pure arithmetic on coordinates and rotation, nothing else.
"""
from __future__ import annotations

from . import checker


def _candidate_moves(step_mm: float = 300.0, radius_mm: float = 1500.0) -> list[tuple[float, float, int | None]]:
    """A fixed, finite, deterministically ordered set of candidate repair
    moves: (dx, dy, rotation_override). Order matters for reproducibility —
    the same violation always tries the same candidates in the same order,
    which is part of why two runs produce identical output. Candidates are
    sorted by distance from the origin (smallest nudge first) so the
    repair loop prefers the least disruptive fix available.
    """
    offsets = []
    steps = int(radius_mm // step_mm)
    for i in range(-steps, steps + 1):
        for j in range(-steps, steps + 1):
            offsets.append((i * step_mm, j * step_mm))
    offsets.sort(key=lambda o: (o[0] ** 2 + o[1] ** 2, o[0], o[1]))
    moves: list[tuple[float, float, int | None]] = [(dx, dy, None) for dx, dy in offsets]
    for rot in (90, 180, 270):
        moves.append((0.0, 0.0, rot))
    return moves


_MOVES = _candidate_moves()


def _room_bbox(room: dict) -> tuple[float, float, float, float]:
    xs = [p[0] for p in room["boundary_mm"]]
    ys = [p[1] for p in room["boundary_mm"]]
    return min(xs), min(ys), max(xs), max(ys)


def _try_repair_one(placements: list[dict], target_id: str, room: dict, pack, current_count: int) -> bool:
    """Try every candidate move for `target_id`, keep the layout in the
    position that yields the fewest total violations. Only apply a change
    if it *strictly* reduces the violation count — this single condition
    is the strictly-decreasing measure that proves the outer loop
    terminates (see ARCHITECTURE.md)."""
    target = next(p for p in placements if p["placement_id"] == target_id)
    original_x, original_y, original_rot = target["x_mm"], target["y_mm"], target["rotation_deg"]
    x_min, y_min, x_max, y_max = _room_bbox(room)

    best_count = current_count
    best_state: tuple[float, float, int] | None = None

    for dx, dy, rot_override in _MOVES:
        new_x = original_x + dx
        new_y = original_y + dy
        new_rot = rot_override if rot_override is not None else original_rot
        if new_x < x_min or new_y < y_min or new_x > x_max or new_y > y_max:
            continue
        target["x_mm"], target["y_mm"], target["rotation_deg"] = new_x, new_y, new_rot
        count = len(checker.validate_layout(placements, room, pack))
        if count < best_count:
            best_count = count
            best_state = (new_x, new_y, new_rot)
            if best_count == 0:
                break

    if best_state is not None:
        target["x_mm"], target["y_mm"], target["rotation_deg"] = best_state
        return True
    target["x_mm"], target["y_mm"], target["rotation_deg"] = original_x, original_y, original_rot
    return False


# Drop priority: least essential to most essential. Only used as a last
# resort, once, after positional repair has stopped making progress.
_DROP_PRIORITY = ("accessory", "collaboration", "storage", "chair", "desk")


def _attempt_drop(placements: list[dict], room: dict, pack, violations: list[dict]) -> bool:
    involved_ids = {pid for v in violations for pid in v["affected_placement_ids"]}
    for family in _DROP_PRIORITY:
        candidates = [
            p for p in placements
            if p["placement_id"] in involved_ids and pack.catalog_by_sku[p["sku"]]["family"] == family
        ]
        candidates.sort(key=lambda p: p["placement_id"])
        for p in candidates:
            placements.remove(p)
            return True
    return False


def repair(placements: list[dict], room: dict, pack) -> tuple[list[dict], list[dict], str, dict]:
    """The bounded repair loop.

    Termination bound: MAX_PASSES = 6 * max(1, len(placements)) + 20, a
    concrete finite number fixed before the loop starts. Independently of
    that cap, the loop also stops the moment a full pass produces zero
    improvement (every violation's target placement failed to find any
    strictly-better candidate), and stops immediately once violations
    reach zero. Three independent, all-finite stopping conditions.
    """
    max_passes = 6 * max(1, len(placements)) + 20
    violations = checker.validate_layout(placements, room, pack)
    passes_used = 0
    drops_used = 0

    while violations and passes_used < max_passes:
        passes_used += 1
        progress = False
        current_count = len(violations)
        for v in violations:
            target_id = v["affected_placement_ids"][-1]
            if _try_repair_one(placements, target_id, room, pack, current_count):
                progress = True
                break
        violations = checker.validate_layout(placements, room, pack)
        if not progress:
            break

    while violations and drops_used < len(placements):
        if not _attempt_drop(placements, room, pack, violations):
            break
        drops_used += 1
        violations = checker.validate_layout(placements, room, pack)

    status = "valid" if not violations else "unsatisfiable"
    stats = {
        "passes_used": passes_used,
        "max_passes": max_passes,
        "drops_used": drops_used,
        "final_violation_count": len(violations),
    }
    return placements, violations, status, stats
