/**
 * materials-recommend — U-Shade's final material shortlist.
 *
 * PRODUCT DECISION (owner, 2026-06-24): in the end we recommend BETWEEN 3 AND 5
 * materials, ranked on three honest axes:
 *   1. Cost            — lower `costPerUnit` is better (reclaimed/free wins).
 *   2. CO₂ reduction   — lower `transportCarbonKg` is better (transport-only carbon,
 *                        per the project's carbon rule; manufacturing is the avoided
 *                        embodied cost of reusing reclaimed stock).
 *   3. Ease of assembly — lighter `unitMassKg` + a hand-assemblable `installMethod`
 *                        is better (membranes drape/clip; heavy steel needs plant).
 *
 * Every score is derived from real datasheet fields — never fabricated. Missing fields
 * fall back to a neutral 0.5 (honest "unknown", neither rewarded nor punished) and the
 * `why` string only cites axes we actually have data for. This is a RECOMMENDATION the
 * organiser reviews — it does not commit the architect to anything.
 */

import type { MaterialItem } from "./materials-provider";

export interface MaterialScore {
  item: MaterialItem;
  /** 0–1 combined score (higher = stronger recommendation). */
  score: number;
  cost: number; // 0–1 per-axis (higher = cheaper)
  co2: number; // 0–1 per-axis (higher = lower carbon)
  assembly: number; // 0–1 per-axis (higher = easier)
  /** Short honest rationale, only citing axes backed by real data. */
  why: string;
}

export interface RecommendOptions {
  min?: number; // default 3
  max?: number; // default 5
  weights?: { cost: number; co2: number; assembly: number };
}

const NEUTRAL = 0.5;

/** Min-max normalise; returns a function value→[0,1]. `invert` flips so LOWER is better. */
function scaler(values: number[], invert: boolean) {
  const real = values.filter((v) => Number.isFinite(v));
  if (real.length === 0) return () => NEUTRAL;
  const lo = Math.min(...real);
  const hi = Math.max(...real);
  if (hi === lo) return () => NEUTRAL;
  return (v: number) => {
    if (!Number.isFinite(v)) return NEUTRAL;
    const t = (v - lo) / (hi - lo); // 0 at lo, 1 at hi
    return invert ? 1 - t : t;
  };
}

/** Heuristic assembly weight from install method when mass is absent. Lower = harder. */
function installEase(item: MaterialItem): number {
  const m = (item.installMethod ?? "").toLowerCase();
  if (/weld|crane|plant|bolt-?heavy|cast/.test(m)) return 0.2;
  if (/bolt|frame|scaffold|truss|fix/.test(m)) return 0.55;
  if (/drape|clip|cable|lash|tension|net|cover|zip|hang/.test(m)) return 0.85;
  // Membranes are generally hand-assemblable; structure generally heavier.
  return item.type === "membr" ? 0.7 : 0.45;
}

/**
 * Rank materials and return the top 3–5 (clamped to what's available). Items must be
 * genuinely viable shade/structure stock (the caller passes the catalogue already).
 */
export function recommendMaterials(
  items: MaterialItem[],
  opts: RecommendOptions = {},
): MaterialScore[] {
  const min = opts.min ?? 3;
  const max = opts.max ?? 5;
  const w = opts.weights ?? { cost: 1, co2: 1, assembly: 1 };
  const wSum = w.cost + w.co2 + w.assembly || 1;

  if (items.length === 0) return [];

  const costScale = scaler(items.map((i) => i.costPerUnit ?? NaN), true);
  const co2Scale = scaler(items.map((i) => i.transportCarbonKg ?? NaN), true);
  const massScale = scaler(items.map((i) => i.unitMassKg ?? NaN), true);

  // First pass: per-axis scores only (needed before we can claim a superlative).
  const rows = items.map((item) => {
    const cost = item.costPerUnit != null ? costScale(item.costPerUnit) : NEUTRAL;
    const co2 = item.transportCarbonKg != null ? co2Scale(item.transportCarbonKg) : NEUTRAL;
    // Ease of assembly: prefer real mass; blend in the install-method heuristic.
    const massScore = item.unitMassKg != null ? massScale(item.unitMassKg) : NEUTRAL;
    const assembly = item.unitMassKg != null ? 0.6 * massScore + 0.4 * installEase(item) : installEase(item);
    return { item, cost, co2, assembly };
  });

  // Set medians per axis — a `why` clause must beat the field, not just exist.
  const median = (xs: number[]) => {
    const s = [...xs].sort((a, b) => a - b);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };
  const costMed = median(rows.map((r) => r.cost));
  const co2Med = median(rows.map((r) => r.co2));
  const asmMed = median(rows.map((r) => r.assembly));

  // Honesty gate: only claim an axis when the item is genuinely strong on it —
  // a high absolute normalized score AND strictly better than the set median.
  // (Min-max alone gives even the worst item a value; this stops false superlatives.)
  const STRONG = 0.66;
  const strong = (v: number, med: number) => v >= STRONG && v > med;

  const scored: MaterialScore[] = rows.map(({ item, cost, co2, assembly }) => {
    const score = (w.cost * cost + w.co2 * co2 + w.assembly * assembly) / wSum;

    const reasons: string[] = [];
    if (item.costPerUnit === 0) reasons.push("free to reclaim");
    else if (item.costPerUnit != null && strong(cost, costMed)) reasons.push("low cost");
    if (item.transportCarbonKg != null && strong(co2, co2Med)) reasons.push("low transport CO₂");
    if (strong(assembly, asmMed)) reasons.push("quick to assemble");
    const why = reasons.length ? reasons.join(" · ") : "balanced on cost, carbon and assembly";

    return { item, score, cost, co2, assembly, why };
  });

  scored.sort((a, b) => b.score - a.score);
  const n = Math.max(min, Math.min(max, scored.length));
  return scored.slice(0, n);
}
