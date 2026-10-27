/**
 * "Beyond Festivals" scenarios — proof that the U-Shade engine is site-general.
 *
 * The SAME timeline × attractors → heat × crowd → ranked-shade engine, pointed at
 * non-festival sites (a park, a schoolyard, a plaza, a beach). Each domain ships a
 * small SYNTHETIC dataset (frontend/public/scenarios/<id>.json, built by
 * scripts/gen-scenario-data.mjs) shaped exactly like the festival's DaytimeField
 * data — so the real signature animation, crowd→heat coupling, and worst-cell
 * crosshair all run unchanged on fabricated-but-honest inputs.
 *
 * This registry is intentionally thin: copy + framing for the picker. Everything
 * geometric/temporal lives in the JSON, loaded at runtime by the scenario shell.
 *
 * ISOLATION: nothing here is referenced by the festival flow. Entry is the new
 * "Beyond Festivals" door on the welcome screen; the festival path never imports it.
 */

export type ScenarioId = "park" | "playground" | "plaza" | "beach";

/** Lightweight registry entry — the gallery card. */
export type Scenario = {
  id: ScenarioId;
  label: string; // "City park"
  site: string; // basemap location, must match the JSON `site`
  tagline: string; // one line: what U-Shade does here
  blurb: string; // 1–2 sentences for the card body
  attractorsNote: string; // names the crowd magnets in plain language
  accent: "green" | "teal" | "amber" | "indigo";
  animUrl: string; // /scenarios/<id>.json
};

export const SCENARIOS: Scenario[] = [
  {
    id: "park",
    label: "City park",
    site: "Parc de la Ciutadella, Barcelona",
    tagline: "Shade the playground and lawn before the afternoon peak",
    blurb:
      "A public park fills and empties across the day. U-Shade crosses the heat grid with where families actually gather and ranks the few canopy spots that protect the most people.",
    attractorsNote: "Playground · fountain · picnic lawn · café",
    accent: "green",
    animUrl: "/scenarios/park.json",
  },
  {
    id: "playground",
    label: "School playground",
    site: "Escola del Mar — schoolyard",
    tagline: "Cool the asphalt where kids cluster at recess",
    blurb:
      "A bare yard bakes by midday recess. The same engine reads the bell-driven timeline and the play equipment kids swarm, then sizes shade for a lower heat tolerance.",
    attractorsNote: "Climbing frame · swings · court · sandpit",
    accent: "teal",
    animUrl: "/scenarios/playground.json",
  },
  {
    id: "plaza",
    label: "Transit plaza",
    site: "Plaça de Catalunya, Barcelona",
    tagline: "Shade the dwell points along the commute",
    blurb:
      "A stone plaza has no canopy and constant flow. U-Shade finds where crowds queue and linger — metro exits, market stalls, bus stops — and ranks shade by dwell × heat.",
    attractorsNote: "Metro exits · market stalls · bus stop · seating",
    accent: "indigo",
    animUrl: "/scenarios/plaza.json",
  },
  {
    id: "beach",
    label: "Beach promenade",
    site: "Platja de la Barceloneta",
    tagline: "Place shade where bathers gather at midday sun",
    blurb:
      "Sand reflects and the midday sun is relentless. The engine tracks where beachgoers converge — access ramps, chiringuito, volleyball — and ranks the highest-impact shade.",
    attractorsNote: "Access ramp · chiringuito · volleyball · showers",
    accent: "amber",
    animUrl: "/scenarios/beach.json",
  },
];

export function getScenario(id: ScenarioId): Scenario {
  const s = SCENARIOS.find((x) => x.id === id);
  if (!s) throw new Error(`unknown scenario ${id}`);
  return s;
}

// ── runtime dataset shape (the generated JSON) ──────────────────────────────
export type Corners = {
  SW: [number, number];
  SE: [number, number];
  NE: [number, number];
  NW: [number, number];
};

export type ScenarioZone = {
  rank: number;
  center: [number, number];
  footprint: [number, number][];
  areaM2: number;
  peakC: number;
  whyHere: string;
  marginalDemand: number;
  crowdShare: number;
  coolingC: number;
};

export type ScenarioAttractor = {
  name: string;
  kind: string; // "stage" | "entrance" | "amenity"
  lon: number;
  lat: number;
};

/** Everything DaytimeField needs PLUS the scenario shell's attractors/zones. */
export type ScenarioData = {
  site: string;
  date: string;
  clockLabel: string;
  zoom: number;
  center: [number, number];
  bounds: Corners;
  lattice: { cols: number; rows: number; cell_size_m: number };
  hours: string[];
  heat_hours: { hour: string; cells: [number, number, number][] | null }[];
  frames: [number, number][][];
  n_agents: number;
  utci_min: number;
  utci_max: number;
  attractors: ScenarioAttractor[];
  zones: ScenarioZone[];
  headline: { peakC: number; peopleInHeat: number };
};
