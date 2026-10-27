/**
 * Design tokens — UI-SPEC §2.3 (LOCKED palette, immutable) + the domain data
 * tokens the map fields consume. Typed mirror of the CSS custom properties in
 * styles.css. Components consume the SEMANTIC names (Tailwind `bg-surface`,
 * `text-data-heat`), never these raw hues — this export exists for the few places
 * that need a hex in JS (deck.gl layer color ramps, canvas legends, SVG marks).
 *
 * The 12 locked primitives are the ONLY hues in the product. Do not invent.
 */

/** The 12 LOCKED primitive hues (UI-SPEC §2.3). Immutable — no additions. */
export const PALETTE = {
  black: "#0A0A0A",
  paper: "#F2F0ED",
  white: "#FFFFFF",
  ink: "#16181D",
  // Owner directive (2026-06-24): the brand accent is ORANGE, not green. Token NAMES
  // kept (`green`/`green2`) so every `var(--green)` / PALETTE.green reference flips at
  // once; the hues are a deep + vivid orange, kept distinct from --heat (red-orange).
  green: "#B0541A",
  green2: "#E07D2B",
  amber: "#DFA22E",
  red: "#C0392B",
  teal: "#0E8C8C",
  heat: "#E8462A",
  indigo: "#4746D8",
  grey: "#A8AAB6",
} as const;

export type PaletteName = keyof typeof PALETTE;

/** Provenance tier → mark color (used for map marks + non-DOM legends). */
export const PROVENANCE_COLOR: Record<"GROUNDED" | "DERIVED" | "ASSUMED", string> = {
  GROUNDED: PALETTE.green,
  DERIVED: PALETTE.amber,
  ASSUMED: PALETTE.grey,
};

/**
 * UTCI heat bands (UI-SPEC §4.1 / ORGANIZER-OUTPUT-SPEC) — kept for the legend +
 * the danger-line reference. Shade is eligible only ≥26 °C; 32 °C is the dangerous line.
 */
export const UTCI_BANDS: { maxC: number; rgb: [number, number, number]; label: string }[] = [
  { maxC: 26, rgb: [210, 206, 200], label: "Comfortable (<26 °C)" },
  { maxC: 32, rgb: [223, 162, 46], label: "Caution (26–32 °C)" },
  { maxC: 38, rgb: [232, 96, 42], label: "Dangerous (32–38 °C)" },
  { maxC: 46, rgb: [232, 70, 42], label: "Severe (38–46 °C)" },
  { maxC: Infinity, rgb: [150, 30, 20], label: "Emergency (>46 °C)" },
];

/**
 * CONTINUOUS UTCI ramp — perceptually luminance-rising, warming hue, anchored to
 * ABSOLUTE thresholds (so colour keeps its real meaning, not a misleading local
 * stretch). Continuous (not stepped) so a site that sits inside ONE band — e.g.
 * a mild day at 23–31 °C — still shows real nuance instead of a flat wash.
 * NEVER rainbow/jet. Stops at the band breakpoints so the legend lines up.
 */
const UTCI_STOPS: { c: number; rgb: [number, number, number] }[] = [
  { c: 9, rgb: [150, 178, 196] },   // cool blue-grey (no stress, low)
  { c: 26, rgb: [226, 208, 150] },  // pale amber — caution line
  { c: 32, rgb: [233, 150, 58] },   // orange — dangerous line
  { c: 38, rgb: [224, 79, 44] },    // heat red — severe
  { c: 46, rgb: [150, 30, 22] },    // deep red — emergency
];

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

export function utciColor(c: number): [number, number, number] {
  if (c <= UTCI_STOPS[0].c) return UTCI_STOPS[0].rgb;
  for (let i = 1; i < UTCI_STOPS.length; i++) {
    if (c <= UTCI_STOPS[i].c) {
      const lo = UTCI_STOPS[i - 1];
      const hi = UTCI_STOPS[i];
      const t = (c - lo.c) / (hi.c - lo.c);
      return [
        lerp(lo.rgb[0], hi.rgb[0], t),
        lerp(lo.rgb[1], hi.rgb[1], t),
        lerp(lo.rgb[2], hi.rgb[2], t),
      ];
    }
  }
  return UTCI_STOPS[UTCI_STOPS.length - 1].rgb;
}

/**
 * HeatmapLayer colorRange (spec S7 thermal well) — 6 stops, transparent-cool → emergency.
 * Low end barely-there so the near-black basemap shows through; high end seethes red.
 * oklch ramp from the spec: caution 0.80/0.10/90 → emergency 0.52/0.20/28, approximated in sRGB.
 */
export const HEAT_COLOR_RANGE: [number, number, number][] = [
  [40, 70, 92],     // cool floor (near-black blue) — comfortable
  [120, 150, 120],  // pale — approaching caution
  [226, 208, 150],  // caution (26 °C)
  [233, 150, 58],   // dangerous (32 °C)
  [224, 79, 44],    // severe (38 °C)
  [150, 30, 22],    // emergency (46+ °C)
];

/** Crowd ramp — cool hue family (paper → teal → indigo), distinct from heat. */
export function crowdColor(t: number): [number, number, number] {
  // t in 0..1. teal #0E8C8C → indigo #4746D8, luminance rising from paper.
  const a: [number, number, number] = [14, 140, 140];
  const b: [number, number, number] = [71, 70, 216];
  const k = Math.max(0, Math.min(1, t));
  return [
    Math.round(a[0] + (b[0] - a[0]) * k),
    Math.round(a[1] + (b[1] - a[1]) * k),
    Math.round(a[2] + (b[2] - a[2]) * k),
  ];
}

/** Hex → [r,g,b]. */
export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
