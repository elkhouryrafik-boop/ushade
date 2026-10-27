"""Georeference the a demo festival 2026 official map -> viz/data/stages_2026.geojson.

METHOD (v3 — orientation corrected by user ground truth):
v2 had the coast axis MIRRORED (placed Port where the mains belong). User ground truth:
Estrella Damm + Revolut stand on the SW deck (the depuradora platform, ~2.2226, 41.4073),
where v2 had put Port. Re-fitting the v2 anchor correspondences with that fixed point gives
the corrected official-map orientation:

  map-up    = sea (SE)        map-down = inland (W/NW edge: Museu Blau, gate forecourt)
  map-right = SW (mains deck) map-left = NE (marina / PV pergola: Port, Cupra Pulse)

A 2x2 linear fit on {mains, Port, Auditori, ENTRANCE} confirms map-right maps strongly
to W+S (SW) and map-up weakly seaward; the cartoon's depth axis compresses the inland
strip (bottom of map = the whole W/NW inland edge), so global affines still fail —
coordinates remain MANUAL zone placements anchored to OSM landmarks, with the official
map providing ordering/adjacency truth only (re-read per label cluster from crop tiles).

OSM anchors (NatureGooddest festival_map assets, WGS84 centroids):
  PV pergola platform   2.228278, 41.411463   (NE corner, marina)
  Banys del Forum pier  2.226433, 41.409206   (SE waterfront -> Aperol)
  Amphitheatre bowl     2.223531, 41.409128   (5,928 m2 structure -> Cupra)
  Museu Blau wedge      2.221040, 41.411250   (NW corner -> Auditori Rockdelux, gate)
  Bosc de columnes      2.224819, 41.410494   (canopy -> Radio a demo festival)
  SW deck (user pin)    2.22260,  41.40730    (depuradora platform -> the mains)

Adjacency read off the official map (left=NE, right=SW):
  top-right platform: ESTRELLA DAMM (NE of pair) | REVOLUT (SW of pair); PLENITUDE at the
    platform's inland edge.
  top-left waterfront: PORT (NE-most) -> CUPRA PULSE -> SCHWARZKOPF (inland), around the
    PV pergola esplanade.
  top-middle promenade, NE->SW: PRO AREA, DISNEY, BARCELONA SONA, [pier: APEROL],
    ADIDAS YARD.
  lower-left cluster (inland NE strip): SCHWARZKOPF edge -> FEVER HOUSE -> LEVI'S
    WAREHOUSE -> 501 CLUB -> LEVI'S PLAZA (most inland).
  bottom strip (inland W/NW): ENTRANCE (NW gate, El Maresme side), OCCIDENT on the
    entrance esplanade (audience field toward the gate), AUDITORI ROCKDELUX inside the
    Museu Blau building, EXIT on its N side.

Estimated placement accuracy: +/-20-40 m (cartoon-map source limit). Good enough for
sim attractors on the 6 m lattice; NOT a survey.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parent / "data"

# name, lon, lat, kind, capacity_class, placement note
FEATURES = [
    # --- main stages, SW deck (depuradora platform) — USER-CONFIRMED zone ---
    ("Estrella Damm", 2.22330, 41.40770, "stage", "main",
     "SW deck, NE of the pair (map: left of Revolut, left=NE)"),
    ("Revolut", 2.22210, 41.40680, "stage", "main",
     "SW deck, SW of the pair, toward the breakwater"),
    # --- electronic, inland edge of the mains platform ---
    ("Plenitude", 2.22360, 41.40840, "stage", "electronic",
     "inland edge of the SW deck, between the mains and the park"),
    # --- entrance esplanade ---
    ("Occident", 2.22260, 41.40990, "stage", "main",
     "entrance esplanade open ground SW of the 3,912 m2 building, "
     "audience field toward the NW gate"),
    ("Cupra", 2.22353, 41.40913, "stage", "main",
     "tiered amphitheatre bowl (OSM 5,928 m2 structure) — anchored"),
    # --- NE waterfront (marina / PV pergola esplanade) ---
    ("Port", 2.22870, 41.41100, "stage", "secondary",
     "NE-most waterfront, marina edge seaward of the PV pergola"),
    ("Cupra Pulse", 2.22790, 41.41070, "stage", "electronic",
     "SW of Port on the pergola esplanade"),
    ("Schwarzkopf", 2.22740, 41.41135, "stage", "secondary",
     "inland of Cupra Pulse, W of the PV pergola platform"),
    # --- club cluster (inland NE strip, between Bosc and the pergola) ---
    ("Fever House", 2.22680, 41.41110, "stage", "club", "club cluster, NE end"),
    ("The Levi's Warehouse", 2.22660, 41.41050, "stage", "club",
     "club cluster centre, open ground E of the 1,448 m2 structure"),
    ("The 501 Club xCOLORSxSTUDIOS", 2.22570, 41.41100, "stage", "club",
     "club cluster, SW of the Warehouse"),
    ("The Levi's Plaza", 2.22520, 41.41130, "stage", "club",
     "club cluster, most inland (N strip)"),
    # --- waterfront promenade, NE->SW: Pro Area, Disney, Sona, [pier], Adidas ---
    ("Primavera Pro Area", 2.22790, 41.41020, "area", "non-stage",
     "promenade NE-most, toward the marina"),
    ("Disney", 2.22690, 41.40970, "stage", "promenade", "promenade, NE of the pier"),
    ("Barcelona Sona by Estrella Damm", 2.22647, 41.40951, "stage", "promenade",
     "promenade at the pier root, just off the pier deck (validated clear)"),
    ("Aperol Island of Joy", 2.22643, 41.40921, "stage", "promenade",
     "Banys del Forum pier — anchored"),
    ("The Adidas Yard", 2.22520, 41.40850, "stage", "promenade",
     "promenade SW of the pier, toward the mains deck"),
    # --- anchored landmarks ---
    ("Radio a demo festival", 2.22482, 41.41049, "area", "non-stage",
     "under the Bosc de columnes canopy — anchored"),
    ("Auditori Rockdelux", 2.22104, 41.41125, "stage", "indoor",
     "inside the Museu Blau / Auditori Forum building — anchored"),
    # --- access ---
    ("ENTRANCE (main)", 2.22040, 41.41060, "entrance", "main",
     "NW gate beside Museu Blau, El Maresme|Forum metro side (single main entrance, 2026)"),
    ("EXIT (Auditori)", 2.22160, 41.41180, "exit", "main",
     "exit lane on the N side of the Museu Blau building"),
]


def main() -> None:
    feats = []
    for name, lon, lat, kind, cls, note in FEATURES:
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {
                "name": name, "kind": kind, "capacity_class": cls,
                "placement": note,
                "source": ("primavera 2026 official map (adjacency) + OSM landmarks (anchors) "
                           "+ user ground truth (mains on the SW deck), manual zone placement v3"),
                "accuracy_m": "20-40 (ASSUMED, cartoon-map source limit)",
                "edition": 2026,
            },
        })
    out = {"type": "FeatureCollection", "features": feats}
    (DATA / "stages_2026.geojson").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {DATA / 'stages_2026.geojson'} ({len(feats)} features)")


if __name__ == "__main__":
    main()
