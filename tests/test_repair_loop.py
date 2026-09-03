"""Confirms the arbiter genuinely repairs a deliberately broken layout,
rather than starting from a layout that was already valid. Run with:
python tests/test_repair_loop.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rulebound.loader import load_asset_pack
from rulebound.generator import select_items_for_room, generate_initial_layout
from rulebound.checker import validate_layout
from rulebound.arbiter import repair


def main() -> None:
    pack = load_asset_pack(ROOT / "data")
    room = next(r for r in pack.rooms if r["room_id"] == "ROOM-01")
    brief = pack.briefs["ROOM-01"]
    selections = select_items_for_room(room, brief, pack)
    placements = generate_initial_layout(room, selections, pack)

    assert len(placements) >= 2, "Need at least two placements to force an overlap."
    placements[1]["x_mm"] = placements[0]["x_mm"]
    placements[1]["y_mm"] = placements[0]["y_mm"]

    broken = validate_layout(placements, room, pack)
    assert len(broken) > 0, "Expected the deliberately broken layout to have violations."
    print(f"Deliberately broken layout: {len(broken)} violation(s), including a forced overlap.")

    fixed_placements, final_violations, status, stats = repair(copy.deepcopy(placements), room, pack)
    print(f"After repair: status={status}, violations={len(final_violations)}, "
          f"passes_used={stats['passes_used']}/{stats['max_passes']}, drops_used={stats['drops_used']}")

    assert stats["passes_used"] > 0, "Repair loop should have run at least one pass."
    assert len(final_violations) < len(broken), "Repair loop made no improvement at all."
    print("PASS: repair loop reduced violation count from a genuinely broken starting layout.")


if __name__ == "__main__":
    main()
