from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def round_half_up(value) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def quantity_discount_bps(quantity: int, tiers: list[dict]) -> int:
    # tiers sorted ascending by min_qty; pick the highest tier the qty clears.
    applicable = 0
    for tier in sorted(tiers, key=lambda t: t["min_qty"]):
        if quantity >= tier["min_qty"]:
            applicable = tier["discount_bps"]
    return applicable


def labour_rate_for_minutes(total_minutes: int, tiers: list[dict]) -> tuple[int, str]:
    for tier in tiers:
        if tier["max_minutes"] is None or total_minutes <= tier["max_minutes"]:
            band = f"<= {tier['max_minutes']}" if tier["max_minutes"] is not None else "above previous tiers"
            return tier["rate_inr_per_hour"], band
    raise ValueError("No labour tier matched.")


def freight_for_goods(net_goods_inr: int, tiers: list[dict]) -> tuple[int, str]:
    for tier in tiers:
        if tier.get("max_goods_inr") is not None and net_goods_inr <= tier["max_goods_inr"]:
            return tier["flat_inr"], f"<= {tier['max_goods_inr']}"
    for tier in tiers:
        if tier.get("max_goods_inr") is None:
            amount = round_half_up(net_goods_inr * tier["percent_bps"] / Decimal(10000))
            return amount, "above_all_flat_bands"
    raise ValueError("No freight tier matched.")


def price_line(line_id: str, sku: str, finish_id: str, quantity: int, catalog_item: dict, finish: dict, discount_tiers: list[dict]) -> dict:
    unit_price = catalog_item["list_price_inr"]
    base_amount = unit_price * quantity
    uplift_bps = finish["uplift_bps"]
    finish_uplift = round_half_up(Decimal(base_amount) * uplift_bps / Decimal(10000))
    discount_bps = quantity_discount_bps(quantity, discount_tiers)
    quantity_discount = round_half_up(Decimal(base_amount) * discount_bps / Decimal(10000))
    net_goods = base_amount + finish_uplift - quantity_discount

    return {
        "line_id": line_id,
        "sku": sku,
        "finish_id": finish_id,
        "quantity": quantity,
        "unit_list_price_inr": unit_price,
        "base_amount_inr": base_amount,
        "finish_uplift_inr": finish_uplift,
        "quantity_discount_inr": quantity_discount,
        "net_goods_inr": net_goods,
        "labour_minutes": catalog_item["labour_minutes"] * quantity,
        "trace": [
            {"rule_id": "CATALOG", "inputs": {"unit_price": unit_price, "quantity": quantity}, "amount_inr": base_amount},
            {"rule_id": "RB-PRC-010", "inputs": {"uplift_bps": uplift_bps, "base_amount_inr": base_amount}, "amount_inr": finish_uplift},
            {"rule_id": "RB-PRC-009", "inputs": {"discount_bps": discount_bps, "base_amount_inr": base_amount}, "amount_inr": -quantity_discount},
        ],
    }


def build_quote(room_id: str, quote_id: str, line_inputs: list[dict], pack) -> dict:
    """line_inputs: list of {sku, finish_id, quantity}. Returns a full quote
    dict matching quote.schema.json. Blocks (status='blocked') if any line
    references an unknown SKU/finish or an incompatible finish, per
    RB-PRC-013 — never silently drops or partially prices a line.
    """
    rules_by_id = pack.rules_by_id
    discount_tiers = rules_by_id["RB-PRC-009"]["tiers"]
    labour_tiers = rules_by_id["RB-PRC-011"]["tiers"]
    freight_tiers = rules_by_id["RB-PRC-012"]["tiers"]

    blocking_reasons: list[str] = []
    lines: list[dict] = []

    for idx, li in enumerate(line_inputs, start=1):
        sku, finish_id, quantity = li["sku"], li["finish_id"], li["quantity"]
        item = pack.catalog_by_sku.get(sku)
        finish = pack.finishes_by_id.get(finish_id)
        if item is None:
            blocking_reasons.append(f"Unknown SKU '{sku}'.")
            continue
        if finish is None:
            blocking_reasons.append(f"Unknown finish_id '{finish_id}' for SKU '{sku}'.")
            continue
        if item["family"] not in finish.get("compatible_families", []):
            blocking_reasons.append(f"Finish '{finish_id}' is not compatible with family '{item['family']}' (SKU '{sku}').")
            continue
        if quantity <= 0:
            blocking_reasons.append(f"SKU '{sku}' has non-positive quantity {quantity}.")
            continue
        lines.append(price_line(f"L{idx:03d}", sku, finish_id, quantity, item, finish, discount_tiers))

    if blocking_reasons:
        return {
            "quote_id": quote_id,
            "room_id": room_id,
            "currency": "INR",
            "lines": [],
            "summary": {"grand_total_inr": 0},
            "summary_trace": [],
            "status": "blocked",
            "blocking_reasons": sorted(blocking_reasons),
        }

    goods_after_adjustments = sum(l["net_goods_inr"] for l in lines)
    total_minutes = sum(l["labour_minutes"] for l in lines)
    rate, band = labour_rate_for_minutes(total_minutes, labour_tiers)
    labour_inr = round_half_up(Decimal(total_minutes) * rate / Decimal(60))
    freight_inr, freight_band = freight_for_goods(goods_after_adjustments, freight_tiers)
    grand_total = goods_after_adjustments + labour_inr + freight_inr

    return {
        "quote_id": quote_id,
        "room_id": room_id,
        "currency": "INR",
        "lines": lines,
        "summary": {
            "goods_after_adjustments_inr": goods_after_adjustments,
            "labour_minutes": total_minutes,
            "labour_rate_inr_per_hour": rate,
            "labour_inr": labour_inr,
            "freight_inr": freight_inr,
            "grand_total_inr": grand_total,
        },
        "summary_trace": [
            {"rule_id": "RB-PRC-011", "inputs": {"total_labour_minutes": total_minutes, "rate_inr_per_hour": rate, "band": band}, "amount_inr": labour_inr},
            {"rule_id": "RB-PRC-012", "inputs": {"band": freight_band, "goods_inr": goods_after_adjustments}, "amount_inr": freight_inr},
        ],
        "status": "priced",
    }
