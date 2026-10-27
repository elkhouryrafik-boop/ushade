import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { PolygonLayer } from "@deck.gl/layers";
import { useHeatGuard } from "@/lib/heatguard-store";
import {
  getStructureZones,
  getHeatArtifact,
  getCrowdArtifact,
  getFestivalSchema,
  getStatus,
  getAcceptance,
  type StructureZone,
} from "@/lib/heatguard-api";
import { isCustomRun } from "@/lib/useRunPipeline";
import { schemaPoints, nearestFeature } from "@/lib/festival-schema-layers";
import { hexToRgb, PALETTE, UTCI_BANDS } from "@/lib/tokens";
import { useMapCanvas } from "../PersistentMapCanvas";
import { StageScaffold, EmptyState } from "../StageScaffold";
import { AnalysisChecklist } from "../AnalysisChecklist";
import { Check, WarningTriangle, ShieldAlt, Plus } from "iconoir-react";
import { EASE, DUR } from "@/lib/motion";

/**
 * S6/S7/S8 — Analysis → Crowd×Heat → Shade placement.
 * Dark thermal well (data-theme="dark" managed by WizardShell).
 * Real ranked zones from GET /api/artifacts/{id}/structure_zones.
 * All backend calls unchanged from the original implementation.
 */

const GREEN = hexToRgb(PALETTE.green);
const RED = hexToRgb(PALETTE.red);
const AMBER = hexToRgb(PALETTE.amber);
const GREEN2 = hexToRgb(PALETTE.green2);

function priorityColor(rank: number): [number, number, number] {
  if (rank <= 2) return RED;
  if (rank === 3) return AMBER;
  return GREEN2;
}

// "Why here?" — honest language tied to the real signals the placer crossed
// (dangerous heat × dense crowd). Rank carries the placer's hot×busy ordering.
function whyHere(rank: number, peakC?: number): string {
  const heat = peakC !== undefined && peakC >= 32 ? "Dangerous heat" : "High heat";
  if (rank <= 2) return `${heat} × dense crowd`;
  if (rank === 3) return `${heat} × busy ground`;
  return `${heat} × crowd flow`;
}


function bandFor(utci: number) {
  return UTCI_BANDS.find((b) => utci < b.maxC) ?? UTCI_BANDS[UTCI_BANDS.length - 1];
}

function inRing(lon: number, lat: number, ring: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function PlacementStage() {
  const { state, dispatch } = useHeatGuard();
  const { simRunId, acceptedRanks, hoveredZone } = state;
  const { setLayers, setLayerUI, mapRef } = useMapCanvas();
  const reduce = useReducedMotion();
  const [showZones, setShowZones] = useState(true);
  const [showAllZones, setShowAllZones] = useState(false);

  // A custom (organizer-drawn) run computes live — its artifacts appear over time, so
  // we keep retrying while analysing. The Fòrum demo is pre-baked, so one shot is enough.
  const custom = isCustomRun(simRunId);
  const analysingCustom = custom && state.analyzing;

  // Client-side watchdog (CCA-F P2 backstop): the backend marks a stage "failed" on
  // an internal error, but if the server process dies the status simply stops
  // advancing — a failed run would otherwise spin on "running" forever. We stamp the
  // moment analysis begins for THIS run, and after a hard cap surface an honest
  // "couldn't complete" failure rather than an infinite spinner. This is a guard, not
  // the primary terminator — real completion/failure still comes from the backend.
  const RUN_TIMEOUT_MS = 5 * 60 * 1000;
  const [pollStartedAt, setPollStartedAt] = useState<number | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    if (!analysingCustom) {
      setPollStartedAt(null);
      setTimedOut(false);
      return;
    }
    // Start the clock once per analysis session; reset by the !analysingCustom branch.
    setPollStartedAt((prev) => prev ?? Date.now());
  }, [analysingCustom]);
  useEffect(() => {
    if (!analysingCustom || pollStartedAt === null) return;
    const remaining = RUN_TIMEOUT_MS - (Date.now() - pollStartedAt);
    if (remaining <= 0) {
      setTimedOut(true);
      return;
    }
    const t = setTimeout(() => setTimedOut(true), remaining);
    return () => clearTimeout(t);
  }, [analysingCustom, pollStartedAt]);

  // Once we've timed out, STOP hammering a likely-dead backend (P2 guard). Real
  // success can still arrive right up to the cap; after it, the watchdog owns the verdict.
  const polling = analysingCustom && !timedOut;
  const heatQ = useQuery({
    queryKey: ["heat", simRunId],
    queryFn: () => getHeatArtifact(simRunId!),
    enabled: simRunId !== null,
    staleTime: Infinity,
    retry: false,
    refetchInterval: polling ? 4000 : false,
  });
  const crowdQ = useQuery({
    queryKey: ["crowd", simRunId],
    queryFn: () => getCrowdArtifact(simRunId!),
    enabled: simRunId !== null && heatQ.isSuccess,
    staleTime: Infinity,
    retry: false,
    refetchInterval: polling ? 4000 : false,
  });
  const zonesQ = useQuery({
    queryKey: ["zones", simRunId],
    queryFn: () => getStructureZones(simRunId!),
    enabled: simRunId !== null && crowdQ.isSuccess,
    staleTime: Infinity,
    retry: false,
    refetchInterval: polling ? 4000 : false,
  });
  // Real modeled cooling from the Phase-5b acceptance gate (utci_delta_c) — NOT a
  // hardcoded number. Falls back only if the artifact is missing.
  const acceptanceQ = useQuery({
    queryKey: ["acceptance", simRunId],
    queryFn: () => getAcceptance(simRunId!),
    enabled: simRunId !== null && zonesQ.isSuccess,
    staleTime: Infinity,
    retry: false,
  });
  // Real modeled cooling from the acceptance gate ONLY — null (shown "—") if not reported.
  const coolingC: number | null = acceptanceQ.data?.utci_delta_c ?? null;
  // Drive the analysis checklist + map reveal off REAL pipeline status for custom
  // runs (CCA-F P1/P2 — progress comes from the backend finishing, never a timer).
  const statusQ = useQuery({
    queryKey: ["status", simRunId],
    queryFn: () => getStatus(simRunId!),
    enabled: polling,
    refetchInterval: polling ? 4000 : false,
  });
  useEffect(() => {
    if (statusQ.data) dispatch({ type: "setRunStatus", status: statusQ.data });
  }, [statusQ.data, dispatch]);

  const zones = useMemo(() => zonesQ.data?.structures ?? [], [zonesQ.data]);
  const crowdCells = useMemo(() => crowdQ.data?.runs.v2.cells ?? [], [crowdQ.data]);
  const crowdMax = useMemo(
    () => crowdCells.reduce((m, c) => Math.max(m, c.density), 1),
    [crowdCells],
  );
  const totalDemand = zonesQ.data?.total_demand ?? 0;

  const schemaQ = useQuery({
    queryKey: ["festival-schema"],
    queryFn: getFestivalSchema,
    staleTime: Infinity,
  });
  const features = useMemo(
    () => (schemaQ.data ? schemaPoints(schemaQ.data.features) : []),
    [schemaQ.data],
  );
  const zoneName = (z: StructureZone) =>
    features.length ? nearestFeature(z.center, features) : null;

  const zonePeak = useMemo(() => {
    const cells = heatQ.data?.cells ?? [];
    const out: Record<number, number> = {};
    if (!cells.length) return out;
    for (const z of zones) {
      let peak = -Infinity;
      for (const c of cells) if (inRing(c.lon, c.lat, z.footprint)) peak = Math.max(peak, c.utci_c);
      if (peak > -Infinity) out[z.rank] = peak;
    }
    return out;
  }, [heatQ.data, zones]);
  const siteHottest = heatQ.data ? heatQ.data.utci_max_c : null;

  const acceptedZones = zones.filter((z) => acceptedRanks.includes(z.rank));
  const peopleInHeat = Math.round(totalDemand);
  const peopleShaded = Math.round(acceptedZones.reduce((s, z) => s + z.marginal_demand, 0));
  const pctShaded = peopleInHeat > 0 ? Math.round((peopleShaded / peopleInHeat) * 100) : 0;
  const costPerStructure = zonesQ.data?.stopping_rule?.cost_per_structure ?? 0;
  const costTotal = acceptedZones.length * costPerStructure;
  const costPerPerson = peopleShaded > 0 ? Math.round(costTotal / peopleShaded) : 0;

  const framedRef = useState({ done: false })[0];
  useEffect(() => {
    if (state.analyzing || !zones.length || framedRef.done) return;
    const lons = zones.flatMap((z) => z.footprint.map((p) => p[0]));
    const lats = zones.flatMap((z) => z.footprint.map((p) => p[1]));
    const map = mapRef.current;
    if (!map || !lons.length) return;
    framedRef.done = true;
    map.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 90, duration: 900, maxZoom: 17 },
    );
  }, [zones, state.analyzing, mapRef, framedRef]);

  useEffect(() => {
    if (zonesQ.data && state.runStatus?.structure_zones !== "done") {
      dispatch({
        type: "setRunStatus",
        status: { utci_grid: "done", crowd_grid: "done", structure_zones: "done" },
      });
    }
  }, [zonesQ.data, state.runStatus, dispatch]);

  useEffect(() => {
    const layers = [];
    // The animated heat × crowd field is owned by <DaytimeField> (its own overlay,
    // hourly cross-fade + crowd→heat coupling + day-clock). Here we only own the
    // ranked shade ZONES (the accept/dismiss interaction surface).
    if (showZones) {
      layers.push(
        new PolygonLayer<StructureZone>({
          id: "zones",
          data: zones,
          getPolygon: (d) => d.footprint,
          getFillColor: (d) =>
            acceptedRanks.includes(d.rank)
              ? [...GREEN, 190]
              : [...priorityColor(d.rank), hoveredZone === d.rank ? 150 : 95],
          getLineColor: (d) =>
            acceptedRanks.includes(d.rank) ? [...GREEN, 255] : [245, 245, 245, 255],
          getLineWidth: (d) =>
            hoveredZone === d.rank ? 5 : acceptedRanks.includes(d.rank) ? 4 : 2,
          lineWidthUnits: "pixels",
          stroked: true,
          filled: true,
          parameters: { depthCompare: "always" },
          updateTriggers: {
            getFillColor: [acceptedRanks, hoveredZone],
            getLineWidth: [acceptedRanks, hoveredZone],
          },
          pickable: true,
        }),
      );
    }
    setLayers(layers);
    setLayerUI({
      rows: [{ id: "zones", label: "Shade spots", tier: "ASSUMED", on: showZones }],
      onToggle: (id) => {
        if (id === "zones") setShowZones((v) => !v);
      },
    });
  }, [zones, showZones, acceptedRanks, hoveredZone, setLayers, setLayerUI]);

  const loading = zonesQ.isLoading;
  const failed = zonesQ.isError;

  // Step state: for a custom run, the REAL pipeline status drives it (the artifact
  // 404s while computing are expected, not failures). For the pre-baked demo, the
  // artifact query is the source of truth (a query error there = backend really down).
  const stepState = (
    q: { isError: boolean; isSuccess: boolean; isLoading: boolean },
    gateOpen: boolean,
    statusKey: "utci_grid" | "crowd_grid" | "structure_zones",
  ): "queued" | "running" | "done" | "failed" => {
    const rs = custom ? state.runStatus?.[statusKey] : undefined;
    if (q.isSuccess || rs === "done") return "done";
    // The backend emits "failed" (StageStatus union) when a stage throws — NOT "error",
    // which it never sends. A custom run reports failure via runStatus; the pre-baked
    // demo (no runStatus) reports it via the artifact query erroring. The watchdog
    // timeout surfaces a stalled/dead backend that never emitted "failed" at all.
    if (rs === "failed" || (rs === undefined && q.isError)) return "failed";
    // A custom run that has stalled past the hard cap (still pending/running) fails the
    // step that hasn't landed yet, so the checklist stops spinning forever.
    if (custom && timedOut && rs !== "done") return "failed";
    if (!gateOpen) return "queued";
    return "running";
  };

  const steps = [
    {
      key: "climate",
      label: "Mapping where it gets hottest",
      detail: "Reading the infrared/UTCI heat grid…",
      waitingOn: "the site",
      fact: heatQ.data
        ? `Hottest ${heatQ.data.utci_max_c.toFixed(0)}°C feels-like across the site`
        : undefined,
      tier: "GROUNDED" as const,
      state: stepState(heatQ, true, "utci_grid"),
    },
    {
      key: "crowd",
      label: "Predicting where crowds gather",
      detail: "Simulating festival-goers flowing to the stages…",
      waitingOn: "the heat map",
      fact: crowdQ.data ? `Crowds peak around the main stages (${crowdMax}/cell)` : undefined,
      tier: "ASSUMED" as const,
      state: stepState(crowdQ, heatQ.isSuccess, "crowd_grid"),
    },
    {
      key: "placement",
      label: "Choosing the best spots for shade",
      detail: "Crossing hot × busy to rank shade-priority zones…",
      waitingOn: "the crowd map",
      fact: zonesQ.data ? `${zonesQ.data.structures.length} hot, busy zones found` : undefined,
      tier: "ASSUMED" as const,
      state: stepState(zonesQ, crowdQ.isSuccess, "structure_zones"),
    },
  ];

  if (state.analyzing) {
    return (
      <AnalysisChecklist
        steps={steps}
        allDone={zonesQ.isSuccess}
        onContinue={() => dispatch({ type: "setAnalyzing", analyzing: false })}
      />
    );
  }

  return (
    <StageScaffold
      index="04 / SHADE"
      title="Where the shade goes"
      lede="Hot × busy. Accept the spots that protect the most people."
      cta={{
        label: "Clad these zones →",
        onClick: () => dispatch({ type: "setStage", stage: "materials" }),
        disabled: acceptedRanks.length === 0,
        disabledReason: "Accept at least one placement to continue.",
      }}
    >
      <div className="space-y-5">
        {/* Hero datum — one big number, tiny mono support. Scale contrast is the
            whole point (P2 "minimal, with big numbers"). Color is rationed: heat
            red only for the danger temperature; the protected figure reads in paper. */}
        {siteHottest !== null && zones.length > 0 && (
          <div className="pb-1">
            {acceptedRanks.length > 0 ? (
              <>
                <p className="text-label" style={{ color: "var(--grey)" }}>
                  CROWD IN DANGEROUS HEAT · NOW COVERED
                </p>
                <motion.p
                  key={pctShaded}
                  className="text-hero mt-1 tabular-nums leading-[0.9]"
                  style={{ color: "var(--paper)" }}
                  initial={reduce ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: DUR.card / 1000, ease: EASE.out }}
                >
                  {pctShaded}
                  <span className="text-display align-top" style={{ color: "var(--teal)" }}>
                    %
                  </span>
                </motion.p>
                <div
                  className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono text-[11px]"
                  style={{ color: "var(--grey)" }}
                >
                  <span>
                    <span className="tabular-nums font-medium" style={{ color: "var(--paper)" }}>
                      ~{peopleShaded.toLocaleString()}
                    </span>
                    {" / "}
                    {peopleInHeat.toLocaleString()} PEOPLE
                  </span>
                  {coolingC !== null && (
                    <span>
                      −
                      <span className="tabular-nums font-medium" style={{ color: "var(--paper)" }}>
                        {coolingC.toFixed(1)}
                      </span>
                      °C FEELS-LIKE
                    </span>
                  )}
                  <span>
                    ~€
                    <span className="tabular-nums font-medium" style={{ color: "var(--paper)" }}>
                      {costTotal.toLocaleString()}
                    </span>
                    {" · €"}
                    {costPerPerson}/PERSON
                  </span>
                </div>
              </>
            ) : (
              <>
                <p className="text-label" style={{ color: "var(--grey)" }}>
                  PEAK FEELS-LIKE · {bandFor(siteHottest).label.split(" (")[0].toUpperCase()}
                </p>
                <p
                  className="text-hero mt-1 tabular-nums leading-[0.9]"
                  style={{ color: "var(--heat)" }}
                >
                  {Math.round(siteHottest)}
                  <span className="text-display align-top">°C</span>
                </p>
                <p className="mt-2 font-mono text-[11px]" style={{ color: "var(--grey)" }}>
                  ~
                  <span className="tabular-nums font-medium" style={{ color: "var(--paper)" }}>
                    {peopleInHeat.toLocaleString()}
                  </span>{" "}
                  PEOPLE IN CAUTION-OR-WORSE HEAT · ACCEPT SPOTS TO SEE WHO YOU PROTECT
                </p>
              </>
            )}
          </div>
        )}

        {/* Engineering disclaimer */}
        <div
          className="flex items-start gap-2 px-3 py-2.5"
          style={{
            border: "1px solid color-mix(in srgb, var(--amber) 40%, transparent)",
            borderRadius: "var(--radius-sm)",
            background: "color-mix(in srgb, var(--amber) 8%, transparent)",
          }}
        >
          <ShieldAlt
            className="mt-0.5 size-4 shrink-0"
            style={{ color: "var(--amber)" }}
            strokeWidth={1.5}
          />
          <p className="font-mono text-[11px] leading-relaxed" style={{ color: "var(--paper)" }}>
            These placements are a climate-and-crowd decision aid. Any built structure requires
            sign-off by a licensed structural engineer and on-site safety review before
            construction.
          </p>
        </div>

        {loading && (
          <EmptyState
            title="Crossing crowd × heat for this site…"
            body="Ranking shade-priority zones from the heat field and crowd density."
          />
        )}

        {failed && (
          <div
            className="flex items-start gap-2 px-3 py-2.5"
            style={{
              border: "1px solid var(--red)",
              borderRadius: "var(--radius-sm)",
              background: "color-mix(in srgb, var(--red) 10%, transparent)",
            }}
          >
            <WarningTriangle
              className="mt-0.5 size-4 shrink-0"
              style={{ color: "var(--red)" }}
              strokeWidth={1.5}
            />
            <p className="font-mono text-[11px] leading-relaxed" style={{ color: "var(--paper)" }}>
              Placement output unavailable. No candidates shown rather than fabricated ones. Backend
              at :8000?
            </p>
          </div>
        )}

        {!loading && !failed && zones.length === 0 && (
          <EmptyState
            title="No shade priority found"
            body="No cell here is both hot and busy enough to justify a structure. An honest non-result — not a failure."
          />
        )}

        {zones.length > 0 && (
          <section>
            {/* Editorial masthead — the s8-ranked-list headline + a ruled column key */}
            <div
              className="flex items-baseline justify-between pb-2"
              style={{ borderBottom: "1.5px solid var(--paper)" }}
            >
              <h3 className="text-subhead leading-[0.95]" style={{ color: "var(--paper)" }}>
                Recommended
                <br />
                shade zones
              </h3>
              <span className="font-mono text-[10px] tabular-nums" style={{ color: "var(--grey)" }}>
                {acceptedRanks.length}/{zones.length} KEPT
              </span>
            </div>

            {/* Column header row — mono labels, ruled. Mirrors the reference table. */}
            <div
              className="grid items-center gap-3 py-1.5 font-mono text-[9px] tracking-[0.14em]"
              style={{
                gridTemplateColumns: "1.6rem 1fr auto",
                color: "var(--grey)",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <span>RANK</span>
              <span>WHY HERE?</span>
              <span className="text-right">COOLING</span>
            </div>

            {/* Ruled rows 01–05. Giant rank numeral, tiny mono captions, one accent. */}
            <ul>
              {(showAllZones ? zones : zones.slice(0, 5)).map((z, i) => {
                const accepted = acceptedRanks.includes(z.rank);
                const hovered = hoveredZone === z.rank;
                const danger = z.rank <= 2;
                const peak = zonePeak[z.rank];
                const crowdShare =
                  totalDemand > 0
                    ? Math.round((z.marginal_demand / totalDemand) * 100)
                    : Math.round(z.coverage_pct);
                // Accent: accepted = green; the danger zones carry a heat tick; the rest
                // are quiet paper. Color stays earned (P5).
                const numColor = accepted
                  ? "var(--green2)"
                  : danger
                    ? "var(--heat)"
                    : "var(--grey)";

                return (
                  <motion.li
                    key={z.rank}
                    onMouseEnter={() => dispatch({ type: "setHoveredZone", rank: z.rank })}
                    onMouseLeave={() => dispatch({ type: "setHoveredZone", rank: null })}
                    className="grid items-center gap-3 transition-colors"
                    initial={reduce ? false : { opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{
                      duration: DUR.card / 1000,
                      ease: EASE.out,
                      delay: Math.min(i, 5) * 0.05,
                    }}
                    style={{
                      gridTemplateColumns: "1.6rem 1fr auto",
                      borderBottom: "1px solid var(--border)",
                      paddingTop: "0.85rem",
                      paddingBottom: "0.85rem",
                      background: hovered
                        ? "color-mix(in srgb, var(--paper) 5%, transparent)"
                        : "transparent",
                    }}
                  >
                    {/* RANK — giant mono numeral, the play-with-size move */}
                    <span
                      className="font-mono font-bold tabular-nums leading-none"
                      style={{ color: numColor, fontSize: "1.45rem" }}
                    >
                      {String(z.rank).padStart(2, "0")}
                    </span>

                    {/* WHY HERE? — peak feels-like is the hard datum (no footprint shown) */}
                    <div className="min-w-0">
                      {peak !== undefined && (
                        <div className="flex items-baseline gap-2">
                          <span
                            className="font-mono text-[13px] tabular-nums font-medium"
                            style={{ color: "var(--heat)" }}
                          >
                            {Math.round(peak)}°C
                          </span>
                          <span
                            className="font-mono text-[10px] uppercase tracking-[0.06em]"
                            style={{ color: "var(--grey)" }}
                          >
                            peak feels-like
                          </span>
                        </div>
                      )}
                      <p
                        className="mt-0.5 truncate font-mono text-[10px] tracking-[0.04em] uppercase"
                        style={{ color: "var(--grey)" }}
                      >
                        {whyHere(z.rank, peak)}
                        {zoneName(z) && <span> · {zoneName(z)}</span>}
                      </p>
                      <p className="mt-0.5 font-mono text-[10px]" style={{ color: "var(--grey)" }}>
                        SHADES ~
                        <span className="tabular-nums" style={{ color: "var(--paper)" }}>
                          {Math.round(z.marginal_demand).toLocaleString()}
                        </span>{" "}
                        MORE ·{" "}
                        <span className="tabular-nums" style={{ color: "var(--paper)" }}>
                          {crowdShare}%
                        </span>{" "}
                        OF CROWD
                      </p>
                    </div>

                    {/* EXPECTED COOLING + the accept control, right-aligned */}
                    <div className="flex flex-col items-end gap-1.5">
                      <span
                        className="font-mono text-[13px] tabular-nums font-medium"
                        style={{ color: accepted ? "var(--green2)" : "var(--teal)" }}
                      >
                        {coolingC !== null ? `−${coolingC.toFixed(1)}°C` : "—"}
                      </span>
                      <button
                        type="button"
                        onClick={() => dispatch({ type: "toggleAccept", rank: z.rank })}
                        aria-label={accepted ? `Dismiss zone ${z.rank}` : `Accept zone ${z.rank}`}
                        aria-pressed={accepted}
                        className="flex h-7 items-center justify-center gap-1 px-2.5 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] transition-colors"
                        style={{
                          background: accepted ? "var(--green)" : "transparent",
                          color: accepted ? "var(--white)" : "var(--green2)",
                          border: `1px solid ${accepted ? "var(--green)" : "color-mix(in srgb, var(--green2) 55%, transparent)"}`,
                          borderRadius: "var(--radius-sm)",
                        }}
                      >
                        {accepted ? (
                          <>
                            <Check className="size-3" strokeWidth={2.6} />
                            Kept
                          </>
                        ) : (
                          <>
                            <Plus className="size-3" strokeWidth={2.4} />
                            Keep
                          </>
                        )}
                      </button>
                    </div>
                  </motion.li>
                );
              })}
            </ul>

            {zones.length > 5 && (
              <button
                type="button"
                onClick={() => setShowAllZones((v) => !v)}
                className="w-full py-2.5 font-mono text-[10px] tracking-[0.08em] uppercase transition-opacity hover:opacity-70"
                style={{ color: "var(--grey)" }}
              >
                {showAllZones ? "Show top five" : `+ ${zones.length - 5} more zones`}
              </button>
            )}
          </section>
        )}
      </div>
    </StageScaffold>
  );
}
