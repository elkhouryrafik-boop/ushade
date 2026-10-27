# Threshold hashing — exact canonicalization (CONTRACT-04)

`acceptance/thresholds.json` carries a `content_sha256` over **only the value block**
`{x_utci_reduction_c, y_coverage_pct}` so that any post-run edit to either gate value
becomes a deterministic test failure (`tests/test_thresholds_immutable.py`), not a
judgment call. This is the anti-gate-gaming tripwire (Pitfall 2 / threat T-00-06).

## The exact recipe (must be reproduced byte-for-byte)

```python
import json, hashlib
value_block = {"x_utci_reduction_c": 4, "y_coverage_pct": 70}
canonical = json.dumps(value_block, sort_keys=True, separators=(",", ":"))
content_sha256 = hashlib.sha256(canonical.encode()).hexdigest()
```

- `sort_keys=True` — key order is fixed regardless of authoring order.
- `separators=(",", ":")` — no incidental whitespace; the canonical form is stable.
- The hash covers **only** `x_utci_reduction_c` and `y_coverage_pct`. `schema_version`,
  `declared_on`, `immutable`, and `x_hash_input` are intentionally **outside** the hash
  so the gate values themselves are the only thing locked.

## What is NOT allowed

- Editing `x_utci_reduction_c` (X = 4 °C) or `y_coverage_pct` (Y = 70 %) after
  `declared_on` (2026-06-10). The thresholds are LOCKED in Phase 0 and immutable
  post-run (PRD §6, CLAUDE.md non-negotiables). Any change desynchronizes the stored
  `content_sha256` and the immutability test fails RED.

## Verification

```bash
python -c "import json,hashlib; t=json.load(open('acceptance/thresholds.json')); \
  h=hashlib.sha256(json.dumps({'x_utci_reduction_c':t['x_utci_reduction_c'],'y_coverage_pct':t['y_coverage_pct']},sort_keys=True,separators=(',',':')).encode()).hexdigest(); \
  assert h==t['content_sha256']; print('hash ok')"
```
