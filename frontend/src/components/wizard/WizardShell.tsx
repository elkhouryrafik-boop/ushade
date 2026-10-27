import { useEffect, useMemo, useState } from "react";
import { HeatGuardProvider, useHeatGuard, type ShapeKind } from "@/lib/heatguard-store";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { getFestivalSchema } from "@/lib/heatguard-api";
import { schemaPoints, festivalSchemaLayers } from "@/lib/festival-schema-layers";
import { PolygonLayer } from "@deck.gl/layers";
import { hexToRgb, PALETTE } from "@/lib/tokens";
import { MapProvider, MapCanvas, useMapCanvas } from "./PersistentMapCanvas";
import { WizardRail } from "./WizardRail";
import { LayerToggle } from "./LayerToggle";
import { DrawControl } from "../heatguard/map/DrawControl";
import { SchemaLabels } from "./SchemaLabels";
import { ZoneMarkers } from "./ZoneMarkers";
import { HeatCrowdLegend } from "./HeatCrowdLegend";
import { DaytimeField } from "./DaytimeField";
import { SiteStage } from "./stages/SiteStage";
import { MaterialsStage } from "./stages/MaterialsStage";
import { PlacementStage } from "./stages/PlacementStage";
import { HandoffStage } from "./stages/HandoffStage";
import { BriefScreen } from "./screens/BriefScreen";
import { LayoutScreen } from "./screens/LayoutScreen";
import { WelcomeScreen } from "./screens/WelcomeScreen";
import { DomainGallery } from "./screens/DomainGallery";
import { BeyondShell } from "./BeyondShell";
import { getScenario, type Scenario, type ScenarioId } from "@/lib/scenarios";
import { loadPersisted } from "@/lib/persist";
import { PrimerBanner } from "./PrimerBanner";
import { Toaster } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import { EditPencil, MapPin } from "iconoir-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { EASE, DUR } from "@/lib/motion";

/**
 * WizardShell — U-Shade organiser app.
 * One persistent Mapbox canvas with 7-stop wizard rail.
 * WelcomeScreen overlays Shell on first load.
 * Auto-theme: placement stage triggers data-theme="dark".
 */

const queryClient = new QueryClient();

const GREEN = hexToRgb(PALETTE.green);

/** Loads festival schema context layers once; pins them under every stage. */
function FestivalSchemaContext() {
  const { setBaseLayers } = useMapCanvas();
  const { state } = useHeatGuard();
  const boundary = useMemo(
    () => state.project.shapes.filter((s) => s.kind === "boundary" && s.geo && s.points.length >= 3),
    [state.project.shapes],
  );
  const { data } = useQuery({
    queryKey: ["festival-schema"],
    queryFn: getFestivalSchema,
    staleTime: Infinity,
  });
  useEffect(() => {
    const layers = data ? festivalSchemaLayers(schemaPoints(data.features)) : [];
    if (boundary.length) {
      layers.push(
        new PolygonLayer({
          id: "site-boundary",
          data: boundary,
          getPolygon: (s: (typeof boundary)[number]) => {
            const r = [...s.points];
            const [fx, fy] = r[0];
            const [lx, ly] = r[r.length - 1];
            if (fx !== lx || fy !== ly) r.push(r[0]);
            return r;
          },
          stroked: true,
          filled: false,
          getLineColor: [...GREEN, 230],
          getLineWidth: 2,
          lineWidthUnits: "pixels",
          parameters: { depthTest: false },
        }),
      );
    }
    setBaseLayers(layers);
  }, [data, boundary, setBaseLayers]);
  return null;
}

/** Routes stage → the correct aside panel. */
function StagePanel() {
  const { state } = useHeatGuard();
  switch (state.stage) {
    case "brief":
      return <BriefScreen />;
    case "layout":
      return <LayoutScreen />;
    case "site":
      return <SiteStage />;
    case "materials":
      return <MaterialsStage />;
    case "placement":
      return <PlacementStage />;
    case "handoff":
      return <HandoffStage />;
    default:
      return <SiteStage />;
  }
}

/** Persistent map column with draw control, PrimerBanner, and layer toggles. */
function MapColumn() {
  const { state, dispatch } = useHeatGuard();
  const { layerUI } = useMapCanvas();
  const [tool, setTool] = useState<ShapeKind | null>(null);
  const onSite = state.stage === "site";
  const onLayout = state.stage === "layout";
  const showZones = state.stage === "placement" || state.stage === "handoff";

  // The draw control is shared: on Site it draws the boundary polygon (local tool);
  // on Layout it drops amenity points driven by the palette's shared layoutTool.
  const drawTool = onLayout ? state.layoutTool : tool;
  const setDrawTool = onLayout
    ? (t: ShapeKind | null) => dispatch({ type: "setLayoutTool", tool: t })
    : setTool;

  return (
    <div className="relative min-w-0 flex-1">
      <MapCanvas>
        <SchemaLabels />
        {showZones && <ZoneMarkers />}
        {/* Animated daytime heat × crowd field (hourly cross-fade + crowd→heat
            coupling + moving dots + day-clock) — the signature placement view. */}
        {state.stage === "placement" && <DaytimeField />}
        {(onSite || onLayout) && <DrawControl activeTool={drawTool} setActiveTool={setDrawTool} />}
      </MapCanvas>

      {showZones && <HeatCrowdLegend />}

      {/* Parc del Fòrum primer banner — top-right of map, dismissible */}
      <PrimerBanner />

      {/* Site label chip (top-left) */}
      <div className="pointer-events-none absolute left-4 top-4 z-20 flex items-center gap-2 px-3 py-2 backdrop-blur"
        style={{
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          background: "color-mix(in srgb, var(--surface) 90%, transparent)",
        }}
      >
        <MapPin className="size-3.5 shrink-0" style={{ color: "var(--teal)" }} strokeWidth={1.5} />
        <span className="font-mono text-xs" style={{ color: "var(--text-primary)" }}>Parc del Fòrum, Barcelona</span>
      </div>

      {/* Draw-boundary affordance (Site stage only) */}
      {onSite && (
        <Button
          size="sm"
          variant={tool === "boundary" ? "default" : "outline"}
          onClick={() => setTool("boundary")}
          className="absolute left-4 top-16 z-20 bg-surface/90 backdrop-blur focus-visible:ring-2 focus-visible:ring-offset-2"
        >
          <EditPencil className="size-3.5" strokeWidth={1.5} />
          {tool === "boundary" ? "Drawing… click to place vertices" : "Draw boundary"}
        </Button>
      )}

      <LayerToggle layers={layerUI.rows} onToggle={layerUI.onToggle} />
    </div>
  );
}

/** Shell mounts map once; apart from WelcomeScreen, all stages render here. */
function Shell() {
  const { state } = useHeatGuard();
  const reduce = useReducedMotion();

  // Materials + The Plan (merged handoff) are full-page DOCUMENTS (their own "world"),
  // not the 400px map-side panel. Everything else is the map workspace (rail+map+aside).
  const fullPage = state.stage === "materials" || state.stage === "handoff";

  // Materials renders FULL-BLEED (Airbnb-style split: cards + map, rebuilt by the
  // materials agent). The Plan stays a centered editorial column. Map stages keep the
  // map + 400px aside.
  const fullBleed = state.stage === "materials";

  // Whole-app DARK (owner directive, 2026-06-24): every stage + the welcome run on the
  // dark surface, not just the map views. Tokens flip via [data-theme="dark"].
  useEffect(() => {
    document.documentElement.dataset.theme = "dark";
    return () => {
      document.documentElement.dataset.theme = "light";
    };
  }, []);

  // ── Transition choreography (tokens only; every variant settles, no loops) ──
  // Map-side aside: each stage's panel cross-slides in from the right and the
  // outgoing one slips left. Reduced-motion → opacity-only (no transform).
  const asidePanel = reduce
    ? {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: DUR.inspector / 1000, ease: EASE.out },
      }
    : {
        initial: { opacity: 0, x: 22 },
        animate: { opacity: 1, x: 0 },
        exit: { opacity: 0, x: -22 },
        transition: { duration: DUR.card / 1000, ease: EASE.out },
      };

  // Document "rise": the full-page world deliberately rises over the map and
  // settles (translateY + a hair of scale for depth). On exit it falls back down,
  // returning the map. Reduced-motion → opacity-only.
  const documentRise = reduce
    ? {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: DUR.inspector / 1000, ease: EASE.out },
      }
    : {
        initial: { opacity: 0, y: 44, scale: 0.985 },
        animate: { opacity: 1, y: 0, scale: 1 },
        exit: { opacity: 0, y: 28, scale: 0.99 },
        transition: { duration: DUR.stage / 1000, ease: EASE.out },
      };

  // Scrim: a thin veil that fades the live map down behind a rising document so
  // moving stage→stage reads as crossing into another world (depth, not a cut).
  const scrim = reduce
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: { duration: DUR.inspector / 1000, ease: EASE.out } }
    : { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: { duration: DUR.stage / 1000, ease: EASE.out } };

  return (
    <MapProvider>
      <FestivalSchemaContext />
      <a
        href="#stage-panel"
        className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground focus:not-sr-only focus:absolute focus:left-3 focus:top-3"
      >
        Skip to controls
      </a>
      <div
        className="flex h-screen w-full overflow-hidden"
        style={{ background: "var(--bg)", color: "var(--text-primary)" }}
      >
        <WizardRail />
        {/* Content region. The Mapbox workspace stays MOUNTED the whole time (never
            torn down between stages); full-page documents RISE over it as an overlay,
            so moving stage→stage reads as crossing into another world. */}
        <div className="relative flex min-w-0 flex-1">
          <MapColumn />
          {/* Workspace side panel — only for the map stages (brief/site/layout/placement).
              Each stage's panel slides + fades in (per-phase transition). */}
          {!fullPage && (
            <aside
              id="stage-panel"
              aria-label="Stage controls"
              className="flex w-[400px] shrink-0 flex-col"
              style={{ borderLeft: "1px solid var(--border)", background: "var(--bg)" }}
            >
              <AnimatePresence mode="wait">
                <motion.div
                  key={state.stage}
                  className="flex min-h-0 flex-1 flex-col"
                  initial={asidePanel.initial}
                  animate={asidePanel.animate}
                  exit={asidePanel.exit}
                  transition={asidePanel.transition}
                >
                  <StagePanel />
                </motion.div>
              </AnimatePresence>
            </aside>
          )}
          {/* Scrim — veils the live map behind a rising document so the change reads
              as crossing into another world (depth), never an abrupt cut. Sits below
              the document, above the map; pointer-events off so it never blocks. */}
          <AnimatePresence>
            {fullPage && (
              <motion.div
                key="doc-scrim"
                aria-hidden
                className="pointer-events-none absolute inset-0 z-20"
                style={{ background: "color-mix(in srgb, var(--ink) 38%, transparent)" }}
                initial={scrim.initial}
                animate={scrim.animate}
                exit={scrim.exit}
                transition={scrim.transition}
              />
            )}
          </AnimatePresence>
          {/* Full-page document (materials/handoff/report) — rises over the map. */}
          <AnimatePresence>
            {fullPage && (
              <motion.main
                key={state.stage}
                id="stage-panel"
                aria-label="Document"
                className="absolute inset-0 z-30 overflow-y-auto"
                style={{ background: "var(--bg)", transformOrigin: "50% 100%" }}
                initial={documentRise.initial}
                animate={documentRise.animate}
                exit={documentRise.exit}
                transition={documentRise.transition}
              >
                {fullBleed ? (
                  // Materials: full-bleed split (no clamp, no padding — owns its layout).
                  <StagePanel />
                ) : (
                  // The Plan: centered editorial column on the dark deliverable surface.
                  <div className="mx-auto w-full max-w-3xl px-12 py-12">
                    <StagePanel />
                  </div>
                )}
              </motion.main>
            )}
          </AnimatePresence>
        </div>
      </div>
      <Toaster />
    </MapProvider>
  );
}

/** Root: the WelcomeScreen overlay is ALWAYS the entry (new + returning) — there is
 *  no separate dashboard screen. Mounts after client paint so the overlay decision
 *  is client-only (no hydration flash). */
type RootMode = "welcome" | "festival" | "gallery" | "beyond";

function Root() {
  const { dispatch } = useHeatGuard();
  const [ready, setReady] = useState(false);
  const [mode, setMode] = useState<RootMode>("welcome");
  // Active "Beyond Festivals" scenario — null on the festival path. ISOLATED from the
  // HeatGuard store, so the festival flow is provably untouched by scenario mode.
  const [scenario, setScenario] = useState<Scenario | null>(null);

  // Read the persisted save ONCE on mount (client-only, after the hydration gate).
  // The store is already hydrated from this same slice by HeatGuardProvider; we re-read
  // it here only to (a) decide whether "create" is destructive and (b) feed the welcome
  // "Continue" list. Existing helper — no new store action invented.
  const [saved, setSaved] = useState<ReturnType<typeof loadPersisted>>(null);

  useEffect(() => {
    setSaved(loadPersisted());
    setReady(true);
  }, []);

  if (!ready) return null;

  // A save is "meaningful" once a boundary has been drawn (siteAreaM2 > 0) — mirrors
  // persist.hasSavedProject(). Only then is "Create" destructive and Resume reachable.
  const savedAreaM2 = (saved?.project as { siteAreaM2?: number } | undefined)?.siteAreaM2 ?? 0;
  const hasMeaningfulSave = !!saved && savedAreaM2 > 0;

  // Feed the returning-user "Continue" list from the persisted slice (bug 3). Without
  // this the list can never render. One entry — the single persisted project (KEY is
  // single-slot today), shaped to WelcomeScreen's SavedProject.
  const savedProjects = hasMeaningfulSave
    ? [
        {
          name:
            ((saved!.project as { theme?: string }).theme || "Untitled festival").slice(0, 48),
          site: "Parc del Fòrum, Barcelona",
          status: saved!.stage === "handoff" ? "complete" : "in progress",
          lastEdited: new Date(saved!.savedAt).toLocaleDateString(),
        },
      ]
    : [];

  // Beyond Festivals — render the PARALLEL scenario shell instead of the festival Shell
  // (its own map, own state; the festival workspace is not mounted here).
  if (mode === "beyond" && scenario) {
    return (
      <BeyondShell
        scenario={scenario}
        onExit={() => {
          setScenario(null);
          setMode("welcome");
        }}
      />
    );
  }

  return (
    <>
      <Shell />
      {mode === "welcome" && (
        <WelcomeScreen
          savedProjects={savedProjects}
          onNew={() => {
            setMode("festival");
            // "Create your festival". Only reset when there is NOTHING worth keeping —
            // a meaningful saved project is preserved (bug 1: never silently nuke a save).
            // With a save present we start a fresh brief WITHOUT a destructive reset, so
            // the persisted project survives until the user explicitly discards it.
            if (!hasMeaningfulSave) {
              dispatch({ type: "reset" });
            }
            dispatch({ type: "setStage", stage: "brief" });
          }}
          onResume={(project) => {
            setMode("festival");
            if (project) {
              // CONTINUE a real saved project (bug 2). The store was already hydrated
              // from this same persisted slice on mount (HeatGuardProvider → hydrate),
              // so the drawn boundary / accepted zones / current stage are already live.
              // We just drop the overlay and land on the persisted stage — never
              // overwrite the user's save with demo data.
              dispatch({ type: "setStage", stage: saved?.stage ?? "placement" });
              return;
            }
            // No project → the "Try Parc del Fòrum" demo door: load the canned demo.
            dispatch({
              type: "setProject",
              patch: {
                capacity: 70000,
                budget: 80000,
                date: "2025-06-01",
                theme: "Sun-bleached natural canopy, reclaimed timber and woven jute",
                siteAreaM2: 197000,
              },
            });
            dispatch({ type: "startRun", runId: "primavera-demo" });
            dispatch({ type: "setStage", stage: "placement" });
          }}
          onBeyond={() => setMode("gallery")}
        />
      )}
      {mode === "gallery" && (
        <DomainGallery
          onPick={(id: ScenarioId) => {
            setScenario(getScenario(id));
            setMode("beyond");
          }}
          onBack={() => setMode("welcome")}
        />
      )}
    </>
  );
}

export function WizardApp() {
  return (
    <QueryClientProvider client={queryClient}>
      <HeatGuardProvider>
        <Root />
      </HeatGuardProvider>
    </QueryClientProvider>
  );
}
