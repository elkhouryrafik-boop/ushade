"""Revise the festival site boundary + derive a walkability layer (demo artifacts).

Problem: the hand-drawn sibling boundary misses the 2026 seafront promenade strip and the
Banys del Fòrum pier — 4 user-placed stages fall outside it. Also `nogo.geojson` conflates
"can't place shade" with "can't walk": pergola canopies and the pier ARE walkable festival
floor in 2026.

Outputs (viz/data/):
- boundary_2026.geojson  — old boundary ∪ pier polygon ∪ 35 m pads around outlying features,
  smoothed + simplified. The sim site polygon.
- walkable_nogo_2026.geojson — crowd blockers ONLY: building footprints + bridge structures.
  Pergolas/pier/plaza stay walkable (they remain no-go for SHADE in the PRD pipeline — that
  distinction lives there, untouched).
Validation: all 86 festival features inside boundary_2026; no stage inside a blocker
(known intentional exception: Auditori Rockdelux is INSIDE the Museu Blau building).
"""
from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

DATA = Path(__file__).parent / "data"
SIBLING = Path(r"examples/stages_2026_edited.geojson Resources\NatureGooddest\assets\festival_map")

PAD_M = 35.0          # ASSUMED pad around features the old boundary missed
DEG = 1.0 / 111_320.0  # rough metres -> degrees at this latitude (fine for a demo pad)
SMOOTH_M = 8.0         # close gaps/slivers
SIMPLIFY_M = 2.0


def main() -> None:
    boundary = json.load(open(DATA / "boundary.geojson", encoding="utf-8"))
    festival = json.load(open(DATA / "festival_map_2026.geojson", encoding="utf-8"))
    site = json.load(open(SIBLING / "site_elements.geojson", encoding="utf-8"))

    old = unary_union([shape(f["geometry"]) for f in boundary["features"]])

    # the pier is walkable festival floor (Aperol Island stands on it)
    pier = [
        shape(f["geometry"])
        for f in site["features"]
        if f["geometry"]["type"] == "Polygon" and f["properties"].get("man_made") == "pier"
    ]

    pts = [shape(f["geometry"]) for f in festival["features"]]
    outside = [p for p in pts if not old.contains(p)]
    pads = [p.buffer(PAD_M * DEG) for p in outside]

    merged = unary_union([old, *pier, *pads])
    s = SMOOTH_M * DEG
    merged = merged.buffer(s).buffer(-s).simplify(SIMPLIFY_M * DEG)
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda g: g.area)  # keep the main connected site

    (DATA / "boundary_2026.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": mapping(merged),
                        "properties": {
                            "name": "Primavera 2026 festival site (revised)",
                            "method": f"old hand-drawn boundary ∪ pier ∪ {PAD_M:.0f} m pads "
                            "around outlying user-placed features; smoothed+simplified",
                            "accuracy": "ASSUMED (demo); old boundary hand-drawn",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # crowd blockers: buildings + bridges only (NOT pergolas, NOT pier, NOT plaza)
    blockers = [
        f
        for f in site["features"]
        if f["geometry"]["type"] == "Polygon"
        and (
            f["properties"].get("element_class") == "building"
            or f["properties"].get("bridge") == "yes"
        )
    ]
    (DATA / "walkable_nogo_2026.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": blockers}), encoding="utf-8"
    )

    # --- validation ---
    inside = sum(1 for p in pts if merged.contains(p))
    blk = unary_union([shape(f["geometry"]) for f in blockers])
    offenders = [
        f["properties"]["name"]
        for f, p in zip(festival["features"], pts)
        if f["properties"].get("layer") == "stage" and blk.contains(p)
    ]
    print(f"boundary_2026: area ~{merged.area / DEG / DEG / 1e6:.1f} km2-equiv, "
          f"{inside}/{len(pts)} features inside")
    print(f"blockers: {len(blockers)} polygons (buildings+bridges only)")
    print(f"stages inside blockers: {offenders} "
          f"(expected: ['Auditori Rockdelux'] — intentional, indoor stage)")
    assert inside == len(pts), "revised boundary still misses features"


if __name__ == "__main__":
    main()
