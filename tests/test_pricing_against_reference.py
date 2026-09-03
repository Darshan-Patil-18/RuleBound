"""Cross-checks rulebound/pricing.py against both worked reference quotes
shipped in the pack. Run with: python tests/test_pricing_against_reference.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rulebound.loader import load_asset_pack
from rulebound.pricing import build_quote


def check_reference(pack, ref_path: Path) -> None:
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    line_inputs = [{"sku": l["sku"], "finish_id": l["finish_id"], "quantity": l["quantity"]} for l in ref["lines"]]
    quote = build_quote(ref["room_id"], "TEST", line_inputs, pack)

    assert quote["status"] == "priced", f"{ref_path.name}: expected priced, got {quote['status']}"
    for got, exp in zip(quote["lines"], ref["lines"]):
        for field in ("base_amount_inr", "finish_uplift_inr", "quantity_discount_inr", "net_goods_inr"):
            assert got[field] == exp[field], f"{ref_path.name} {exp['line_id']}.{field}: got {got[field]}, expected {exp[field]}"
    for field in ("goods_after_adjustments_inr", "labour_minutes", "labour_inr", "freight_inr", "grand_total_inr"):
        assert quote["summary"][field] == ref["summary"][field], (
            f"{ref_path.name} summary.{field}: got {quote['summary'][field]}, expected {ref['summary'][field]}"
        )
    print(f"PASS: {ref_path.name} — grand_total_inr = {quote['summary']['grand_total_inr']}")


def main() -> None:
    pack = load_asset_pack(ROOT / "data")
    ref_dir = ROOT / "data" / "reference_quotes"
    for ref_path in sorted(ref_dir.glob("REF-QUOTE-*.json")):
        check_reference(pack, ref_path)
    print("ALL REFERENCE QUOTES MATCH")


if __name__ == "__main__":
    main()
