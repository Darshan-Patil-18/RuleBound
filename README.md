# RuleBound — Solution (Darshan Patil)

A deterministic system that turns a room spec + plain-English brief into a
rule-checked 2D furniture layout and a fully traced INR quote. Built for
**RuleBound: The Sealed Build Challenge** (LV8 Tech).

See `ARCHITECTURE.md` for the design, and its **Arbitration** section for
how the repair loop works and provably terminates.

## Demo video

`<PASTE YOUR DEMO VIDEO LINK HERE BEFORE SUBMITTING>`

## Run it

Requires Python 3.10+, standard library only — no dependencies to install.

```bash
python runner.py --input data --output OUTPUT
```

This writes `OUTPUT/<room_id>/layout.json` and `OUTPUT/<room_id>/quote.json`
for every room found under `<input>/rooms/`.

## Verify it

```bash
# 1. Confirm the input pack itself is intact
python tools/verify_pack.py

# 2. Confirm output matches the required schema shape
python tools/validate_output.py OUTPUT

# 3. Confirm two runs produce byte-identical output
python tools/check_determinism.py --command "python runner.py --input {input} --output {output}" --input data --work-dir .determinism-check

# 4. Confirm the pricing engine matches both worked reference quotes exactly
python tests/test_pricing_against_reference.py

# 5. Confirm the repair loop genuinely repairs a broken layout
python tests/test_repair_loop.py
```

All five should print a clean pass with no errors.

## What's in this repository

```
runner.py                  the one documented command (entry point)
rulebound/
  loader.py                 typed asset pack loader
  geometry.py                polygon/rectangle geometry helpers (no deps)
  checker.py                 one detector per rule in data/rules.json
  generator.py                brief parsing + generic item selection + initial placement
  arbiter.py                  the bounded repair loop (see ARCHITECTURE.md)
  pricing.py                   pricing engine, exact per PRICING_SPEC.md
tests/
  test_pricing_against_reference.py   cross-checks pricing.py against both worked examples
  test_repair_loop.py                 confirms the arbiter fixes a deliberately broken layout
data/, schemas/, tools/, worked_examples/   released pack, unmodified
ARCHITECTURE.md            design + required Arbitration section
CHANGELOG.md               what changed since Round 1
```

## Result

- All 4 rectangular rooms (`ROOM-01`, `ROOM-02`, `ROOM-04`, `ROOM-05`)
  resolve to `status: valid` with a fully priced quote.
- `ROOM-03` (the L-shaped room, with a diagonal egress path) genuinely
  demonstrates the escalation path: it resolves to `status: unsatisfiable`
  with two remaining `RB-GEO-002` violations, and its quote is correctly
  `blocked`. This is not a bug — see `ARCHITECTURE.md`.
- `tests/test_pricing_against_reference.py` confirms every field of both
  `REF-QUOTE-01` and `REF-QUOTE-02` — including finish uplift, quantity
  discount, labour band, and freight band — matches this engine exactly.

## No LLM anywhere in this pipeline

Every layer — generation, checking, repair, and pricing — is plain
deterministic Python (regex, arithmetic, geometry). This was a deliberate
choice, not just a requirement for the pricing path: it is what makes the
byte-identical-output guarantee provable rather than merely likely.
