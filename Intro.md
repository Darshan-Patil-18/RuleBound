Hello!!

I'm Darshan, and this is my submission for the Rulebound Hackathon.

This project implements rule-based logic that reads a room brief and spec, generates a furniture layout, enforces 8 spatial rules and 6 pricing rules deterministically, and produces a traceable INR quote. No AI model runs anywhere in the pricing or repair path — it's pure rule-based code.

# 1. Main generation pipeline (generates layout.json and quote.json for all rooms)
python runner.py --input data --output OUTPUT

# 2. Confirm asset pack integrity
python tools/verify_pack.py

# 3. Validate generated outputs against schema
python tools/validate_output.py OUTPUT

# 4. Check byte-identical determinism across dual runs
python tools/check_determinism.py --command "python runner.py --input {input} --output {output}" --input data --work-dir .determinism-check

# 5. Verify pricing engine against reference quotes
python tests/test_pricing_against_reference.py

# 6. Verify arbiter repair loop with deliberate constraint violations
python tests/test_repair_loop.py
