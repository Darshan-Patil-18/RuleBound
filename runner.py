"""RuleBound Round 1/3 solution — single entry point.

Usage:
    python runner.py --input <input-directory> --output <output-directory>

For every rooms/<room_id>.json found under --input, writes:
    <output>/<room_id>/layout.json
    <output>/<room_id>/quote.json

No LLM, no external API, no randomness anywhere in this file or anything
it calls. Output is UTF-8, sorted keys, 2-space indent, trailing newline,
and byte-identical across repeated runs on the same input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rulebound.loader import load_asset_pack
from rulebound.generator import select_items_for_room, generate_initial_layout
from rulebound.arbiter import repair
from rulebound.pricing import build_quote


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def process_room(room: dict, brief_text: str, pack) -> tuple[dict, dict]:
    selections = select_items_for_room(room, brief_text, pack)
    placements = generate_initial_layout(room, selections, pack)
    placements, violations, status, stats = repair(placements, room, pack)

    # Strip internal-only bookkeeping (group_id) before writing output —
    # it is not part of layout.schema.json's placement object shape.
    clean_placements = [{k: v for k, v in p.items() if k != "group_id"} for p in placements]

    layout = {
        "room_id": room["room_id"],
        "placements": sorted(clean_placements, key=lambda p: p["placement_id"]),
        "violations": violations,
        "status": status,
    }

    if status == "valid":
        # Build one quote line per distinct (sku, finish_id) pair actually
        # present in the final placements, with quantity = how many times
        # that pair occurs. This keeps the quote a direct, honest reflection
        # of what is in the layout, not a copy of the original selection
        # request (which may have been partially dropped during repair).
        counts: dict[tuple[str, str], int] = {}
        for p in placements:
            key = (p["sku"], p["finish_id"])
            counts[key] = counts.get(key, 0) + 1
        line_inputs = [
            {"sku": sku, "finish_id": finish_id, "quantity": qty}
            for (sku, finish_id), qty in sorted(counts.items())
        ]
        quote = build_quote(room["room_id"], f"QUOTE-{room['room_id']}", line_inputs, pack)
    else:
        quote = {
            "quote_id": f"QUOTE-{room['room_id']}",
            "room_id": room["room_id"],
            "currency": "INR",
            "lines": [],
            "summary": {"grand_total_inr": 0},
            "summary_trace": [],
            "status": "blocked",
            "blocking_reasons": [
                f"Room {room['room_id']} is unsatisfiable: {len(violations)} rule violation(s) remained "
                f"after {stats['passes_used']} repair pass(es) (cap {stats['max_passes']}) and "
                f"{stats['drops_used']} item drop(s). See layout.json violations for detail."
            ],
        }

    return layout, quote


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pack = load_asset_pack(args.input)
    output_root = Path(args.output)

    for room in sorted(pack.rooms, key=lambda r: r["room_id"]):
        room_id = room["room_id"]
        brief_text = pack.briefs.get(room_id, "")
        layout, quote = process_room(room, brief_text, pack)
        write_json(output_root / room_id / "layout.json", layout)
        write_json(output_root / room_id / "quote.json", quote)

    print(f"Wrote output for {len(pack.rooms)} room(s) to {output_root}")


if __name__ == "__main__":
    main()
