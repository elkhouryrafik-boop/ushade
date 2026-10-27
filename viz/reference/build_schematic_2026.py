"""Render primavera_2026_schematic.svg from the georeferenced data (north-up plan view).

The schematic is GENERATED from viz/data/*.geojson (boundary, no-go structures, green,
stages_2026) so it is consistent with the georeferenced truth by construction — unlike
the v1 hand-drawn schematic which mimicked the official map's isometric layout.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
OUT = HERE / "primavera_2026_schematic.svg"

W, H, PAD = 1100, 760, 40
CLS_COLOR = {
    "main": "#dc2626", "electronic": "#a855f7", "secondary": "#f59e0b",
    "club": "#0ea5e9", "promenade": "#0d9488", "indoor": "#1d4ed8",
    "non-stage": "#64748b",
}


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def main() -> None:
    boundary, nogo, green, stages = (load(n) for n in
        ("boundary.geojson", "nogo.geojson", "green.geojson", "stages_2026.geojson"))

    # local metric frame (equirectangular about site centre)
    lats, lons = [], []
    for f in boundary["features"]:
        for ring in f["geometry"]["coordinates"]:
            for x, y in ring:
                lons.append(x); lats.append(y)
    lon0, lat0 = (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
    kx = 111320 * math.cos(math.radians(lat0))
    ky = 110540

    def metres(lon, lat):
        return (lon - lon0) * kx, (lat - lat0) * ky

    pts = [metres(x, y) for x, y in zip(lons, lats)]
    mxs, mys = [p[0] for p in pts], [p[1] for p in pts]
    span_x, span_y = max(mxs) - min(mxs), max(mys) - min(mys)
    scale = min((W - 2 * PAD) / span_x, (H - 2 * PAD) / span_y)

    def px(lon, lat):
        mx, my = metres(lon, lat)
        return (PAD + (mx - min(mxs)) * scale,
                H - PAD - (my - min(mys)) * scale)  # y up = north up

    def path(rings):
        d = []
        for ring in rings:
            d.append("M " + " L ".join(f"{px(x, y)[0]:.1f} {px(x, y)[1]:.1f}" for x, y in ring) + " Z")
        return " ".join(d)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="system-ui, Segoe UI, sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#dbeafe"/>',  # sea
           f'<text x="{W-200}" y="{H-18}" font-size="13" fill="#1d4ed8" font-style="italic">Mediterranean Sea</text>']

    # site ground
    for f in boundary["features"]:
        svg.append(f'<path d="{path(f["geometry"]["coordinates"])}" fill="#f1f5f9" '
                   f'stroke="#60a5fa" stroke-width="2"/>')
    # green
    for f in green["features"]:
        svg.append(f'<path d="{path(f["geometry"]["coordinates"])}" fill="#bbf7d0" '
                   f'stroke="#4ade80" stroke-width="0.8" opacity="0.8"/>')
    # structures
    for f in nogo["features"]:
        p = f["properties"]
        name = p.get("name") or ""
        cls = p.get("element_class")
        if "Depuradora" in name:
            continue  # platform roof — festival ground, not an obstacle face
        fill = {"pergola": "#c7d2fe", "building": "#cbd5e1", "structure": "#e2e8f0"}.get(cls, "#e2e8f0")
        svg.append(f'<path d="{path(f["geometry"]["coordinates"])}" fill="{fill}" '
                   f'stroke="#64748b" stroke-width="1"/>')

    # landmark labels
    for label, lon, lat, dy in [
        ("Museu Blau / Auditori", 2.22104, 41.41125, 0),
        ("Bosc de columnes", 2.22440, 41.41080, 0),
        ("PV pergola", 2.22828, 41.41146, 0),
        ("Banys del Fòrum pier", 2.22643, 41.40921, 14),
    ]:
        x, y = px(lon, lat)
        svg.append(f'<text x="{x:.0f}" y="{y + dy:.0f}" font-size="10.5" fill="#475569" '
                   f'font-style="italic" text-anchor="middle">{label}</text>')

    # stages
    for f in stages["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        x, y = px(lon, lat)
        kind, cls = p["kind"], p["capacity_class"]
        if kind == "entrance":
            svg.append(f'<rect x="{x-46:.0f}" y="{y-11:.0f}" width="92" height="22" rx="5" fill="#16a34a"/>'
                       f'<text x="{x:.0f}" y="{y+5:.0f}" font-size="12" font-weight="800" '
                       f'text-anchor="middle" fill="#fff">ENTRANCE</text>')
            continue
        if kind == "exit":
            svg.append(f'<rect x="{x-26:.0f}" y="{y-10:.0f}" width="52" height="20" rx="5" fill="#166534"/>'
                       f'<text x="{x:.0f}" y="{y+4:.0f}" font-size="11" font-weight="800" '
                       f'text-anchor="middle" fill="#fff">EXIT</text>')
            continue
        r = {"main": 10, "non-stage": 5}.get(cls, 7)
        color = CLS_COLOR.get(cls, "#334155")
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" '
                   f'stroke="#fff" stroke-width="2"/>')
        weight = "700" if cls == "main" else "600"
        size = 12 if cls == "main" else 10.5
        svg.append(f'<text x="{x:.0f}" y="{y - r - 4:.0f}" font-size="{size}" font-weight="{weight}" '
                   f'text-anchor="middle" fill="#0f172a" stroke="#fff" stroke-width="3" '
                   f'paint-order="stroke">{p["name"]}</text>')

    # north arrow + title + legend
    svg.append(f'<g transform="translate({W-60},70)"><circle r="24" fill="#fff" stroke="#94a3b8"/>'
               f'<path d="M 0 14 L 0 -14 M -5 -7 L 0 -14 L 5 -7" stroke="#334155" stroke-width="2.5" fill="none"/>'
               f'<text y="-30" font-size="13" font-weight="700" text-anchor="middle" fill="#334155">N</text></g>')
    svg.append(f'<text x="{PAD}" y="28" font-size="17" font-weight="800" fill="#0f172a">'
               f'a demo festival 2026 — Parc del Fòrum (georeferenced schematic, north-up)</text>')
    legend = [("main stage", "main"), ("electronic", "electronic"), ("secondary", "secondary"),
              ("club", "club"), ("promenade", "promenade"), ("indoor", "indoor")]
    for i, (lab, cls) in enumerate(legend):
        x = PAD + i * 130
        svg.append(f'<circle cx="{x+7}" cy="48" r="7" fill="{CLS_COLOR[cls]}" stroke="#fff" stroke-width="1.5"/>'
                   f'<text x="{x+20}" y="52" font-size="11.5" fill="#334155">{lab}</text>')
    svg.append(f'<text x="{PAD}" y="{H-14}" font-size="10" fill="#64748b">'
               f'Placement: official 2026 map (adjacency) + OSM landmarks (anchors); accuracy ±20–40 m (ASSUMED). '
               f'Not a survey.</text>')
    svg.append("</svg>")

    OUT.write_text("\n".join(svg), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
