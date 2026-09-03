# Changelog

## Round 1 → Round 3

This is a full rewrite of the Round 1 submission's solution code. The
released pack files (`data/`, `schemas/`, `tools/`, `worked_examples/`,
`PROBLEM.md`, `PRICING_SPEC.md`, `RUNNER_CONTRACT.md`) are unchanged from
the original release — only the solution itself changed.

### Fixed
- **Item selection was not actually generic.** The Round 1 selection logic
  matched specific SKU substrings (e.g. `"003" in sku`) that happened to
  reproduce the two worked reference quotes, which would have silently
  failed on any room using catalog SKUs outside this pack. Selection now
  uses only `family`, `dimensions_mm`, and `list_price_inr` — properties
  every SKU has, including ones outside this pack.
- **The "ergonomic chair" keyword match never actually matched anything**
  in Round 1, because it searched catalog item names for words like "task"
  or "ergonomic" that don't appear anywhere in `catalog.json` — so every
  room silently fell back to the same chair regardless of the brief. The
  chair upgrade logic now uses list price as an explicit, documented
  proxy for build quality instead of a keyword match against text that
  was never there.
- **Quantity extraction split brief text on commas**, which could separate
  a count from the noun it described in a single comma-joined sentence.
  It now splits only on sentence terminators and searches a local window
  before each keyword.
- **The walkway clearance rule (`RB-GEO-001`) had no confirmed test case**
  in Round 1 and its detector's wiring into the master validator was
  never independently verified. It's now implemented with an explicit,
  documented operational definition (see `ARCHITECTURE.md`) and is
  exercised directly by `tests/test_repair_loop.py`.

### Added
- `tests/test_pricing_against_reference.py` — cross-checks every field of
  the pricing engine against both `REF-QUOTE-01` and `REF-QUOTE-02`
  exactly (base amount, finish uplift, quantity discount, net goods,
  labour band, freight band, grand total).
- `tests/test_repair_loop.py` — proves the repair loop reduces a
  deliberately broken layout's violation count, rather than only ever
  running on layouts that were already valid.
- Explicit repair-loop statistics (`passes_used`, `max_passes`,
  `drops_used`) surfaced in `blocking_reasons` when a room escalates to
  `unsatisfiable`, so the quote explains *how hard* the system tried
  before giving up, not just that it gave up.

### Known, stated limitation
- `ROOM-03` (the L-shaped room with a diagonal egress corridor) resolves
  to `status: unsatisfiable` — two `RB-GEO-002` violations remain after
  the full bounded repair loop. This is treated as a correct outcome of
  a genuinely tight room, not a bug: see `ARCHITECTURE.md` → Arbitration,
  question 4.
