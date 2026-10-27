"""Cross-language contract validation (Python side).

`validate.py` loads the neutral `contracts/*.schema.json` files (the single
source of truth) and validates artifacts against them with jsonschema 4.26 +
a referencing.Registry built from `contracts/_defs/`. The Node side
(`validate.ts`) does the same with Ajv2020 over the SAME files — neither
runtime co-authors the contract (00-RESEARCH §Single-Source Schema Strategy).
"""
