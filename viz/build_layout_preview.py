"""Build viz/layout_preview.html — a demo festival @ Parc del Fòrum layout for user approval.

Demo artifact (PRD untouched). Reads the sibling NatureGooddest plan-traced festival map,
adds proposed entrance points (real-world access: El Maresme|Fòrum metro NW, Diagonal Mar SW,
Sant Adrià esplanade NE), and emits one self-contained interactive HTML (MapLibre + Esri
World Imagery tiles — no API key needed).

Entrances are PROPOSED (snapped to the festival boundary nearest each real access direction)
and labelled as such — the user approves/moves them before any simulation runs.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

SIBLING = Path(r"examples/stages_2026_edited.geojson Resources\NatureGooddest\assets\festival_map")
HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "layout_preview.html"

# Real-world access directions (lon, lat) — snapped to nearest boundary vertex below.
# Sources: primaverasound.com how-to-arrive (El Maresme|Fòrum L4 main), Diagonal Mar,
# Sant Adrià coastline. PROPOSED until user approves.
ENTRANCE_SEEDS = [
    {"name": "Main — El Maresme|Fòrum (metro L4)", "lonlat": (2.2200, 41.4115), "kind": "main"},
    {"name": "SW — Diagonal Mar / Plaça del Fòrum", "lonlat": (2.2210, 41.4070), "kind": "secondary"},
    {"name": "NE — Sant Adrià esplanade", "lonlat": (2.2290, 41.4120), "kind": "secondary"},
]


def load(name: str) -> dict:
    return json.loads((SIBLING / name).read_text(encoding="utf-8"))


def all_boundary_vertices(boundary: dict) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for feat in boundary["features"]:
        geom = feat["geometry"]
        rings = geom["coordinates"] if geom["type"] == "Polygon" else [r for p in geom["coordinates"] for r in p]
        for ring in rings:
            pts.extend((float(x), float(y)) for x, y in ring)
    return pts


def snap(seed: tuple[float, float], verts: list[tuple[float, float]]) -> tuple[float, float]:
    sx, sy = seed
    # crude lon/lat metric is fine at this scale (snap target, not survey)
    return min(verts, key=lambda v: math.hypot((v[0] - sx) * math.cos(math.radians(sy)), v[1] - sy))


def main() -> None:
    boundary = load("boundary.geojson")
    stages = load("stages.geojson")
    buildings = load("buildings.geojson")
    site = load("site_elements.geojson")
    meta = load("meta.json")

    # keep only the layers useful for the layout view
    nogo = {
        "type": "FeatureCollection",
        "features": [
            f for f in site["features"]
            if f["geometry"]["type"] == "Polygon" and f["properties"].get("nogo")
        ],
    }
    green = {
        "type": "FeatureCollection",
        "features": [
            f for f in site["features"]
            if f["geometry"]["type"] == "Polygon" and f["properties"].get("element_class") == "green"
        ],
    }

    verts = all_boundary_vertices(boundary)
    entrances = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": list(snap(e["lonlat"], verts))},
                "properties": {"name": e["name"], "kind": e["kind"], "status": "PROPOSED"},
            }
            for e in ENTRANCE_SEEDS
        ],
    }

    DATA.mkdir(exist_ok=True)
    for fname, obj in [
        ("boundary.geojson", boundary),
        ("stages.geojson", stages),
        ("buildings.geojson", buildings),
        ("nogo.geojson", nogo),
        ("green.geojson", green),
        ("entrances.geojson", entrances),
    ]:
        (DATA / fname).write_text(json.dumps(obj), encoding="utf-8")

    center = meta["center"]
    html = HTML_TEMPLATE
    for key, obj in [
        ("__BOUNDARY__", boundary),
        ("__STAGES__", stages),
        ("__BUILDINGS__", buildings),
        ("__NOGO__", nogo),
        ("__GREEN__", green),
        ("__ENTRANCES__", entrances),
    ]:
        html = html.replace(key, json.dumps(obj))
    html = html.replace("__CENTER__", json.dumps(center))
    OUT.write_text(html, encoding="utf-8")
    print(f"OK wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB), "
          f"{len(stages['features'])} stages, {len(entrances['features'])} proposed entrances")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>HeatGuard — a demo festival @ Parc del Fòrum — Layout Preview</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet"/>
<style>
  html,body{margin:0;height:100%;font-family:system-ui,Segoe UI,sans-serif}
  #map{position:absolute;inset:0}
  .panel{position:absolute;top:12px;left:12px;z-index:2;background:rgba(20,22,28,.88);color:#eee;
         padding:14px 16px;border-radius:10px;max-width:330px;font-size:13px;line-height:1.45}
  .panel h1{font-size:15px;margin:0 0 6px}
  .panel .sub{color:#aaa;font-size:11px}
  .legend{margin-top:8px}
  .legend div{display:flex;align-items:center;gap:8px;margin:3px 0}
  .sw{width:14px;height:14px;border-radius:3px;flex:0 0 14px}
  .badge{display:inline-block;background:#c2410c;color:#fff;border-radius:4px;
         padding:1px 6px;font-size:10px;font-weight:600;margin-left:6px}
  .maplibregl-popup-content{color:#111;font-size:12px}
</style>
</head>
<body>
<div class="panel">
  <h1>Layout preview — for approval <span class="badge">PROPOSED</span></h1>
  <div class="sub">a demo festival — Parc del Fòrum, Barcelona.<br/>
  Stages: plan-traced (NatureGooddest sibling). Entrances: proposed from real access
  routes (metro L4 / Diagonal Mar / Sant Adrià) — say the word and I move them.</div>
  <div class="legend">
    <div><span class="sw" style="background:#f59e0b"></span>Stage (size = capacity class)</div>
    <div><span class="sw" style="background:#22c55e"></span>Proposed entrance</div>
    <div><span class="sw" style="background:#60a5fa;opacity:.85"></span>Festival boundary</div>
    <div><span class="sw" style="background:#ef4444;opacity:.55"></span>No-go (buildings, pergolas, piers)</div>
    <div><span class="sw" style="background:#16a34a;opacity:.5"></span>Grass / green</div>
  </div>
</div>
<div id="map"></div>
<script>
const map = new maplibregl.Map({
  container:'map',
  center: __CENTER__,
  zoom: 15.2,
  style: {
    version: 8,
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources: {
      esri: {
        type:'raster',
        tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        attribution: 'Imagery © Esri'
      }
    },
    layers: [{id:'esri', type:'raster', source:'esri'}]
  }
});
map.addControl(new maplibregl.NavigationControl());

const DATA = {
  boundary: __BOUNDARY__,
  stages: __STAGES__,
  buildings: __BUILDINGS__,
  nogo: __NOGO__,
  green: __GREEN__,
  entrances: __ENTRANCES__
};

map.on('load', () => {
  map.addSource('boundary',{type:'geojson',data:DATA.boundary});
  map.addLayer({id:'boundary-line',type:'line',source:'boundary',
    paint:{'line-color':'#60a5fa','line-width':2.5}});

  map.addSource('green',{type:'geojson',data:DATA.green});
  map.addLayer({id:'green-fill',type:'fill',source:'green',
    paint:{'fill-color':'#16a34a','fill-opacity':0.25}});

  map.addSource('nogo',{type:'geojson',data:DATA.nogo});
  map.addLayer({id:'nogo-fill',type:'fill',source:'nogo',
    paint:{'fill-color':'#ef4444','fill-opacity':0.30}});
  map.addLayer({id:'nogo-line',type:'line',source:'nogo',
    paint:{'line-color':'#ef4444','line-width':0.8,'line-opacity':0.7}});

  map.addSource('stages',{type:'geojson',data:DATA.stages});
  map.addLayer({id:'stage-pts',type:'circle',source:'stages',
    paint:{
      'circle-radius':['match',['get','capacity_class'],'main',11,'secondary',8,6],
      'circle-color':'#f59e0b','circle-stroke-color':'#fff','circle-stroke-width':2
    }});
  map.addLayer({id:'stage-labels',type:'symbol',source:'stages',
    layout:{'text-field':['get','name'],'text-size':12,'text-offset':[0,1.4],
            'text-font':['Noto Sans Regular']},
    paint:{'text-color':'#fff','text-halo-color':'#000','text-halo-width':1.4}});

  map.addSource('entrances',{type:'geojson',data:DATA.entrances});
  map.addLayer({id:'ent-pts',type:'circle',source:'entrances',
    paint:{'circle-radius':['match',['get','kind'],'main',12,9],
           'circle-color':'#22c55e','circle-stroke-color':'#fff','circle-stroke-width':2.5}});
  map.addLayer({id:'ent-labels',type:'symbol',source:'entrances',
    layout:{'text-field':['get','name'],'text-size':11.5,'text-offset':[0,1.5],
            'text-font':['Noto Sans Regular']},
    paint:{'text-color':'#bbf7d0','text-halo-color':'#000','text-halo-width':1.4}});

  for (const [layer, getHTML] of [
    ['stage-pts', p => `<b>${p.name}</b><br/>class: ${p.capacity_class}<br/><i>${p.coords_status}</i>`],
    ['ent-pts',   p => `<b>${p.name}</b><br/>status: ${p.status}`]
  ]) {
    map.on('click', layer, e => {
      const f = e.features[0];
      new maplibregl.Popup().setLngLat(f.geometry.coordinates)
        .setHTML(getHTML(f.properties)).addTo(map);
    });
    map.on('mouseenter', layer, () => map.getCanvas().style.cursor='pointer');
    map.on('mouseleave', layer, () => map.getCanvas().style.cursor='');
  }
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
