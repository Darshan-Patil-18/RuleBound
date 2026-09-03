from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class AssetPack:
    catalog: list[dict[str, Any]]
    finishes: list[dict[str, Any]]
    rules: dict[str, Any]
    rooms: list[dict[str, Any]]
    briefs: dict[str, str]
    historical_jobs: list[dict[str, Any]]

    catalog_by_sku: dict[str, dict[str, Any]] = field(default_factory=dict)
    finishes_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    rules_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    catalog_by_family: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def load_asset_pack(input_dir: str | Path) -> AssetPack:
    root = Path(input_dir)
    rooms = [read_json(path) for path in sorted((root / "rooms").glob("ROOM-*.json"))]
    briefs = {
        path.stem: path.read_text(encoding="utf-8").strip()
        for path in sorted((root / "briefs").glob("ROOM-*.txt"))
    }
    catalog = read_json(root / "catalog.json")
    finishes = read_json(root / "finishes.json")
    rules = read_json(root / "rules.json")
    historical_jobs = read_json(root / "historical_jobs.json")

    catalog_by_sku = {item["sku"]: item for item in catalog}
    finishes_by_id = {item["finish_id"]: item for item in finishes}
    rules_by_id = {rule["rule_id"]: rule for rule in rules["rules"]}
    catalog_by_family: dict[str, list[dict[str, Any]]] = {}
    for item in catalog:
        catalog_by_family.setdefault(item["family"], []).append(item)
    # Deterministic, stable ordering within each family (by SKU string).
    for items in catalog_by_family.values():
        items.sort(key=lambda i: i["sku"])

    return AssetPack(
        catalog=catalog,
        finishes=finishes,
        rules=rules,
        rooms=rooms,
        briefs=briefs,
        historical_jobs=historical_jobs,
        catalog_by_sku=catalog_by_sku,
        finishes_by_id=finishes_by_id,
        rules_by_id=rules_by_id,
        catalog_by_family=catalog_by_family,
    )
