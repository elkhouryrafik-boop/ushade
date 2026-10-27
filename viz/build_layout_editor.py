"""Build viz/layout_editor.html — drag-and-drop layout editor for the 2026 Primavera layout.

Left: satellite map (MapLibre, Esri imagery) with all 21 features as DRAGGABLE markers,
plus boundary / no-go / green context layers. Right: the official 2026 festival map image
for visual reference (pan/zoom). "Save layout" downloads stages_2026_edited.geojson with
every feature's current position; the user hands that back and it becomes canonical.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "layout_editor.html"

festival = json.loads((DATA / "festival_map_2026.geojson").read_text(encoding="utf-8"))
boundary = json.loads((DATA / "boundary_2026.geojson").read_text(encoding="utf-8"))
nogo = json.loads((DATA / "walkable_nogo_2026.geojson").read_text(encoding="utf-8"))
green = json.loads((DATA / "green.geojson").read_text(encoding="utf-8"))

# stages + access stay draggable; the 65 amenities render as a light reference layer
stages = {
    "type": "FeatureCollection",
    "features": [f for f in festival["features"] if f["properties"].get("layer") in ("stage", "access")],
}
amenities = {
    "type": "FeatureCollection",
    "features": [f for f in festival["features"] if f["properties"].get("layer") == "amenity"],
}

html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>HeatGuard — Primavera 2026 Layout Editor</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet"/>
<style>
  html,body{margin:0;height:100%;font-family:system-ui,Segoe UI,sans-serif;background:#0e1014;color:#eee}
  #wrap{display:flex;height:100%}
  #left{flex:1.2;position:relative;min-width:0}
  #map{position:absolute;inset:0}
  #right{flex:1;display:flex;flex-direction:column;border-left:2px solid #333;min-width:0}
  #right .hdr{padding:8px 12px;font-size:13px;color:#bbb;background:#16181d}
  #imgbox{flex:1;overflow:hidden;position:relative;cursor:grab;background:#000}
  #imgbox img{position:absolute;transform-origin:0 0;user-select:none;-webkit-user-drag:none}
  #bar{position:absolute;top:10px;left:10px;z-index:5;background:rgba(20,22,28,.92);
       padding:10px 14px;border-radius:10px;font-size:12.5px;max-width:300px;line-height:1.5}
  #bar h1{font-size:14px;margin:0 0 4px}
  #bar button{background:#16a34a;color:#fff;border:0;border-radius:7px;padding:8px 14px;
              font-size:13px;font-weight:600;cursor:pointer;margin-top:8px;width:100%}
  #bar button:hover{background:#15803d}
  #bar .moved{color:#fbbf24}
  .mk{display:flex;flex-direction:column;align-items:center;cursor:grab}
  .mk .dot{width:14px;height:14px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 4px #000}
  .mk .lbl{margin-top:2px;font-size:10.5px;font-weight:600;color:#fff;
           text-shadow:0 0 3px #000,0 0 3px #000;white-space:nowrap;pointer-events:none}
  .mk.moved .dot{border-color:#fbbf24;box-shadow:0 0 6px #fbbf24}
</style>
</head>
<body>
<div id="wrap">
  <div id="left">
    <div id="map"></div>
    <div id="bar">
      <h1>Layout editor</h1>
      Drag any point to its true spot (yellow ring = moved).
      Blue line = REVISED site boundary (pier + promenade now included).
      Faint white dots = amenities (not draggable here).
      Right pane = official 2026 map for reference (drag to pan, wheel to zoom).
      <div id="status">moved: <span id="nmoved" class="moved">0</span> / <span id="ntotal"></span></div>
      <button id="save">&#128190; Save layout (downloads .geojson)</button>
    </div>
  </div>
  <div id="right">
    <div class="hdr">Official a demo festival 2026 map (reference — sea is up on this image)</div>
    <div id="imgbox"><img id="refimg" src="reference/primavera_2026_official_map.png"/></div>
  </div>
</div>
<script>
const FEATURES = __STAGES__;
const AMENITIES = __AMENITIES__;
const BOUNDARY = __BOUNDARY__;
const NOGO = __NOGO__;
const GREEN = __GREEN__;

const COLORS = {stage:'#f59e0b', entrance:'#22c55e', exit:'#38bdf8', area:'#c084fc', radio:'#c084fc'};

const m = new maplibregl.Map({
  container:'map', center:[2.22541,41.40998], zoom:15.4,
  style:{version:8,
    glyphs:'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources:{esri:{type:'raster',
      tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize:256, attribution:'Imagery © Esri'}},
    layers:[{id:'esri',type:'raster',source:'esri'}]}
});
m.addControl(new maplibregl.NavigationControl());

m.on('load', () => {
  m.addSource('green',{type:'geojson',data:GREEN});
  m.addLayer({id:'green-fill',type:'fill',source:'green',paint:{'fill-color':'#16a34a','fill-opacity':0.22}});
  m.addSource('nogo',{type:'geojson',data:NOGO});
  m.addLayer({id:'nogo-fill',type:'fill',source:'nogo',paint:{'fill-color':'#ef4444','fill-opacity':0.26}});
  m.addLayer({id:'nogo-line',type:'line',source:'nogo',paint:{'line-color':'#ef4444','line-width':0.8,'line-opacity':0.6}});
  m.addSource('boundary',{type:'geojson',data:BOUNDARY});
  m.addLayer({id:'boundary-line',type:'line',source:'boundary',paint:{'line-color':'#60a5fa','line-width':2.5}});
  m.addSource('amenities',{type:'geojson',data:AMENITIES});
  m.addLayer({id:'amenity-pts',type:'circle',source:'amenities',
    paint:{'circle-radius':3,'circle-color':'#fff','circle-opacity':0.55,
           'circle-stroke-color':'#000','circle-stroke-width':0.5}});
});

document.getElementById('ntotal').textContent = FEATURES.features.length;
const markers = [];
let nMoved = 0;
for (const f of FEATURES.features) {
  const el = document.createElement('div');
  el.className = 'mk';
  const kind = f.properties.kind || 'stage';
  const color = COLORS[kind] || '#f59e0b';
  el.innerHTML = `<div class="dot" style="background:${color}"></div><div class="lbl">${f.properties.name}</div>`;
  const mk = new maplibregl.Marker({element:el, draggable:true, anchor:'top'})
    .setLngLat(f.geometry.coordinates).addTo(m);
  mk._feature = f; mk._moved = false;
  mk.on('dragend', () => {
    const p = mk.getLngLat();
    f.geometry.coordinates = [ +p.lng.toFixed(6), +p.lat.toFixed(6) ];
    if (!mk._moved) { mk._moved = true; nMoved++; el.classList.add('moved');
      document.getElementById('nmoved').textContent = nMoved; }
    f.properties.user_adjusted = true;
  });
  markers.push(mk);
}

document.getElementById('save').onclick = () => {
  const out = JSON.parse(JSON.stringify(FEATURES));
  out._edited = {on: new Date().toISOString(), moved: nMoved, tool: 'layout_editor.html'};
  for (const f of out.features) {
    if (f.properties.user_adjusted) {
      f.properties.accuracy_m = 'user-placed (ground truth)';
      f.properties.source = (f.properties.source || '') + ' + user manual adjustment (layout_editor)';
    }
  }
  const blob = new Blob([JSON.stringify(out, null, 2)], {type:'application/geo+json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'stages_2026_edited.geojson';
  a.click();
};

// --- right pane: pan/zoom the official map image ---
const box = document.getElementById('imgbox'), img = document.getElementById('refimg');
let s=0.35, tx=0, ty=0, panning=false, px=0, py=0;
function apply(){ img.style.transform = `translate(${tx}px,${ty}px) scale(${s})`; }
img.onload = () => { s = box.clientWidth / img.naturalWidth; apply(); };
box.addEventListener('wheel', e => {
  e.preventDefault();
  const r = box.getBoundingClientRect(), mx = e.clientX-r.left, my = e.clientY-r.top;
  const k = e.deltaY < 0 ? 1.15 : 1/1.15;
  tx = mx - (mx - tx)*k; ty = my - (my - ty)*k; s *= k; apply();
});
box.addEventListener('mousedown', e => { panning=true; px=e.clientX; py=e.clientY; box.style.cursor='grabbing'; });
window.addEventListener('mousemove', e => {
  if(!panning) return; tx += e.clientX-px; ty += e.clientY-py; px=e.clientX; py=e.clientY; apply();
});
window.addEventListener('mouseup', () => { panning=false; box.style.cursor='grab'; });
</script>
</body>
</html>
"""

for key, obj in [("__STAGES__", stages), ("__AMENITIES__", amenities), ("__BOUNDARY__", boundary), ("__NOGO__", nogo), ("__GREEN__", green)]:
    html = html.replace(key, json.dumps(obj))

OUT.write_text(html, encoding="utf-8")
print(f"OK wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB), {len(stages['features'])} draggable features")
