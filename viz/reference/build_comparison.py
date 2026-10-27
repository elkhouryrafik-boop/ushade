"""Build map_comparison.html — official 2026 map (left) vs georeferenced satellite (right).

Right pane: Esri World Imagery + OSM truth layers (boundary, no-go incl. pergolas/buildings/
pier) + the affine-georeferenced 2026 stages. Used to eyeball + hand-correct placements;
corrections live in georef_stages_2026.py / NUDGES below.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
OUT = HERE / "map_comparison.html"

# hand corrections applied AFTER the affine (lon, lat) — empty until eyeball pass
NUDGES: dict[str, tuple[float, float]] = {}


def main() -> None:
    stages = json.loads((DATA / "stages_2026.geojson").read_text(encoding="utf-8"))
    for f in stages["features"]:
        n = f["properties"]["name"]
        if n in NUDGES:
            f["geometry"]["coordinates"] = list(NUDGES[n])
            f["properties"]["nudged"] = True
    boundary = json.loads((DATA / "boundary.geojson").read_text(encoding="utf-8"))
    nogo = json.loads((DATA / "nogo.geojson").read_text(encoding="utf-8"))

    html = TEMPLATE
    html = html.replace("__STAGES__", json.dumps(stages))
    html = html.replace("__BOUNDARY__", json.dumps(boundary))
    html = html.replace("__NOGO__", json.dumps(nogo))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Primavera 2026 — official map vs georeferenced placement</title>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet"/>
<style>
  html,body{margin:0;height:100%;font-family:system-ui,sans-serif;background:#0f1115;color:#eee}
  .wrap{display:flex;height:100vh}
  .half{flex:1;position:relative;min-width:0}
  .half h2{position:absolute;top:8px;left:10px;z-index:5;margin:0;font-size:13px;
           background:rgba(0,0,0,.65);padding:5px 10px;border-radius:6px}
  #left{overflow:auto;background:#1a1d23}
  #left img{width:100%;display:block}
  #map{position:absolute;inset:0}
</style>
</head>
<body>
<div class="wrap" style="flex-direction:column">
  <div style="display:flex;flex:1;min-height:0">
    <div class="half" id="left">
      <h2>Official 2026 map (primaverasound.com)</h2>
      <img src="primavera_2026_official_map.png" alt="official map"/>
    </div>
    <div class="half" id="schem" style="overflow:auto;background:#fff">
      <h2>Generated schematic (north-up, georeferenced)</h2>
      <img src="primavera_2026_schematic.svg" alt="schematic" style="width:100%;display:block"/>
    </div>
  </div>
  <div class="half" style="flex:1">
    <h2>Verification — satellite + OSM truth + placed stages</h2>
    <div id="map"></div>
  </div>
</div>
<script>
const map = new maplibregl.Map({
  container:'map', center:[2.22455,41.40995], zoom:15.4,
  style:{version:8,
    glyphs:'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources:{esri:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],tileSize:256,attribution:'Imagery © Esri'}},
    layers:[{id:'esri',type:'raster',source:'esri'}]}
});
map.addControl(new maplibregl.NavigationControl());
const STAGES=__STAGES__, BOUNDARY=__BOUNDARY__, NOGO=__NOGO__;
const CLS_COLOR={main:'#ef4444',electronic:'#a855f7',secondary:'#f59e0b',club:'#38bdf8',
                 promenade:'#2dd4bf',indoor:'#1d4ed8','non-stage':'#94a3b8'};
map.on('load',()=>{
  map.addSource('boundary',{type:'geojson',data:BOUNDARY});
  map.addLayer({id:'b-line',type:'line',source:'boundary',paint:{'line-color':'#60a5fa','line-width':2}});
  map.addSource('nogo',{type:'geojson',data:NOGO});
  map.addLayer({id:'n-fill',type:'fill',source:'nogo',paint:{'fill-color':'#ef4444','fill-opacity':0.18}});
  map.addLayer({id:'n-line',type:'line',source:'nogo',paint:{'line-color':'#f87171','line-width':0.7,'line-opacity':0.6}});
  map.addSource('stages',{type:'geojson',data:STAGES});
  map.addLayer({id:'s-pts',type:'circle',source:'stages',paint:{
    'circle-radius':['match',['get','kind'],'entrance',10,'exit',8,
        ['match',['get','capacity_class'],'main',10,'non-stage',5,7]],
    'circle-color':['match',['get','kind'],'entrance','#22c55e','exit','#166534',
        ['match',['get','capacity_class'],
         'main',CLS_COLOR.main,'electronic',CLS_COLOR.electronic,'secondary',CLS_COLOR.secondary,
         'club',CLS_COLOR.club,'promenade',CLS_COLOR.promenade,'indoor',CLS_COLOR.indoor,
         CLS_COLOR['non-stage']]],
    'circle-stroke-color':'#fff','circle-stroke-width':2}});
  map.addLayer({id:'s-lab',type:'symbol',source:'stages',layout:{
    'text-field':['get','name'],'text-size':10.5,'text-offset':[0,1.3],
    'text-font':['Noto Sans Regular'],'text-allow-overlap':false},
    paint:{'text-color':'#fff','text-halo-color':'#000','text-halo-width':1.3}});
  map.on('click','s-pts',e=>{
    const f=e.features[0];
    new maplibregl.Popup().setLngLat(f.geometry.coordinates)
      .setHTML(`<b style="color:#111">${f.properties.name}</b><br/><span style="color:#333">${f.properties.capacity_class} · ${f.properties.kind}<br/>${f.geometry.coordinates.map(v=>v.toFixed(6)).join(', ')}</span>`).addTo(map);
  });
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
