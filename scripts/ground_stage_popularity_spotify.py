"""Ground stage popularity in REAL Spotify monthly listeners (replaces the ASSUMED 1-5 hand table).

Each set's headliner gets its real Spotify monthly-listener count (fetched + source-cited 2026-06, via
deep-research). A stage's pulling power = its headline act's listeners (people come for the headliner),
mapped by log-scale to a draw weight. This moves the crowd model's POPULARITY driver from ASSUMED to
GROUNDED (the derived weight/draw is DERIVED-from-GROUNDED); the per-zone spawn split stays ASSUMED.

Writes: src/crowd/data/set_times_2026.json (adds spotify_monthly_listeners + real popularity_weight),
        src/crowd/data/daytime_program_2026.json (real per-stage draw), and a provenance sidecar.
Run: PYTHONPATH=src python scripts/ground_stage_popularity_spotify.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

_DATA = Path("src/crowd/data")

# Real Spotify monthly listeners — each from the act's Spotify artist page (or chartmasters where
# Spotify rounded), captured 2026-06-21..23 via verified web research. NONE fabricated.
LISTENERS: dict[str, int] = {
    "Addison Rae": 15_100_000, "Amaarae": 5_015_531, "Ashnikko": 5_429_907, "Bad Gyal": 13_000_000,
    "Beverly Glenn-Copeland": 79_730, "Doja Cat": 55_900_000, "Father John Misty": 9_400_000,
    "Gorillaz": 40_726_525, "Lambrini Girls": 476_399, "Lechuga Zafiro & Verraco": 20_332,
    "Little Simz": 4_956_208, "Mac DeMarco": 21_443_126, "Massive Attack": 8_900_000,
    "My Bloody Valentine": 819_000, "Olivia Rodrigo": 67_876_917, "Panda Bear": 1_907_422,
    "Peggy Gou": 7_416_651, "PinkPantheress": 35_748_595, "Skrillex": 22_855_612,
    "The Cure": 25_611_363, "The xx": 5_649_446, "Viagra Boys": 863_300,
}


def weight_from_listeners(ml: int) -> float:
    """Log-scale monthly listeners -> CONTINUOUS 1.0..5.0 draw weight. Anchored on the real spread.

    log10(20K)=4.3 -> 1.0 ; log10(68M)=7.85 -> 5.0. Linear in log-listeners between, clamped. Kept
    CONTINUOUS (not re-bucketed to ints) so the real differences survive — Olivia 68M and PinkPantheress
    36M are both huge but NOT equal. Defensible: pull scales with the ORDER OF MAGNITUDE of the audience.
    """
    lo, hi = 4.3, 7.85
    t = (math.log10(max(ml, 1)) - lo) / (hi - lo)
    return round(max(1.0, min(5.0, 1 + 4 * t)), 2)


def main() -> None:
    st = json.loads((_DATA / "set_times_2026.json").read_text(encoding="utf-8"))
    rows = st["rows"]

    # 1) per-set real weight + listeners
    unmatched = []
    for r in rows:
        h = r.get("headliner")
        ml = LISTENERS.get(h)
        if ml is None:
            unmatched.append(h)
            continue
        # ADDITIVE only — the FROZEN night path (demand.py) reads int popularity_weight; leave it.
        r["spotify_monthly_listeners"] = ml
        r["spotify_weight"] = weight_from_listeners(ml)  # continuous grounded weight (record/daytime use)

    # 2) per-stage draw = headline (max-listener) act on that stage, log-mapped
    stage_pull: dict[str, int] = {}
    stage_top: dict[str, tuple[str, int]] = {}
    for r in rows:
        s, h = r.get("stage_name"), r.get("headliner")
        ml = LISTENERS.get(h, 0)
        if ml > stage_pull.get(s, -1):
            stage_pull[s] = ml
            stage_top[s] = (h, ml)

    # 3) write real draws into the daytime program (same stage names)
    dp = json.loads((_DATA / "daytime_program_2026.json").read_text(encoding="utf-8"))
    before = {}
    for s, v in dp.get("stage_program", {}).items():
        before[s] = v.get("draw")
        if s in stage_pull:
            v["draw"] = weight_from_listeners(stage_pull[s])

    # 4) provenance — popularity is now GROUNDED (real Spotify); the derived draw is DERIVED-from-GROUNDED.
    st.setdefault("_meta", {})["popularity_provenance"] = {
        "tier": "GROUNDED",
        "source": "Spotify monthly listeners per headliner (artist pages / chartmasters), captured 2026-06-21..23",
        "method": "per-set weight = log10-scaled monthly listeners -> 1..5; per-stage draw = headline (max-listener) act on the stage, same mapping",
        "note": "Replaces the ASSUMED 1-5 hand table. Popularity DRIVER now GROUNDED; the per-zone spawn split (85/15) stays ASSUMED. Night lineup used as the stage brand-pull proxy for the daytime sim (the daytime lineup itself is illustrative).",
        "as_of": "2026-06",
    }
    dp.setdefault("_meta", {})["draw_provenance"] = st["_meta"]["popularity_provenance"]

    (_DATA / "set_times_2026.json").write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")
    (_DATA / "daytime_program_2026.json").write_text(json.dumps(dp, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== per-stage draw: ASSUMED hand -> GROUNDED Spotify ===")
    for s in sorted(stage_pull, key=lambda x: -stage_pull[x]):
        if s in before:
            top, ml = stage_top[s]
            print(f"  {s:22s} draw {before[s]} -> {dp['stage_program'][s]['draw']}  "
                  f"(headline: {top}, {ml:,} listeners)")
    if unmatched:
        print("UNMATCHED headliners (no listener data):", set(unmatched))


if __name__ == "__main__":
    main()
