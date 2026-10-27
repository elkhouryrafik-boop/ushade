/**
 * gen-scenario-data.mjs — synthetic "Beyond Festivals" scenario datasets.
 *
 * Emits one JSON per domain into frontend/public/scenarios/<id>.json, in the EXACT
 * shape DaytimeField already consumes (lattice / hours / heat_hours / frames /
 * n_agents / utci_min / utci_max), PLUS the bits the scenario shell needs
 * (bounds corners, attractors in geo, ranked mock zones, headline stats).
 *
 * This is a MOCK: the heat field is a hand-tuned daytime UTCI curve with spatial
 * variation, and the "crowd" is N random-walkers biased toward each domain's
 * attractors — so density blooms on the attractors exactly like the real crowd sim
 * would, and DaytimeField's crowd→heat coupling + worst-cell crosshair light up for
 * free. The ranked zones are derived from the same field (hot × busy), so the side
 * list and the animation agree.
 *
 * Run:  node frontend/scripts/gen-scenario-data.mjs
 * Pure Node, no deps. Deterministic (seeded RNG) so the build is reproducible.
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, "..", "public", "scenarios");

// ── seeded RNG (mulberry32) — deterministic builds ──
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const r1 = (x) => Math.round(x * 10) / 10;
const r2 = (x) => Math.round(x * 100) / 100;
const pad2 = (n) => String(n).padStart(2, "0");

// ── geo: axis-aligned rectangle of side `sizeM` (metres) centred on [lon,lat] ──
function cornersFor(center, sizeM) {
  const [lon, lat] = center;
  const dLat = sizeM / 2 / 111320;
  const dLon = sizeM / 2 / (111320 * Math.cos((lat * Math.PI) / 180));
  return {
    SW: [lon - dLon, lat - dLat],
    SE: [lon + dLon, lat - dLat],
    NE: [lon + dLon, lat + dLat],
    NW: [lon - dLon, lat + dLat],
  };
}
// Bilinear project of grid (col,row) → [lon,lat]. u=W→E, v=S→N (row 0 = south),
// IDENTICAL to DaytimeField.project so attractors/zones line up with the heat field.
function project(corners, col, row, cols, rows) {
  const { SW, SE, NE, NW } = corners;
  const u = col / cols;
  const v = row / rows;
  const lon = (1 - u) * (1 - v) * SW[0] + u * (1 - v) * SE[0] + u * v * NE[0] + (1 - u) * v * NW[0];
  const lat = (1 - u) * (1 - v) * SW[1] + u * (1 - v) * SE[1] + u * v * NE[1] + (1 - u) * v * NW[1];
  return [r2(lon * 1000) / 1000, r2(lat * 1000) / 1000];
}

// ── per-domain configuration ─────────────────────────────────────────────────
// attractors: u,v ∈ [0,1] grid fraction (v=0 south). `pull` weights crowd share.
// ambientLo/Hi: site-air UTCI at dawn/peak. openHot: extra °C in the sun-baked open.
const DOMAINS = [
  {
    id: "park",
    seed: 11,
    site: "Parc de la Ciutadella, Barcelona",
    center: [2.1860, 41.3880],
    sizeM: 210,
    cellM: 7,
    zoom: 16.2,
    clockLabel: "park time",
    date: "Sat 12 Jul",
    ambientLo: 23,
    ambientHi: 35,
    openHot: 4.5,
    canopyM2: 24 * 24,
    pplPerAgent: 22,
    attractors: [
      { name: "PLAYGROUND", kind: "stage", u: 0.30, v: 0.66, pull: 1.5 },
      { name: "FOUNTAIN", kind: "amenity", u: 0.62, v: 0.55, pull: 1.0 },
      { name: "PICNIC LAWN", kind: "stage", u: 0.72, v: 0.30, pull: 1.2 },
      { name: "CAFÉ KIOSK", kind: "amenity", u: 0.45, v: 0.22, pull: 0.8 },
      { name: "MAIN GATE", kind: "entrance", u: 0.10, v: 0.12, pull: 0.6 },
    ],
  },
  {
    id: "playground",
    seed: 23,
    site: "Escola del Mar — schoolyard",
    center: [2.1720, 41.3955],
    sizeM: 90,
    cellM: 3,
    zoom: 17.6,
    clockLabel: "school time",
    date: "Wed 14 May",
    ambientLo: 22,
    ambientHi: 33,
    openHot: 5.5, // bare asphalt yard bakes
    canopyM2: 12 * 12,
    pplPerAgent: 3, // a schoolyard, not a stadium
    attractors: [
      { name: "CLIMBING FRAME", kind: "stage", u: 0.32, v: 0.60, pull: 1.4 },
      { name: "SWINGS", kind: "stage", u: 0.60, v: 0.68, pull: 1.3 },
      { name: "BASKETBALL COURT", kind: "stage", u: 0.70, v: 0.32, pull: 1.1 },
      { name: "SANDPIT", kind: "amenity", u: 0.28, v: 0.30, pull: 0.9 },
      { name: "ASSEMBLY DOOR", kind: "entrance", u: 0.12, v: 0.50, pull: 0.7 },
    ],
  },
  {
    id: "plaza",
    seed: 37,
    site: "Plaça de Catalunya, Barcelona",
    center: [2.1700, 41.3870],
    sizeM: 160,
    cellM: 5,
    zoom: 16.6,
    clockLabel: "city time",
    date: "Thu 24 Jul",
    ambientLo: 24,
    ambientHi: 36,
    openHot: 5.0, // stone plaza, no canopy
    canopyM2: 20 * 20,
    pplPerAgent: 30,
    attractors: [
      { name: "METRO EXIT", kind: "entrance", u: 0.18, v: 0.20, pull: 1.4 },
      { name: "MARKET STALLS", kind: "stage", u: 0.55, v: 0.58, pull: 1.3 },
      { name: "CENTRAL FOUNTAIN", kind: "amenity", u: 0.50, v: 0.40, pull: 0.9 },
      { name: "BUS STOP", kind: "entrance", u: 0.82, v: 0.30, pull: 1.0 },
      { name: "SEATING TERRACE", kind: "amenity", u: 0.72, v: 0.74, pull: 0.8 },
    ],
  },
  {
    id: "beach",
    seed: 53,
    site: "Platja de la Barceloneta",
    center: [2.1930, 41.3780],
    sizeM: 240,
    cellM: 8,
    zoom: 16.0,
    clockLabel: "beach time",
    date: "Sun 03 Aug",
    ambientLo: 25,
    ambientHi: 37,
    openHot: 4.0, // sand reflects, sea breeze tempers
    canopyM2: 24 * 24,
    pplPerAgent: 26,
    attractors: [
      { name: "ACCESS RAMP", kind: "entrance", u: 0.16, v: 0.78, pull: 1.2 },
      { name: "CHIRINGUITO", kind: "stage", u: 0.45, v: 0.60, pull: 1.4 },
      { name: "VOLLEYBALL", kind: "stage", u: 0.70, v: 0.50, pull: 1.0 },
      { name: "SHOWERS", kind: "amenity", u: 0.34, v: 0.40, pull: 0.8 },
      { name: "LIFEGUARD", kind: "amenity", u: 0.58, v: 0.30, pull: 0.7 },
    ],
  },
];

const COLS = 30;
const ROWS = 30;
const HOURS_START = 8; // 08:00 … 20:00 daytime window
const HOURS_END = 20;
const N_AGENTS = 130;
const N_FRAMES = 160;

// daytime UTCI multiplier: a smooth bell peaking ~14:30 (fraction ≈ 0.54 of window)
function dayCurve(frac) {
  const peak = 0.54;
  const w = 0.34;
  return Math.exp(-((frac - peak) ** 2) / (2 * w * w));
}
// "busyness" of the day — how packed the site is at this fraction (ramps up to a
// midday/afternoon peak then eases). Drives how tightly agents cluster on attractors.
function busyCurve(frac) {
  return 0.35 + 0.65 * dayCurve(frac);
}

function build(dom) {
  const rand = rng(dom.seed);
  const corners = cornersFor(dom.center, dom.sizeM);
  const nHours = HOURS_END - HOURS_START + 1;
  const hours = [];
  for (let h = 0; h < nHours; h++) hours.push(`${pad2(HOURS_START + h)}:00`);

  // open-area hot centre (the sun-baked gap between attractors) + cool patches near
  // the leafier/shaded attractors, so iso-contours have something to trace.
  const openU = 0.5 + (rand() - 0.5) * 0.2;
  const openV = 0.46 + (rand() - 0.5) * 0.2;

  // spatial base field (time-independent shape), °C offset from ambient
  const spatial = new Float64Array(COLS * ROWS);
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const u = c / COLS;
      const v = r / ROWS;
      // hot in the open centre
      const dOpen = Math.hypot(u - openU, v - openV);
      let s = dom.openHot * Math.exp(-(dOpen * dOpen) / (2 * 0.22 * 0.22));
      // cooler near shaded/leafy attractors (amenity/stage with greenery)
      for (const a of dom.attractors) {
        const d = Math.hypot(u - a.u, v - a.v);
        s -= 1.6 * Math.exp(-(d * d) / (2 * 0.1 * 0.1));
      }
      // gentle edge cool-down + a little deterministic texture
      s += (rand() - 0.5) * 0.8;
      spatial[r * COLS + c] = s;
    }
  }

  // heat_hours: every hour, every cell (no nulls — whole rectangle is in-site)
  let utciMin = Infinity;
  let utciMax = -Infinity;
  const perHourField = []; // keep for zone scoring
  const heat_hours = hours.map((hour, h) => {
    const frac = h / (nHours - 1);
    const ambient = dom.ambientLo + (dom.ambientHi - dom.ambientLo) * dayCurve(frac);
    const field = new Float64Array(COLS * ROWS);
    const cells = [];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const t = ambient + spatial[r * COLS + c] * (0.5 + 0.5 * dayCurve(frac));
        field[r * COLS + c] = t;
        if (t < utciMin) utciMin = t;
        if (t > utciMax) utciMax = t;
        cells.push([c, r, r1(t)]);
      }
    }
    perHourField.push(field);
    return { hour, cells };
  });

  // ── agents: each owns a "home" attractor (weighted by pull); milling around it,
  // pulled tighter at busy hours, with a small fraction wandering. ──
  const totalPull = dom.attractors.reduce((s, a) => s + a.pull, 0);
  const agents = [];
  for (let k = 0; k < N_AGENTS; k++) {
    let pick = rand() * totalPull;
    let home = dom.attractors[0];
    for (const a of dom.attractors) {
      pick -= a.pull;
      if (pick <= 0) { home = a; break; }
    }
    const wander = rand() < 0.12; // a few free roamers
    agents.push({
      home,
      wander,
      c: home.u * COLS + (rand() - 0.5) * 4,
      r: home.v * ROWS + (rand() - 0.5) * 4,
    });
  }

  const frames = [];
  for (let f = 0; f < N_FRAMES; f++) {
    const frac = f / (N_FRAMES - 1);
    const busy = busyCurve(frac);
    const spread = 5.5 - 3.5 * busy; // cells of scatter around home (tighter midday)
    const snap = []; // [c,r] per agent
    for (const ag of agents) {
      const tc = ag.wander
        ? COLS * (0.5 + 0.42 * Math.sin(frac * 6.28 + ag.home.u * 9))
        : ag.home.u * COLS;
      const tr = ag.wander
        ? ROWS * (0.5 + 0.42 * Math.cos(frac * 6.28 + ag.home.v * 9))
        : ag.home.v * ROWS;
      // ease toward target + jitter scaled by spread
      ag.c += (tc - ag.c) * 0.08 + (rand() - 0.5) * spread * 0.5;
      ag.r += (tr - ag.r) * 0.08 + (rand() - 0.5) * spread * 0.5;
      ag.c = Math.max(0.5, Math.min(COLS - 1.5, ag.c));
      ag.r = Math.max(0.5, Math.min(ROWS - 1.5, ag.r));
      snap.push([r2(ag.c), r2(ag.r)]);
    }
    frames.push(snap);
  }

  // ── density integral per cell (avg agents over all frames) ──
  const dens = new Float64Array(COLS * ROWS);
  for (const snap of frames) {
    for (const [c, r] of snap) {
      const ci = c | 0;
      const ri = r | 0;
      if (ci >= 0 && ci < COLS && ri >= 0 && ri < ROWS) dens[ri * COLS + ci]++;
    }
  }
  for (let i = 0; i < dens.length; i++) dens[i] /= frames.length;

  // peak felt heat per cell over the day (max across hours)
  const peakHeat = new Float64Array(COLS * ROWS);
  for (const field of perHourField) {
    for (let i = 0; i < field.length; i++) peakHeat[i] = Math.max(peakHeat[i], field[i]);
  }

  // ── rank zones: score = (heat over 26 °C) × density, with min separation ──
  const scored = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const i = r * COLS + c;
      const heatTerm = Math.max(0, peakHeat[i] - 26);
      const score = heatTerm * (dens[i] + 0.15);
      scored.push({ c, r, score, peak: peakHeat[i], dens: dens[i] });
    }
  }
  scored.sort((a, b) => b.score - a.score);
  const chosen = [];
  for (const s of scored) {
    if (chosen.every((z) => Math.hypot(z.c - s.c, z.r - s.r) >= 5)) chosen.push(s);
    if (chosen.length >= 5) break;
  }

  const PPL_PER_AGENT = dom.pplPerAgent ?? 60;
  const densTotal = dens.reduce((a, b) => a + b, 0);
  const half = 2; // footprint half-width in cells
  const zones = chosen.map((s, idx) => {
    const rank = idx + 1;
    const center = project(corners, s.c + 0.5, s.r + 0.5, COLS, ROWS);
    const footprint = [
      project(corners, s.c - half, s.r - half, COLS, ROWS),
      project(corners, s.c + half, s.r - half, COLS, ROWS),
      project(corners, s.c + half, s.r + half, COLS, ROWS),
      project(corners, s.c - half, s.r + half, COLS, ROWS),
    ];
    const crowdShare = densTotal > 0 ? Math.round((s.dens / densTotal) * 100 * 9) : 0;
    const marginalDemand = Math.round(s.dens * PPL_PER_AGENT * (4 * half * half));
    const heat = s.peak >= 32 ? "Dangerous heat" : "High heat";
    const why = rank <= 2 ? `${heat} × dense crowd` : rank === 3 ? `${heat} × busy ground` : `${heat} × crowd flow`;
    const coolingC = r1(3.6 + 0.9 * dayCurve(0.54) + (5 - rank) * 0.18);
    return {
      rank,
      center,
      footprint,
      areaM2: dom.canopyM2,
      peakC: r1(s.peak),
      whyHere: why,
      marginalDemand,
      crowdShare: Math.min(crowdShare, 60),
      coolingC,
    };
  });

  const peopleInHeat = Math.round(
    zones.reduce((a, z) => a + z.marginalDemand, 0) * 1.5 +
      densTotal * PPL_PER_AGENT * 0.4,
  );
  const headline = { peakC: r1(utciMax), peopleInHeat };

  // attractors in geo for the map labels/dots
  const attractorsGeo = dom.attractors.map((a) => {
    const [lon, lat] = project(corners, a.u * COLS, a.v * ROWS, COLS, ROWS);
    return { name: a.name, kind: a.kind, lon, lat };
  });

  return {
    site: dom.site,
    date: dom.date,
    clockLabel: dom.clockLabel,
    zoom: dom.zoom,
    center: dom.center,
    bounds: corners,
    lattice: { cols: COLS, rows: ROWS, cell_size_m: dom.cellM },
    hours,
    heat_hours,
    frames,
    n_agents: N_AGENTS,
    utci_min: r1(utciMin),
    utci_max: r1(utciMax),
    attractors: attractorsGeo,
    zones,
    headline,
  };
}

mkdirSync(OUT_DIR, { recursive: true });
for (const dom of DOMAINS) {
  const data = build(dom);
  const path = join(OUT_DIR, `${dom.id}.json`);
  writeFileSync(path, JSON.stringify(data));
  const kb = (Buffer.byteLength(JSON.stringify(data)) / 1024).toFixed(0);
  console.log(`✓ ${dom.id}.json — ${kb} KB · peak ${data.headline.peakC}°C · ${data.zones.length} zones · ${data.headline.peopleInHeat} ppl`);
}
console.log(`\nWrote ${DOMAINS.length} scenario datasets → public/scenarios/`);
