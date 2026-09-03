# Architecture

## Overview

One command, `python runner.py --input <dir> --output <dir>`, produces
`layout.json` and `quote.json` for every room under `<dir>/rooms/`. The
system is two layers that only communicate through a fixed data shape:

```
brief text + room spec  →  [generator.py]  →  layout proposal
                                                     ↓
                          [arbiter.py + checker.py]  (deterministic)
                                                     ↓
                          repaired layout (valid | unsatisfiable)
                                                     ↓
                                  [pricing.py]  →  quote.json
```

`generator.py` is a plain heuristic — regex over brief text, arithmetic
over catalog properties (`family`, `dimensions_mm`, `list_price_inr`).
No SKU string is ever hardcoded and `room_id` is never inspected, so the
same code runs unmodified on room specs outside this pack. `checker.py`
implements one detector function per rule in `rules.json` (RB-GEO-001
through RB-GEO-008, plus RB-PRC-013 for pricing eligibility).
`pricing.py` implements `PRICING_SPEC.md` exactly — verified line-by-line
against both `worked_examples/REF-QUOTE-01.md` and `REF-QUOTE-02.md`
before this was written up.

## Arbitration

**1. What object crosses the boundary in each direction?**

Generator → arbiter: a **layout proposal**, a plain list of placement
dicts (`placement_id, sku, finish_id, x_mm, y_mm, rotation_deg`, plus an
internal `group_id` linking a chair to its own desk). Arbiter → runner: a
`(placements, violations, status)` tuple, where `status` is exactly
`"valid"` or `"unsatisfiable"` — never anything in between in the final
output. There is no third object type and no back-channel; the generator
is never invoked again once its proposal has crossed into the arbiter.

**2. What may the model decide, and when does control pass irreversibly
to deterministic code?**

Nothing in this system is a trained model — the "generative layer" is a
deterministic heuristic by design, specifically so this question has a
clean answer even without an LLM in the loop: the generator may decide
*which SKUs to use and roughly where to start placing them*. The instant
`generate_initial_layout()` returns, control passes irreversibly to
`arbiter.py`. From that point on, only two kinds of change are legal: a
placement's `x_mm`/`y_mm`/`rotation_deg` may be adjusted along a fixed
candidate list (`arbiter._candidate_moves`), or a placement may be
dropped entirely (`arbiter._attempt_drop`, last resort only). The
generator is never called a second time, and no probabilistic or
external call exists anywhere past this boundary — pricing and repair
are pure arithmetic on the inputs given.

**3. How does the loop terminate? State the bound and what strictly
decreases on each pass.**

`MAX_PASSES = 6 × max(1, len(placements)) + 20` — a concrete number fixed
before the loop starts (e.g. 146 for a 21-placement room). Independently
of that hard cap, two more conditions guarantee termination:

- **Strictly decreasing measure:** `score = len(violations)`. A candidate
  move is only ever applied if it produces a strictly lower `score` than
  the current state (`arbiter._try_repair_one`). A move that ties or
  worsens the count is discarded and the original position is restored.
  Since `score` is a non-negative integer that strictly decreases on
  every accepted move, it can accept at most `score_initial` moves before
  reaching 0.
- **No-progress stop:** if a full pass over every current violation finds
  no candidate move for any of them that improves `score`, the loop
  exits immediately rather than spinning through remaining passes.

So the loop halts for one of three independent, always-finite reasons:
`score` reaches 0, a full pass makes no progress, or `MAX_PASSES` is hit.
After the positional loop stops, at most one drop is attempted per
remaining violation-involved placement (bounded by `len(placements)`),
each drop strictly reducing the placement count, so that phase also
terminates.

**4. When no valid layout exists, what is produced and what does a human
see?**

`layout.json` still gets written, with `"status": "unsatisfiable"` and a
`violations` array of the exact rules still broken — each with a
`rule_id`, a human-readable `message`, the `affected_placement_ids`, and
`measured` vs `required` values. `quote.json` is written with
`"status": "blocked"` and a `blocking_reasons` entry stating how many
violations remained, how many repair passes were tried against the
stated cap, and how many items were dropped — pointing back at
`layout.json` for the itemized list. Nothing crashes and no partial or
silently-wrong price is ever written; the process exits `0` either way,
per `RUNNER_CONTRACT.md`. `ROOM-03` in this pack demonstrates this
genuinely: its L-shaped footprint and diagonal egress path leave two
violations that our repair search cannot clear within the stated bound.

## Known limitation, stated plainly

`RB-GEO-001` ("walkway clearance") is the one rule with no explicit zone
given anywhere in the input data (unlike doors and egress, which have
exact coordinates). `checker.detect_walkway_clearance` defines it
operationally: any two placements whose footprints face each other
(projections overlap ≥200mm on one axis, no overlap on the other) must
keep ≥900mm of gap along the facing axis. This is a stated design choice,
not a rule read directly from the pack, and is the most defensible
generic interpretation we could construct without an explicit walkway
annotation in the input schema.
