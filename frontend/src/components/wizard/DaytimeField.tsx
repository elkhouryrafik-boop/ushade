import { useEffect, useMemo, useRef, useState } from "react";
import { useControl } from "react-map-gl/mapbox";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { BitmapLayer, ScatterplotLayer, PathLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Play, Pause, WarningTriangle } from "iconoir-react";
import { EASE, DUR } from "@/lib/motion";
import type { Corners } from "@/lib/scenarios";

/**
 * DaytimeField — the product's signature screen.
 *
 * A geo-anchored, day-clocked "daytime field" deck.gl overlay that animates the
 * festival heat × crowd across the real festival day, on the persistent Mapbox map.
 * It is a faithful port of presentations/daytime-animation.html (the 368-line canvas
 * renderer) onto the app's map as a BitmapLayer (heat) + iso-contour BitmapLayer +
 * two ScatterplotLayer/TripsLayer crowd overlays + a worst-cell danger crosshair,
 * all driven by ONE shared day-clock `head` ∈ [0, frames.length-1].
 *
 * Data: /daytime_anim_data.js (~11 MB) injected once on mount → window.ANIM_DATA.
 *
 * Perf: runs on its OWN dedicated MapboxOverlay (a second overlay, exactly like
 * TrajectoryPlayback) so the per-frame tick only re-renders THIS overlay's layers —
 * the heavy primary heat/crowd/zone field never rebuilds during animation. The rAF
 * loop is STOPPED whenever paused (no idle loop — it would block the page + screenshots).
 *
 * The crowd→heat coupling (CD-B, port of src/climate/crowd_heat.py) is recomputed per
 * frame so the thermal field visibly blooms hotter where the crowd packs.
 *
 * The thermal-camera look (per s6-heatmap.png): near-black basemap, a glowing INFERNO
 * field, bright dashed iso-contour rings tracing UTCI bands (26 / 32 / 38 °C) with the
 * 32 °C DANGER band rendered crisper/brighter, leader-tagged zones, a top LIVE status
 * bar, a UTCI legend, and a worst-minute danger crosshair that BLOOMS and SETTLES.
 */

// ── Grid → geo: the 139×153 @6m UTM31N lattice projected to WGS84 (EPSG:32631→4326).
// UTM grid north ≠ true north (convergence) so the projected lattice is a slightly
// ROTATED quad — an axis-aligned bbox would skew it. We map the image onto the FOUR
// true corner points instead (exact alignment with the basemap streets). row 0 = SOUTH.
//
// These are the FESTIVAL (Parc del Fòrum) corners — the default. "Beyond Festivals"
// scenarios pass their own corners via the `bounds` prop; the projection math is
// identical, so the same engine renders a park / schoolyard / plaza / beach. ──
const FEST_CORNERS: Corners = {
  SW: [2.219663266099213, 41.40541203221961],
  SE: [2.2296403300048584, 41.40547926628817],
  NE: [2.2295426464668866, 41.41374749058399],
  NW: [2.219564317755477, 41.4136802370837],
};

// ── INFERNO colormap (verbatim from the HTML) ──
const INFERNO: [number, number, number][] = [
  [12, 8, 38], [40, 11, 84], [101, 21, 110], [159, 42, 99],
  [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164],
];

// ── CD-B crowd→heat constants (PORT of src/climate/crowd_heat.py, verbatim) ──
const CH = {
  RHO_CP: 1200, FRUIN: 6, P_W: 150, SENS: 0.36, MIX_H: 2.5,
  V0: 2.5, WBLOCK: 0.7, K_WIND: 0.7, K_HUMID: 1.4, CAP: 4, VMIN: 0.3,
  PPL_PER_AGENT: 100,
};

// ── Additive blending (luma.gl v9 params) — overlapping crowd dots/trails sum their
// light, so dense convergence points (the stages) glow brighter. ──
const ADDITIVE = {
  blend: true,
  blendColorOperation: "add",
  blendColorSrcFactor: "src-alpha",
  blendColorDstFactor: "one",
  blendAlphaOperation: "add",
  blendAlphaSrcFactor: "one",
  blendAlphaDstFactor: "one",
  depthCompare: "always",
} as const;

// A per-frame agent hop bigger than this (in cells) is a re-path discontinuity — snap,
// don't streak a trail across the whole map (teleport guard, from the HTML).
const JUMP = 10;

// People dots: scatter this many small jittered dots around each agent so the layer
// reads as a full crowd ("people everywhere") rather than 650 discrete points. Each
// agent ≈ 100 people; ~8 representative dots keeps it legible.
const DOTS_PER_AGENT = 8;

// Iso-contour bands (°C) drawn over the inferno field — the "topo map of heat" the spec
// calls the biggest "this is real science" signal (u-shade-spec A4). 32 is the DANGER line.
const CONTOUR_BANDS = [26, 32, 38] as const;
const DANGER_C = 32; // the dangerous-heat line (UI-SPEC §4.1)

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);

/** Sample a colormap at t ∈ [0,1] with linear interpolation between stops. */
function ramp(stops: [number, number, number][], t: number): [number, number, number] {
  t = clamp01(t);
  const n = stops.length - 1;
  const sg = t * n;
  const i = Math.min(n - 1, Math.floor(sg));
  const f = sg - i;
  const a = stops[i];
  const b = stops[i + 1];
  return [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)];
}

/** People/m² (port of pplM2 in the HTML). */
function pplM2(agents: number, cellM: number): number {
  return clamp01((agents * CH.PPL_PER_AGENT) / (cellM * cellM) / CH.FRUIN) * CH.FRUIN;
}

/** ΔUTCI from crowd density (port of dUTCI in the HTML). */
function dUTCI(ppl: number, cellM: number): number {
  const d = Math.min(ppl, CH.FRUIN);
  const f = d / CH.FRUIN;
  const v = CH.V0 * (1 - CH.WBLOCK * f);
  const w = CH.K_WIND * (CH.V0 - v);
  const q = d * CH.P_W * CH.SENS;
  const tau = cellM / Math.max(v, CH.VMIN);
  const m = (q * tau) / (CH.RHO_CP * CH.MIX_H);
  const h = CH.K_HUMID * f * (1 - 0.5 * (v / CH.V0));
  return Math.min(m + w + h, CH.CAP);
}


type AnimData = {
  lattice: { cols: number; rows: number; cell_size_m: number };
  hours: string[];
  heat_hours: { hour: string; cells: [number, number, number][] | null }[];
  frames: [number, number][][];
  n_agents: number;
  utci_min: number;
  utci_max: number;
  site?: string;
  date?: string;
};

// One trail point with its own timestamp (frame index) for the TripsLayer.
type Trail = { path: [number, number][]; timestamps: number[] };

// Module-level promise so the 11 MB script is injected exactly once even across remounts.
let dataPromise: Promise<void> | null = null;
function loadAnimData(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if ((window as unknown as { ANIM_DATA?: unknown }).ANIM_DATA) return Promise.resolve();
  if (dataPromise) return dataPromise;
  dataPromise = new Promise<void>((resolve) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-daytime-anim]');
    if (existing) {
      existing.addEventListener("load", () => resolve());
      if ((window as unknown as { ANIM_DATA?: unknown }).ANIM_DATA) resolve();
      return;
    }
    const s = document.createElement("script");
    s.src = "/daytime_anim_data.js";
    s.async = true;
    s.dataset.daytimeAnim = "1";
    s.addEventListener("load", () => resolve());
    s.addEventListener("error", () => resolve()); // resolve either way; we null-check ANIM_DATA
    document.head.appendChild(s);
  });
  return dataPromise;
}

// ── Marching-squares iso-contour painter ────────────────────────────────────────────
// Renders dashed glowing rings tracing each UTCI band onto a hi-res offscreen canvas
// (sub-cell supersampled so the lines are crisp, not chunky). The 32 °C danger band is
// drawn brighter + heavier than the others. The painted canvas becomes a BitmapLayer
// laid over the inferno field, so it stays geo-locked to the same quad bounds.
//
// We trace contours in the BitmapLayer's pixel space (origin top-left = north, x→east),
// then the layer maps that quad onto the geo corners exactly like the heat field.
const CONTOUR_SS = 6; // px per grid cell — supersample for crisp dashed strokes

/** Marching-squares segments for one iso level over a (cols×rows) scalar field. */
function isoSegments(
  field: Float32Array,
  cols: number,
  rows: number,
  level: number,
): [number, number, number, number][] {
  const segs: [number, number, number, number][] = [];
  const at = (c: number, r: number) => field[r * cols + c];
  // interpolate the crossing point on an edge between two corner values
  const ix = (va: number, vb: number) => (level - va) / (vb - va);
  for (let r = 0; r < rows - 1; r++) {
    for (let c = 0; c < cols - 1; c++) {
      // four corners (skip cells touching NaN — outside-site)
      const tl = at(c, r), tr = at(c + 1, r), bl = at(c, r + 1), br = at(c + 1, r + 1);
      if (Number.isNaN(tl) || Number.isNaN(tr) || Number.isNaN(bl) || Number.isNaN(br)) continue;
      let idx = 0;
      if (tl >= level) idx |= 8;
      if (tr >= level) idx |= 4;
      if (br >= level) idx |= 2;
      if (bl >= level) idx |= 1;
      if (idx === 0 || idx === 15) continue;
      // edge crossing points (in cell-fraction coords) — T(top) R(right) B(bottom) L(left)
      const T: [number, number] = [c + ix(tl, tr), r];
      const R: [number, number] = [c + 1, r + ix(tr, br)];
      const B: [number, number] = [c + ix(bl, br), r + 1];
      const L: [number, number] = [c, r + ix(tl, bl)];
      const push = (a: [number, number], b: [number, number]) => segs.push([a[0], a[1], b[0], b[1]]);
      switch (idx) {
        case 1: case 14: push(L, B); break;
        case 2: case 13: push(B, R); break;
        case 3: case 12: push(L, R); break;
        case 4: case 11: push(T, R); break;
        case 5: push(L, T); push(B, R); break;
        case 6: case 9: push(T, B); break;
        case 7: case 8: push(L, T); break;
        case 10: push(T, R); push(L, B); break;
      }
    }
  }
  return segs;
}

/**
 * Props are OPTIONAL and festival-default — calling `<DaytimeField />` with no props
 * is byte-identical to the original festival behaviour. "Beyond Festivals" scenarios
 * pass their own `bounds` (geo corners), `animData` (a small synthetic dataset), and
 * `clockLabel`. Nothing about the festival path changes.
 */
export function DaytimeField({
  bounds,
  animData,
  clockLabel = "festival time",
}: {
  bounds?: Corners;
  animData?: AnimData;
  clockLabel?: string;
} = {}) {
  const reduceMotion = useReducedMotion();

  // Geo corners + bilinear projection. Default = festival; scenarios override via prop.
  const corners = bounds ?? FEST_CORNERS;
  // deck BitmapLayer quad bounds order: [bottom-left, top-left, top-right, bottom-right].
  const BOUNDS: [[number, number], [number, number], [number, number], [number, number]] = [
    corners.SW,
    corners.NW,
    corners.NE,
    corners.SE,
  ];
  // Bilinear projection of a grid cell (col,row) → [lon,lat] over the 4 true corners.
  // u = col fraction (0=W→1=E); v = row fraction (0=S→1=N, since grid row 0 = south).
  const project = (col: number, row: number, cols: number, rows: number): [number, number] => {
    const u = col / cols;
    const v = row / rows;
    const lon =
      (1 - u) * (1 - v) * corners.SW[0] + u * (1 - v) * corners.SE[0] + u * v * corners.NE[0] + (1 - u) * v * corners.NW[0];
    const lat =
      (1 - u) * (1 - v) * corners.SW[1] + u * (1 - v) * corners.SE[1] + u * v * corners.NE[1] + (1 - u) * v * corners.NW[1];
    return [lon, lat];
  };

  // Load the data (once) then trigger a re-render so the rest of the hook can read it.
  // Scenario mode hands us `animData` directly; festival mode injects the ~11 MB script.
  const [data, setData] = useState<AnimData | null>(
    () =>
      animData ??
      ((typeof window !== "undefined" && (window as unknown as { ANIM_DATA?: AnimData }).ANIM_DATA) || null),
  );
  useEffect(() => {
    if (data) return;
    if (animData) {
      setData(animData);
      return;
    }
    let alive = true;
    loadAnimData().then(() => {
      if (!alive) return;
      const d = (window as unknown as { ANIM_DATA?: AnimData }).ANIM_DATA;
      if (d) setData(d);
    });
    return () => {
      alive = false;
    };
  }, [data, animData]);

  // Respect prefers-reduced-motion (WCAG 2.3.3): start paused for motion-sensitive users.
  const [playing, setPlaying] = useState(
    () =>
      typeof window === "undefined" ||
      !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );
  const [showPeople, setShowPeople] = useState(true);
  const [showTrails, setShowTrails] = useState(true);
  const [showContours, setShowContours] = useState(true);
  // `progress` (0..100) is the scrubber value; mirrors the day-clock head for UI redraw.
  const [progress, setProgress] = useState(0);
  const [clock, setClock] = useState<string>("--:--");
  // Live coupling readouts (the body-heat model reacting in real time): the current
  // peak felt-heat across the site, and how much of it the crowd itself is adding.
  const [peakHeat, setPeakHeat] = useState<number | null>(null);
  const [crowdAdd, setCrowdAdd] = useState<number>(0);
  // Worst-minute danger cell — where dangerous heat (≥32 °C) meets the densest crowd.
  // `danger` is the screen-anchored DOM bloom target; null when nothing is dangerous.
  const [danger, setDanger] = useState<{
    lon: number; lat: number; felt: number; pctInDanger: number;
  } | null>(null);

  // Dedicated overlay — its own deck instance so the per-frame tick is cheap.
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay({ interleaved: false, layers: [] }));
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;

  // ── derived constants + precomputed per-hour heat grids (built once per dataset) ──
  const prep = useMemo(() => {
    if (!data) return null;
    const { cols, rows, cell_size_m: cellM } = data.lattice;
    const nF = data.frames.length;
    const dayHours = data.hours.length - 1;

    // Per-hour heat arrays (Float32 cols*rows, NaN outside-site). Missing hours
    // (cells:null) get LINEAR-interpolated from bracketing real anchors — exactly
    // like the HTML (lines ~210-220).
    const HH: Float32Array[] = data.heat_hours.map((h) => {
      const a = new Float32Array(cols * rows).fill(NaN);
      if (h.cells) for (const [c, r, t] of h.cells) {
        if (c >= 0 && c < cols && r >= 0 && r < rows) a[r * cols + c] = t;
      }
      return a;
    });
    for (let i = 0; i < HH.length; i++) {
      if (data.heat_hours[i].cells) continue;
      let lo = i, hi = i;
      while (lo >= 0 && !data.heat_hours[lo].cells) lo--;
      while (hi < HH.length && !data.heat_hours[hi].cells) hi++;
      const A = lo >= 0 ? HH[lo] : null;
      const B = hi < HH.length ? HH[hi] : null;
      const out = new Float32Array(cols * rows).fill(NaN);
      if (A && B) {
        const f = (i - lo) / (hi - lo);
        for (let k = 0; k < out.length; k++) {
          const a = A[k], b = B[k];
          out[k] = !isNaN(a) && !isNaN(b) ? a + (b - a) * f : !isNaN(a) ? a : b;
        }
      } else if (A) out.set(A);
      else if (B) out.set(B);
      HH[i] = out;
    }

    const umin = data.utci_min;
    const umax = data.utci_max;
    const lo = umin;
    const hi = umax + CH.CAP; // crowd feedback can push a cell up to +CAP above the raw max
    const span = Math.max(0.001, hi - lo);

    // Reusable offscreen canvas (cols×rows) for the BitmapLayer image — repainted each frame.
    const canvas = document.createElement("canvas");
    canvas.width = cols;
    canvas.height = rows;
    const cctx = canvas.getContext("2d")!;
    const img = cctx.createImageData(cols, rows);

    // A scratch field (felt UTCI per cell, NaN outside-site) reused each frame to feed
    // the marching-squares contour tracer — avoids a per-frame allocation.
    const felt = new Float32Array(cols * rows);

    return { cols, rows, cellM, nF, dayHours, HH, lo, span, canvas, cctx, img, felt };
  }, [data]);

  // ── interpolate agent grid positions between frame i and i+1 (port of interpAgents) ──
  const interpAgents = (head: number): [number, number][] => {
    const frames = data!.frames;
    const nF = frames.length;
    const i = Math.floor(head);
    const f = head - i;
    const A = frames[i];
    const B = frames[Math.min(nF - 1, i + 1)];
    const out: [number, number][] = [];
    for (let k = 0; k < A.length; k++) {
      const ax = A[k][0], ay = A[k][1], bx = B[k][0], by = B[k][1];
      if (Math.abs(bx - ax) + Math.abs(by - ay) > JUMP) out.push([bx, by]);
      else out.push([lerp(ax, bx, f), lerp(ay, by, f)]);
    }
    return out;
  };

  // ── paint dashed glowing iso-contours onto a fresh hi-res canvas from the felt field ──
  // Returns a canvas mapped onto the SAME quad bounds as the heat field (origin top-left =
  // north). The 32 °C danger band is rendered brighter + heavier (the "is this real
  // science" signal, u-shade-spec A4). Reusing a single canvas would freeze the texture
  // (BitmapLayer caches by reference) — so a fresh canvas each call, like the heat field.
  const paintContours = (felt: Float32Array, cols: number, rows: number): HTMLCanvasElement | null => {
    const W = cols * CONTOUR_SS;
    const H = rows * CONTOUR_SS;
    const cv = document.createElement("canvas");
    cv.width = W;
    cv.height = H;
    const ctx = cv.getContext("2d");
    if (!ctx) return null;
    ctx.clearRect(0, 0, W, H);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    for (const level of CONTOUR_BANDS) {
      const segs = isoSegments(felt, cols, rows, level);
      if (!segs.length) continue;
      const isDanger = level === DANGER_C;
      // band hue from the same UTCI ramp the field uses, brightened toward white for legibility
      const base = ramp(INFERNO, clamp01((level - prep!.lo) / prep!.span));
      const glow = isDanger ? [255, 120, 90] : [Math.min(255, base[0] + 90), Math.min(255, base[1] + 90), Math.min(255, base[2] + 90)];
      // grid row 0 = SOUTH; BitmapLayer image row 0 = TOP = north → flip y so the painted
      // contour lines up with the (already-flipped) heat field and the basemap streets.
      const path = new Path2D();
      for (const [x0, y0, x1, y1] of segs) {
        path.moveTo(x0 * CONTOUR_SS, (rows - y0) * CONTOUR_SS);
        path.lineTo(x1 * CONTOUR_SS, (rows - y1) * CONTOUR_SS);
      }
      // soft outer glow pass
      ctx.setLineDash([]);
      ctx.shadowColor = `rgba(${glow[0]},${glow[1]},${glow[2]},${isDanger ? 0.95 : 0.6})`;
      ctx.shadowBlur = isDanger ? 14 : 8;
      ctx.strokeStyle = `rgba(${glow[0]},${glow[1]},${glow[2]},${isDanger ? 0.45 : 0.22})`;
      ctx.lineWidth = isDanger ? 7 : 4.5;
      ctx.stroke(path);
      // crisp dashed top stroke
      ctx.shadowBlur = 0;
      ctx.setLineDash(isDanger ? [13, 7] : [8, 9]);
      ctx.strokeStyle = isDanger
        ? "rgba(255,236,228,0.98)"
        : `rgba(${glow[0]},${glow[1]},${glow[2]},0.85)`;
      ctx.lineWidth = isDanger ? 3 : 1.7;
      ctx.stroke(path);
    }
    ctx.setLineDash([]);
    return cv;
  };

  // ── render one frame at day-clock `head` ∈ [0, nF-1]: repaint heat image + dot/trail data ──
  const headRef = useRef(0);
  const tickRef = useRef(0);
  const renderFrame = (head: number) => {
    const p = prep;
    if (!p || !data) return;
    const { cols, rows, cellM, nF, dayHours, HH, lo, span, canvas, cctx, img, felt } = p;

    const hf = (head / (nF - 1)) * dayHours; // 0..(hours-1) hour float
    const ha = Math.floor(hf);
    const hb = Math.min(dayHours, ha + 1);
    const hfr = hf - ha;
    const heatA = HH[ha];
    const heatB = HH[hb];

    const agents = interpAgents(head);

    // bin agent density per cell (for the crowd→heat coupling)
    const dens = new Float32Array(cols * rows);
    for (const [c, r] of agents) {
      const ci = c | 0, ri = r | 0;
      if (ci >= 0 && ci < cols && ri >= 0 && ri < rows) dens[ri * cols + ci]++;
    }

    // ── paint the heat ImageData (interpolated real UTCI + crowd ΔUTCI bloom) ──
    const B = img.data;
    let maxFelt = -Infinity; // peak felt-heat this minute (base + crowd)
    let maxDu = 0; // peak crowd-added ΔUTCI this minute (the body-heat coupling)
    // worst-cell tracker: where dangerous heat (≥DANGER_C) meets the densest crowd, scored
    // felt×crowd so the crosshair lands on the cell that hurts most, not just the hottest.
    let worstScore = -Infinity;
    let worstCol = -1, worstRow = -1, worstFelt = 0;
    let inSiteCells = 0, dangerPeopleCells = 0; // for the "% crowd in dangerous heat" readout
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;
        // grid row 0 = SOUTH, but ImageData row 0 = TOP = north → flip vertically so
        // the painted field matches the geo bounds (and the basemap streets).
        const px = ((rows - 1 - r) * cols + c) * 4;
        let t = NaN;
        const ta = heatA[idx], tb = heatB[idx];
        if (!isNaN(ta) && !isNaN(tb)) t = lerp(ta, tb, hfr);
        else if (!isNaN(ta)) t = ta;
        else if (!isNaN(tb)) t = tb;

        if (isNaN(t)) {
          B[px + 3] = 0; // outside-site → transparent
          felt[idx] = NaN;
          continue;
        }
        let du = 0;
        const ag = dens[idx];
        if (ag > 0) du = dUTCI(pplM2(ag, cellM), cellM);
        const tu = t + du;
        felt[idx] = tu; // feed the contour tracer
        if (tu > maxFelt) maxFelt = tu;
        if (du > maxDu) maxDu = du;

        // crowd-in-danger accounting + worst-cell score
        if (ag > 0) {
          inSiteCells += ag;
          if (tu >= DANGER_C) {
            dangerPeopleCells += ag;
            const score = tu * (1 + ag); // hot AND dense
            if (score > worstScore) {
              worstScore = score;
              worstCol = c; worstRow = r; worstFelt = tu;
            }
          }
        }

        const col = ramp(INFERNO, (tu - lo) / span);
        let R = col[0] * 0.86, G = col[1] * 0.86, Bl = col[2] * 0.86;
        // crowd-heat reddens — the people physically warming the air (matches the HTML)
        if (du > 0.5) {
          const k = clamp01((du - 0.5) / 3);
          R = lerp(R, 255, k * 0.6);
          G = lerp(G, 55, k * 0.5);
          Bl = lerp(Bl, 40, k * 0.5);
        }
        B[px] = R;
        B[px + 1] = G;
        B[px + 2] = Bl;
        B[px + 3] = 255;
      }
    }
    // BitmapLayer caches its texture by image REFERENCE — reusing one canvas means
    // it never re-uploads and the heat freezes on frame 0. So hand deck a FRESH canvas
    // each frame (139×153 is tiny). This is what makes the field visibly change hourly.
    const frameCanvas = document.createElement("canvas");
    frameCanvas.width = cols;
    frameCanvas.height = rows;
    frameCanvas.getContext("2d")!.putImageData(img, 0, 0);

    // ── iso-contours (own fresh canvas, mapped onto the same quad bounds) ──
    const contourCanvas = showContours ? paintContours(felt, cols, rows) : null;

    // ── crowd dots: scatter representative jittered dots around each agent ──
    const tick = tickRef.current++;
    const peopleDots: { position: [number, number] }[] = [];
    const trails: Trail[] = [];
    if (showPeople || showTrails) {
      for (let k = 0; k < agents.length; k++) {
        const [c0, r0] = agents[k];
        if (c0 < 0 || c0 >= cols || r0 < 0 || r0 >= rows) continue;

        if (showPeople) {
          for (let j = 0; j < DOTS_PER_AGENT; j++) {
            // deterministic per-(agent,dot) phase so the milling looks alive but stable
            const ph = k * 1.7 + j * 2.399;
            const jx = 0.55 * Math.sin(tick * 0.045 + ph) + 0.4 * Math.cos(ph * 1.7);
            const jy = 0.55 * Math.cos(tick * 0.038 + ph * 1.3) + 0.4 * Math.sin(ph * 2.1);
            peopleDots.push({ position: project(c0 + jx, r0 + jy, cols, rows) });
          }
        }
        if (showTrails) {
          // a short two-point comet segment (prev interpolated → current) per agent;
          // TripsLayer fades it into a glowing cyan trail.
          const back = Math.max(0, head - 0.6);
          const prev = (() => {
            const i = Math.floor(back), f = back - i;
            const A = data.frames[i], Bf = data.frames[Math.min(nF - 1, i + 1)];
            const ax = A[k][0], ay = A[k][1], bx = Bf[k][0], by = Bf[k][1];
            if (Math.abs(bx - ax) + Math.abs(by - ay) > JUMP) return [bx, by] as [number, number];
            return [lerp(ax, bx, f), lerp(ay, by, f)] as [number, number];
          })();
          if (Math.abs(prev[0] - c0) + Math.abs(prev[1] - r0) <= JUMP) {
            trails.push({
              path: [
                project(prev[0], prev[1], cols, rows),
                project(c0, r0, cols, rows),
              ],
              timestamps: [head - 0.6, head],
            });
          }
        }
      }
    }

    // ── worst-cell danger crosshair (deck PathLayer square + ring) ──
    const dangerGeo = worstCol >= 0 ? project(worstCol + 0.5, worstRow + 0.5, cols, rows) : null;
    const crosshairLayers: PathLayer<unknown>[] = [];
    if (dangerGeo) {
      // an orange open square (corner ticks) + a small ring around the worst cell, in
      // geo-projected corners so it stays pinned to the cell as the map moves.
      const half = 5; // cells out from the worst cell — a ~30 m box
      const cL = worstCol + 0.5 - half, cR = worstCol + 0.5 + half;
      const rT = worstRow + 0.5 - half, rB = worstRow + 0.5 + half;
      const corner = (cc: number, rr: number) => project(cc, rr, cols, rows);
      const tick2 = 2.4; // length of each corner tick, in cells
      const cornerTicks: [number, number][][] = [
        // four L-shaped corner brackets
        [corner(cL, rT + tick2), corner(cL, rT), corner(cL + tick2, rT)],
        [corner(cR - tick2, rT), corner(cR, rT), corner(cR, rT + tick2)],
        [corner(cR, rB - tick2), corner(cR, rB), corner(cR - tick2, rB)],
        [corner(cL + tick2, rB), corner(cL, rB), corner(cL, rB - tick2)],
      ];
      crosshairLayers.push(
        new PathLayer({
          id: "daytime-crosshair",
          data: cornerTicks,
          getPath: (d: [number, number][]) => d,
          getColor: [232, 130, 40, 235],
          widthUnits: "pixels",
          getWidth: 2,
          widthMinPixels: 1.6,
          jointRounded: false,
          capRounded: false,
          parameters: { depthCompare: "always" },
          updateTriggers: { getPath: `${worstCol},${worstRow}` },
        }) as unknown as PathLayer<unknown>,
      );
    }

    // ── readouts — MINUTE-level clock (the hourly infrared anchors interpolate
    // continuously, so the day reads by the minute) + the live body-heat coupling. ──
    const ha2 = Math.min(dayHours, Math.floor(hf));
    const baseH = parseInt((data.hours[ha2] ?? "09:00").slice(0, 2), 10);
    const mm = Math.min(59, Math.floor((hf - Math.floor(hf)) * 60));
    const clk = `${String(baseH).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
    setClock((prevClk) => (prevClk === clk ? prevClk : clk));
    const pct = (head / (nF - 1)) * 100;
    setProgress((prevPct) => (Math.abs(prevPct - pct) < 0.05 ? prevPct : pct));
    // Throttle to 0.1° granularity so React doesn't churn every frame.
    const felt0 = maxFelt > -Infinity ? Math.round(maxFelt * 10) / 10 : null;
    setPeakHeat((p) => (p === felt0 ? p : felt0));
    const add = Math.round(maxDu * 10) / 10;
    setCrowdAdd((p) => (p === add ? p : add));

    // danger DOM bloom target (only when a dangerous cell exists) — throttled so the
    // crosshair box doesn't re-mount/re-bloom every frame (it would never settle).
    if (dangerGeo) {
      const pctInDanger = inSiteCells > 0 ? Math.round((dangerPeopleCells / inSiteCells) * 1000) / 10 : 0;
      setDanger((prev) => {
        if (
          prev &&
          Math.abs(prev.lon - dangerGeo[0]) < 1e-5 &&
          Math.abs(prev.lat - dangerGeo[1]) < 1e-5 &&
          Math.abs(prev.felt - worstFelt) < 0.15 &&
          Math.abs(prev.pctInDanger - pctInDanger) < 0.2
        ) return prev;
        return { lon: dangerGeo[0], lat: dangerGeo[1], felt: worstFelt, pctInDanger };
      });
    } else {
      setDanger((prev) => (prev === null ? prev : null));
    }

    overlayRef.current.setProps({
      layers: [
        new BitmapLayer({
          id: "daytime-heat",
          image: frameCanvas,
          bounds: BOUNDS,
          opacity: 0.8,
          // soft thermal upsample: keep texture smoothing on (deck's default linear filter)
          textureParameters: {
            minFilter: "linear",
            magFilter: "linear",
          },
          // force re-upload of the mutated canvas every tick
          updateTriggers: { image: tick },
          parameters: { depthCompare: "always" },
        }),
        // dashed glowing iso-contours over the field (the "topo map of heat")
        contourCanvas &&
          new BitmapLayer({
            id: "daytime-contours",
            image: contourCanvas,
            bounds: BOUNDS,
            opacity: 0.92,
            textureParameters: { minFilter: "linear", magFilter: "linear" },
            updateTriggers: { image: tick },
            parameters: { depthCompare: "always" },
          }),
        // comet flow trails — bright cyan additive, same look as TrajectoryPlayback
        showTrails &&
          new TripsLayer<Trail>({
            id: "daytime-trails",
            data: trails,
            getPath: (d) => d.path,
            getTimestamps: (d) => d.timestamps,
            getColor: [120, 235, 245],
            opacity: 0.55,
            widthUnits: "pixels",
            getWidth: 2,
            widthMinPixels: 1.2,
            trailLength: 0.6,
            currentTime: head,
            fadeTrail: true,
            jointRounded: true,
            capRounded: true,
            parameters: ADDITIVE,
            updateTriggers: { getPath: tick },
          }),
        // people — a real-scale impression of the crowd: many soft warm-white dots
        showPeople &&
          new ScatterplotLayer<{ position: [number, number] }>({
            id: "daytime-people",
            data: peopleDots,
            getPosition: (d) => d.position,
            getRadius: 1.4,
            radiusUnits: "pixels",
            radiusMinPixels: 1,
            radiusMaxPixels: 2.5,
            getFillColor: [210, 245, 240, 90],
            stroked: false,
            parameters: ADDITIVE,
            updateTriggers: { getPosition: tick },
          }),
        ...crosshairLayers,
      ].filter(Boolean),
    });
  };

  // ── animation loop: drive the shared day-clock head; STOP the rAF when paused ──
  useEffect(() => {
    if (!prep || !data) return;
    const nF = prep.nF;
    const speed = 0.35; // per-frame head advance @ 60fps — a calm, readable festival pace

    // Paused: render ONE static frame and stop (no rAF — keeps the page idle so it
    // doesn't block screenshots or burn the GPU). Matches TrajectoryPlayback.
    if (!playing) {
      renderFrame(headRef.current);
      return;
    }
    let raf = 0;
    const loop = () => {
      let head = headRef.current + speed;
      if (head >= nF - 1) head = 0;
      headRef.current = head;
      renderFrame(head);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prep, data, playing, showPeople, showTrails, showContours]);

  // Clear the overlay's layers on unmount (leaving the daytime view).
  useEffect(() => () => overlayRef.current.setProps({ layers: [] }), []);

  // ── scrubber → head (pauses while scrubbing, like the HTML) ──
  const onScrub = (v: number) => {
    if (!prep) return;
    setPlaying(false);
    const head = (v / 100) * (prep.nF - 1);
    headRef.current = head;
    setProgress(v);
    renderFrame(head);
  };

  // Project the danger lat/lon to a screen %% for the DOM bloom box. We read the live
  // mapbox instance off the overlay's deck so the box tracks the cell on pan/zoom; if
  // it's offscreen we just hide it. Recomputed on each render of the chrome below.
  const dangerScreen = useDangerScreen(danger, overlayRef);

  if (!data) {
    // Data still loading — a tiny dark-glass "preparing the day…" chip, no overlay.
    return (
      <div
        className="pointer-events-none absolute bottom-6 left-1/2 z-20 -translate-x-1/2 px-3 py-2"
        style={{
          background: "color-mix(in srgb, var(--black) 70%, transparent)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          backdropFilter: "blur(8px)",
          color: "var(--grey)",
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          letterSpacing: "0.04em",
        }}
      >
        preparing the day…
      </div>
    );
  }

  const hours = data.hours;
  const chipStyle = (on: boolean): React.CSSProperties => ({
    appearance: "none",
    cursor: "pointer",
    padding: "5px 9px",
    borderRadius: "var(--radius-sm)",
    border: `1px solid ${on ? "var(--teal)" : "var(--border)"}`,
    background: on ? "color-mix(in srgb, var(--teal) 18%, transparent)" : "transparent",
    color: on ? "var(--paper)" : "var(--grey)",
    fontFamily: "var(--font-mono)",
    fontSize: 10.5,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
    transition: "color .15s, background .15s, border-color .15s",
  });

  // Hour-tick spacing: only LABEL every other major tick when ticks are dense, so the
  // 09:00 / 12:00 / 15:00 … labels never overlap (fixes s6-scrubber.png crowding).
  const nLabels = Math.floor(hours.length / 3) + 1;
  const labelEvery = nLabels > 8 ? 6 : 3;

  return (
    <>
      {/* ── TOP STATUS BAR — LIVE · clock · PEAK (thermal-camera HUD, per s6-heatmap.png) ── */}
      <div
        className="pointer-events-none absolute left-1/2 top-5 z-20 -translate-x-1/2"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 0,
          padding: "0",
          background: "color-mix(in srgb, var(--black) 72%, transparent)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          backdropFilter: "blur(12px) saturate(1.2)",
          WebkitBackdropFilter: "blur(12px) saturate(1.2)",
          boxShadow: "0 8px 28px -10px rgba(0,0,0,0.8)",
          overflow: "hidden",
          fontFamily: "var(--font-mono)",
        }}
      >
        {/* LIVE pip */}
        <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 14px" }}>
          <motion.span
            aria-hidden
            style={{ width: 7, height: 7, borderRadius: 999, background: "var(--heat)", display: "block" }}
            animate={reduceMotion ? undefined : { opacity: [1, 0.25, 1] }}
            transition={reduceMotion ? undefined : { duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
          />
          <span style={{ fontSize: 10, letterSpacing: "0.18em", color: "var(--paper)" }}>LIVE</span>
        </div>
        <div style={{ width: 1, alignSelf: "stretch", background: "var(--border)" }} />
        {/* clock */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, padding: "8px 14px" }}>
          <span style={{ fontSize: 13, letterSpacing: "0.06em", color: "var(--paper)", fontVariantNumeric: "tabular-nums" }}>
            {clock}
          </span>
          <span style={{ fontSize: 8.5, letterSpacing: "0.14em", color: "var(--grey)", textTransform: "uppercase" }}>
            {clockLabel}
          </span>
        </div>
        <div style={{ width: 1, alignSelf: "stretch", background: "var(--border)" }} />
        {/* peak felt heat */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, padding: "8px 14px" }}>
          <span style={{ fontSize: 8.5, letterSpacing: "0.14em", color: "var(--grey)", textTransform: "uppercase" }}>
            peak felt
          </span>
          <span style={{ fontSize: 13, color: "var(--heat)", fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
            {peakHeat != null ? `${peakHeat.toFixed(1)}°` : "—"}
          </span>
        </div>
      </div>

      {/* ── WORST-MINUTE DANGER CROSSHAIR — DOM bloom box over the deck crosshair ── */}
      <AnimatePresence>
        {dangerScreen && danger && (
          <motion.div
            key="danger-bloom"
            className="pointer-events-none absolute z-20"
            style={{
              left: `${dangerScreen.x}%`,
              top: `${dangerScreen.y}%`,
              transform: "translate(-50%,-50%)",
            }}
            initial={reduceMotion ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.85 }}
            transition={{ duration: DUR.bloom / 1000, ease: EASE.out }}
          >
            {/* the box outline (subtle; the sharp corner ticks live in the deck layer) */}
            <div
              style={{
                width: 92,
                height: 92,
                border: "1px solid color-mix(in srgb, var(--amber) 70%, transparent)",
                borderRadius: "var(--radius-sm)",
                boxShadow: "0 0 22px -4px color-mix(in srgb, var(--amber) 60%, transparent)",
              }}
            />
            {/* pulsing halo ring (settles to a slow steady pulse — never an infinite churn) */}
            {!reduceMotion && (
              <motion.div
                aria-hidden
                className="absolute left-1/2 top-1/2"
                style={{
                  width: 92,
                  height: 92,
                  marginLeft: -46,
                  marginTop: -46,
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid color-mix(in srgb, var(--amber) 55%, transparent)",
                }}
                animate={reduceMotion ? undefined : { scale: [1, 1.28, 1], opacity: [0.55, 0, 0.4] }}
                transition={reduceMotion ? undefined : { duration: 2.6, repeat: 3, ease: "easeOut" }}
              />
            )}
            {/* readout — "% crowd in dangerous heat" (per s6-danger-cross.png) */}
            <div
              className="absolute"
              style={{
                left: "calc(50% + 58px)",
                top: "50%",
                transform: "translateY(-50%)",
                whiteSpace: "nowrap",
                background: "color-mix(in srgb, var(--black) 78%, transparent)",
                border: "1px solid color-mix(in srgb, var(--amber) 55%, transparent)",
                borderRadius: "var(--radius-sm)",
                padding: "7px 10px",
                backdropFilter: "blur(8px)",
                WebkitBackdropFilter: "blur(8px)",
                boxShadow: "0 8px 24px -10px rgba(0,0,0,0.8)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <WarningTriangle style={{ width: 12, height: 12, color: "var(--amber)" }} />
                <span
                  style={{
                    fontFamily: "var(--font-display)",
                    fontWeight: 600,
                    fontSize: 18,
                    lineHeight: 1,
                    color: "var(--paper)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {danger.pctInDanger.toFixed(1)}%
                </span>
              </div>
              <div
                style={{
                  marginTop: 4,
                  fontFamily: "var(--font-mono)",
                  fontSize: 8.5,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: "var(--amber)",
                }}
              >
                crowd in dangerous heat
              </div>
              <div
                style={{
                  marginTop: 2,
                  fontFamily: "var(--font-mono)",
                  fontSize: 8.5,
                  letterSpacing: "0.08em",
                  color: "var(--grey)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                felt {danger.felt.toFixed(1)}° · worst cell
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── UTCI LEGEND (bottom-right) — gradient ramp + the 32°C danger line marked ── */}
      <div
        className="pointer-events-none absolute bottom-24 right-6 z-20"
        style={{
          width: 168,
          padding: "9px 11px",
          background: "color-mix(in srgb, var(--black) 70%, transparent)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          backdropFilter: "blur(10px)",
          WebkitBackdropFilter: "blur(10px)",
          boxShadow: "0 8px 24px -12px rgba(0,0,0,0.8)",
          fontFamily: "var(--font-mono)",
        }}
      >
        <div style={{ fontSize: 8.5, letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--grey)" }}>
          UTCI · felt heat
        </div>
        <div
          style={{
            marginTop: 6,
            height: 8,
            borderRadius: 999,
            // INFERNO ramp, the same field colormap
            background:
              "linear-gradient(90deg, rgb(12,8,38), rgb(101,21,110), rgb(212,72,66), rgb(245,125,21), rgb(250,193,39), rgb(252,255,164))",
          }}
        />
        <div style={{ position: "relative", marginTop: 3, height: 12 }}>
          {/* the 32°C danger tick on the ramp */}
          <div
            style={{
              position: "absolute",
              left: `${clamp01((DANGER_C - (data.utci_min)) / Math.max(1, data.utci_max + CH.CAP - data.utci_min)) * 100}%`,
              top: -9,
              width: 1,
              height: 9,
              background: "var(--paper)",
              transform: "translateX(-50%)",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: `${clamp01((DANGER_C - (data.utci_min)) / Math.max(1, data.utci_max + CH.CAP - data.utci_min)) * 100}%`,
              top: 0,
              transform: "translateX(-50%)",
              fontSize: 7.5,
              letterSpacing: "0.08em",
              color: "var(--paper)",
              whiteSpace: "nowrap",
            }}
          >
            32° danger
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 12, fontSize: 7.5, color: "var(--grey)" }}>
          <span>cool</span>
          <span>severe</span>
        </div>
      </div>

      {/* ── BOTTOM DAY-CLOCK SCRUBBER (dark glass, matches the dark placement map) ── */}
      <div
        className="pointer-events-auto absolute bottom-6 left-1/2 z-20 -translate-x-1/2"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "10px 16px",
          minWidth: 560,
          maxWidth: "min(820px, calc(100vw - 48px))",
          background: "color-mix(in srgb, var(--black) 70%, transparent)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          backdropFilter: "blur(14px) saturate(1.2)",
          WebkitBackdropFilter: "blur(14px) saturate(1.2)",
          boxShadow: "0 12px 40px -12px rgba(0,0,0,0.85)",
        }}
      >
        {/* Play / pause */}
        <button
          type="button"
          onClick={() => setPlaying((v) => !v)}
          aria-label={playing ? "Pause the festival day" : "Play the festival day"}
          title={playing ? "Pause" : "Play"}
          style={{
            flex: "none",
            width: 38,
            height: 38,
            display: "grid",
            placeItems: "center",
            borderRadius: "999px",
            border: "1px solid var(--teal)",
            background: "color-mix(in srgb, var(--teal) 22%, transparent)",
            color: "var(--paper)",
            cursor: "pointer",
          }}
        >
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </button>

        {/* Big clock readout */}
        <div style={{ flex: "none", minWidth: 92 }}>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 30,
              lineHeight: 1,
              fontWeight: 600,
              letterSpacing: "-0.02em",
              color: "var(--paper)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {clock}
          </div>
          <div
            style={{
              marginTop: 4,
              fontFamily: "var(--font-mono)",
              fontSize: 9,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--grey)",
            }}
          >
            {clockLabel}{data.date ? ` · ${data.date}` : ""}
          </div>
        </div>

        {/* Live coupling readout — peak felt-heat + how much the crowd's own body heat
            is adding to the air right now (the crowd_heat.py model, reacting per minute). */}
        <div style={{ flex: "none", display: "flex", flexDirection: "column", gap: 4, minWidth: 104 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
            <span
              style={{
                fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 17, lineHeight: 1,
                color: "var(--heat)", fontVariantNumeric: "tabular-nums",
              }}
            >
              {peakHeat != null ? `${peakHeat.toFixed(1)}°` : "—"}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--grey)" }}>
              felt · peak
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
            <span
              style={{
                fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 12, lineHeight: 1,
                color: crowdAdd > 0.3 ? "var(--heat)" : "var(--grey)", fontVariantNumeric: "tabular-nums",
              }}
            >
              +{crowdAdd.toFixed(1)}°
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--grey)" }}>
              crowd adds
            </span>
          </div>
        </div>

        {/* Scrubber with hour ticks */}
        <div style={{ position: "relative", flex: 1, height: 38, display: "flex", alignItems: "center" }}>
          <input
            type="range"
            min={0}
            max={100}
            step={0.1}
            value={progress}
            onChange={(e) => onScrub(+e.target.value)}
            aria-label="Scrub through the festival day"
            style={{
              width: "100%",
              accentColor: "var(--teal)",
              cursor: "pointer",
            }}
          />
          {/* hour tick marks */}
          <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
            {hours.map((hh, i) => {
              const pct = (i / (hours.length - 1)) * 100;
              const major = i % 3 === 0 || i === hours.length - 1;
              // only label a SUBSET of majors so labels never overlap (fix: tick crowding)
              const labelThis = (i % labelEvery === 0 || i === hours.length - 1) && pct >= 1.5 && pct <= 98.5;
              return (
                <div key={hh + i}>
                  <div
                    style={{
                      position: "absolute",
                      top: "50%",
                      left: `${pct}%`,
                      width: 1,
                      height: major ? 11 : 6,
                      transform: "translate(-50%,-50%)",
                      background: major ? "var(--grey)" : "var(--border)",
                    }}
                  />
                  {labelThis && (
                    <div
                      style={{
                        position: "absolute",
                        top: "calc(50% + 12px)",
                        left: `${pct}%`,
                        transform: "translateX(-50%)",
                        fontFamily: "var(--font-mono)",
                        fontSize: 8.5,
                        letterSpacing: "0.02em",
                        color: "var(--grey)",
                        whiteSpace: "nowrap",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {hh.slice(0, 5)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Layer toggle chips */}
        <div style={{ display: "flex", gap: 6, flex: "none" }}>
          <button type="button" aria-pressed={showContours} onClick={() => setShowContours((v) => !v)} style={chipStyle(showContours)}>
            Contours
          </button>
          <button type="button" aria-pressed={showPeople} onClick={() => setShowPeople((v) => !v)} style={chipStyle(showPeople)}>
            People
          </button>
          <button type="button" aria-pressed={showTrails} onClick={() => setShowTrails((v) => !v)} style={chipStyle(showTrails)}>
            Trails
          </button>
        </div>
      </div>
    </>
  );
}

// ── Project a lon/lat to a viewport %% using the live deck/mapbox viewport, so the DOM
// danger bloom box tracks the worst cell on pan/zoom. Returns null when offscreen. We
// poll on rAF only while a danger target exists AND the map is interacting, and always
// settle (the box position is also recomputed on every chrome re-render below). ──
function useDangerScreen(
  danger: { lon: number; lat: number } | null,
  overlayRef: React.MutableRefObject<MapboxOverlay>,
) {
  const [screen, setScreen] = useState<{ x: number; y: number } | null>(null);

  useEffect(() => {
    if (!danger) {
      setScreen((s) => (s === null ? s : null));
      return;
    }
    let raf = 0;
    let alive = true;
    const compute = () => {
      // The MapboxOverlay exposes the deck instance; its viewport projects lng/lat → px.
      const deck = (overlayRef.current as unknown as { _deck?: { getViewports?: () => unknown[] } })._deck;
      const vps = deck?.getViewports?.();
      const vp = vps && vps[0] as unknown as
        | { project: (c: [number, number]) => [number, number]; width: number; height: number }
        | undefined;
      if (!vp || !vp.width || !vp.height) {
        setScreen((s) => (s === null ? s : null));
        return;
      }
      const [px, py] = vp.project([danger.lon, danger.lat]);
      if (px < -40 || py < -40 || px > vp.width + 40 || py > vp.height + 40) {
        setScreen((s) => (s === null ? s : null));
      } else {
        const x = Math.round((px / vp.width) * 1000) / 10;
        const y = Math.round((py / vp.height) * 1000) / 10;
        setScreen((s) => (s && Math.abs(s.x - x) < 0.05 && Math.abs(s.y - y) < 0.05 ? s : { x, y }));
      }
    };
    // recompute for a short settle window + on each animation frame the map may move;
    // capped so we never spin an infinite idle loop (would block screenshots).
    let frames = 0;
    const tick = () => {
      if (!alive) return;
      compute();
      frames++;
      // keep tracking for ~1s after the target changes, then settle (static frame holds).
      if (frames < 70) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      alive = false;
      cancelAnimationFrame(raf);
    };
  }, [danger, overlayRef]);

  return screen;
}
