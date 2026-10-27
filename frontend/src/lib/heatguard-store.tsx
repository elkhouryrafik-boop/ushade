import { createContext, useContext, useEffect, useMemo, useReducer, type ReactNode } from "react";
import type { StatusResponse } from "./heatguard-api";
import { loadPersisted, savePersisted } from "./persist";

export type Step = "login" | "workspace" | "simulation" | "structural" | "dashboard";

/** All wizard stages riding the single persistent map canvas. */
// "report" was MERGED into "handoff" (the single editorial deliverable, "The Plan") —
// 2026-06-24 owner directive. The type is kept loose to tolerate older persisted saves
// that may still carry stage:"report"; hydrate() rewrites it to "handoff" (see below).
export type WizardStage = "brief" | "site" | "layout" | "placement" | "materials" | "handoff";
// Canonical journey (spec flow): tell us about it → draw the site → place the layout
// → run + accept the shade zones → U-Shade clads them in sourced material → THE PLAN
// (the merged handoff + report deliverable). Materials comes AFTER the zones exist
// (S9 "clad it · source the material").
export const WIZARD_STAGES: WizardStage[] = ["brief", "site", "layout", "placement", "materials", "handoff"];

export type ShapeKind =
  | "boundary"
  | "stage"
  | "entrance"
  | "restroom"
  | "food"
  | "medical"
  | "service";

export type Shape = {
  id: string;
  kind: ShapeKind;
  points: [number, number][]; // WGS84 [lon,lat] when geo=true; else 0..100×60 svg space
  /** True when points are real WGS84 lon/lat (projected to the map live via bounds).
   *  Explicit because [lon 2.2, lat 41.4] is ambiguous vs the 0..100×60 svg box. */
  geo?: boolean;
  /** Real-world footprint in m² (from @turf/area at draw time); 0/undefined for points. */
  areaM2?: number;
  /** Display name (e.g. "Estrella Damm", "ENTRANCE A") shown on the map + layer list. */
  label?: string;
};

export type Theme = string;

/**
 * One act on the bill — who plays, on which stage, and when. This is the schedule
 * that powers the crowd simulator: the migrating crowd concentrates at the stage
 * that is currently playing, weighted by the act's pull (headliner > main > support).
 */
export type LineupSlot = {
  id: string;
  act: string;
  stage: string;
  /** 24h "HH:MM" local. */
  start: string;
  end: string;
  draw: "headliner" | "main" | "support";
};

export type Project = {
  capacity: number;
  budget: number;
  date: string;
  theme: Theme;
  /** The bill: acts × stage × set time — drives the daytime crowd migration. */
  lineup: LineupSlot[];
  /** Real-world m² area of the drawn boundary (computed by the map). */
  siteAreaM2: number;
  shapes: Shape[];
};

type State = {
  step: Step;
  /** Active wizard stop (UI-SPEC §3). The new unified shell drives off this. */
  stage: WizardStage;
  /** 'wizard' enforces sequential unlock; 'hub' lets returning users jump freely. */
  navMode: "wizard" | "hub";
  project: Project;
  /** Project ID of the live simulation run ("primavera-demo"), null before any run starts. */
  simRunId: string | null;
  /** Polled stage states from GET /api/status/{simRunId}; null before any run starts. */
  runStatus: StatusResponse | null;
  /** Ranks of placement zones the human has Accepted (AI proposes / human commits). */
  acceptedRanks: number[];
  /** True while the climate→crowd→placement analysis is revealing (the animated
   *  pipeline screen). Flips false when the placement output is ready. */
  analyzing: boolean;
  /** Binding material holds: material id → { expiry epoch-ms, backend hold id }.
   *  A hold is a binding reservation, NOT a soft favourite (UI-SPEC §8.4). The holdId
   *  is the real `/api/marketplace/holds` id (empty string on the offline mock path). */
  materialHolds: Record<string, { expiresAt: number; holdId: string }>;
  /** Indicative "add to plan" shortlist (non-binding, ghost state) — material ids. */
  materialPlan: string[];
  /** Transient: rank of the zone currently hovered (list ↔ map cross-highlight). */
  hoveredZone: number | null;
  /** Active layout-placement tool (S5) — drives the map draw mode so the palette in
   *  the aside and the draw control on the map share one selection. */
  layoutTool: ShapeKind | null;
};

const initial: State = {
  // MOCK-03: boot straight into the workspace — there is no real auth (login is
  // deferred). "login" stays a valid Step member only for the ?step= deep-link.
  step: "workspace",
  stage: "site",
  navMode: "wizard",
  simRunId: null,
  runStatus: null,
  acceptedRanks: [],
  analyzing: false,
  materialHolds: {},
  materialPlan: [],
  hoveredZone: null,
  layoutTool: null,
  project: {
    capacity: 12000,
    budget: 15000,
    date: new Date().toISOString().slice(0, 10),
    theme: "Sun-bleached natural canopy, reclaimed timber and woven jute, organic flowing forms inspired by Mediterranean dunes",
    lineup: [
      { id: "ln-1", act: "Opening DJ", stage: "Mar Bonus Stage", start: "16:00", end: "18:00", draw: "support" },
      { id: "ln-2", act: "Indie headliner", stage: "Estrella Damm Main", start: "18:30", end: "20:00", draw: "main" },
      { id: "ln-3", act: "Electronic headliner", stage: "Estrella Damm Main", start: "21:00", end: "22:30", draw: "headliner" },
      { id: "ln-4", act: "Late techno", stage: "Boiler Room", start: "22:30", end: "01:00", draw: "main" },
    ],
    siteAreaM2: 0,
    shapes: [],
  },
};

type Action =
  | { type: "setStep"; step: Step }
  | { type: "setStage"; stage: WizardStage }
  | { type: "setNavMode"; mode: "wizard" | "hub" }
  | { type: "setProject"; patch: Partial<Project> }
  | { type: "addShape"; shape: Shape }
  | { type: "updateShape"; shape: Shape }
  | { type: "setShapes"; shapes: Shape[] }
  | { type: "removeShape"; id: string }
  | { type: "startRun"; runId: string }
  | { type: "setRunStatus"; status: StatusResponse }
  | { type: "toggleAccept"; rank: number }
  | { type: "setAnalyzing"; analyzing: boolean }
  | { type: "placeHold"; id: string; expiresAt: number; holdId?: string }
  | { type: "releaseHold"; id: string }
  | { type: "togglePlan"; id: string }
  | { type: "setHoveredZone"; rank: number | null }
  | { type: "setLayoutTool"; tool: ShapeKind | null }
  | { type: "reset" };

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "setStep": return { ...s, step: a.step };
    case "setStage": return { ...s, stage: a.stage };
    case "setNavMode": return { ...s, navMode: a.mode };
    case "setProject": return { ...s, project: { ...s.project, ...a.patch } };
    case "addShape": return { ...s, project: { ...s.project, shapes: [...s.project.shapes, a.shape] } };
    case "updateShape": {
      // Replace the shape with the matching id (mapbox-gl-draw edit/move/resize);
      // upsert if it somehow isn't present so an edit never silently no-ops.
      const exists = s.project.shapes.some(x => x.id === a.shape.id);
      const shapes = exists
        ? s.project.shapes.map(x => x.id === a.shape.id ? a.shape : x)
        : [...s.project.shapes, a.shape];
      return { ...s, project: { ...s.project, shapes } };
    }
    case "setShapes": return { ...s, project: { ...s.project, shapes: a.shapes } };
    case "removeShape": return { ...s, project: { ...s.project, shapes: s.project.shapes.filter(x => x.id !== a.id) } };
    case "startRun": return {
      ...s,
      simRunId: a.runId,
      acceptedRanks: [],
      analyzing: true,
      // Seed the THREE real stage keys at "pending" so the stepper renders three
      // rows before the first /api/status poll lands (post-pivot backend shape:
      // climate → crowd → placement; D-06).
      runStatus: {
        utci_grid: "pending",
        crowd_grid: "pending",
        structure_zones: "pending",
      },
    };
    case "setRunStatus": return { ...s, runStatus: a.status };
    case "setLayoutTool": return { ...s, layoutTool: a.tool };
    case "setAnalyzing": return { ...s, analyzing: a.analyzing };
    case "placeHold": {
      // Placing a binding hold removes it from the indicative plan (promotes ghost→bound).
      return {
        ...s,
        materialHolds: { ...s.materialHolds, [a.id]: { expiresAt: a.expiresAt, holdId: a.holdId ?? "" } },
        materialPlan: s.materialPlan.filter((p) => p !== a.id),
      };
    }
    case "releaseHold": {
      const next = { ...s.materialHolds };
      delete next[a.id];
      return { ...s, materialHolds: next };
    }
    case "togglePlan": {
      const has = s.materialPlan.includes(a.id);
      return {
        ...s,
        materialPlan: has ? s.materialPlan.filter((p) => p !== a.id) : [...s.materialPlan, a.id],
      };
    }
    case "setHoveredZone": return { ...s, hoveredZone: a.rank };
    case "toggleAccept": {
      const has = s.acceptedRanks.includes(a.rank);
      return {
        ...s,
        acceptedRanks: has
          ? s.acceptedRanks.filter((r) => r !== a.rank)
          : [...s.acceptedRanks, a.rank],
      };
    }
    case "reset": return initial;
  }
}

const Ctx = createContext<{ state: State; dispatch: React.Dispatch<Action> } | null>(null);

/** Hydrate initial state from a persisted save (resume). analyzing is never resumed. */
function hydrate(base: State): State {
  const p = loadPersisted();
  if (!p) return base;
  return {
    ...base,
    // Merge over defaults so older saves missing newer fields (e.g. lineup) stay valid.
    project: { ...base.project, ...(p.project as Partial<Project> | undefined) },
    // Migrate the retired "report" stage → "handoff" (the merged "The Plan" deliverable).
    stage: ((p.stage as string) === "report" ? "handoff" : p.stage) ?? base.stage,
    navMode: "hub", // a returning user with a save gets free navigation (UI-SPEC §3.2)
    simRunId: p.simRunId ?? null,
    runStatus: null, // never resume a run status; an in-flight run is re-driven, not restored
    acceptedRanks: p.acceptedRanks ?? [],
    materialHolds: p.materialHolds ?? {},
    materialPlan: p.materialPlan ?? [],
    analyzing: false,
  };
}

export function HeatGuardProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial, hydrate);
  // Persist the meaningful slice on change (debounced via microtask is overkill for
  // this size — direct write is fine; save is best-effort + SSR-guarded).
  useEffect(() => {
    savePersisted({
      project: state.project,
      stage: state.stage,
      simRunId: state.simRunId,
      acceptedRanks: state.acceptedRanks,
      materialHolds: state.materialHolds,
      materialPlan: state.materialPlan,
    });
  }, [
    state.project, state.stage, state.simRunId,
    state.acceptedRanks, state.materialHolds, state.materialPlan,
  ]);
  const value = useMemo(() => ({ state, dispatch }), [state]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useHeatGuard() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useHeatGuard outside provider");
  return v;
}

export const SHAPE_META: Record<ShapeKind, { label: string; color: string; mode: "polygon" | "box" | "point" }> = {
  boundary:   { label: "Event Boundary", color: "oklch(0.85 0.02 250)", mode: "polygon" },
  stage:      { label: "Stage",          color: "oklch(0.68 0.21 25)",  mode: "box" },   // red-orange — the crowd magnets
  entrance:   { label: "Entrance",       color: "#e07d2b",              mode: "point" }, // orange brand accent — crowd sources
  restroom:   { label: "Restrooms",      color: "oklch(0.70 0.16 250)", mode: "point" }, // blue
  food:       { label: "Food & Bar",     color: "oklch(0.80 0.16 70)",  mode: "point" }, // amber
  medical:    { label: "Medical / Safety", color: "oklch(0.65 0.24 20)", mode: "point" },// deep red
  service:    { label: "Services",       color: "oklch(0.62 0.03 250)", mode: "point" }, // muted grey — amenities
};
