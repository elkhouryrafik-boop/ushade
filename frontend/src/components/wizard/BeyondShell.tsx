import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Marker } from "react-map-gl/mapbox";
import { ScatterplotLayer, PolygonLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { motion } from "framer-motion";
import { Check, MapPin, ArrowLeft, GridMinus, SunLight } from "iconoir-react";
import { MapProvider, MapCanvas, useMapCanvas } from "./PersistentMapCanvas";
import { DaytimeField } from "./DaytimeField";
import { ScenarioPlacementPanel } from "./ScenarioPlacementPanel";
import { PixelMark } from "./PixelMark";
import { hexToRgb, PALETTE } from "@/lib/tokens";
import { EASE } from "@/lib/motion";
import type { Scenario, ScenarioData, ScenarioAttractor, ScenarioZone } from "@/lib/scenarios";

/**
 * BeyondShell — the "Beyond Festivals" scenario workspace.
 *
 * A PARALLEL shell to the festival WizardShell: same persistent Mapbox canvas + the
 * same signature DaytimeField (heat × crowd over a day-timeline) + the same editorial
 * ranked-shade panel — but driven entirely by a synthetic scenario dataset and its own
 * LOCAL state. It deliberately reuses the heavy primitives (MapCanvas, DaytimeField,
 * StageScaffold) while touching NONE of the festival's backend-coupled stages, so the
 * festival flow is provably unaffected.
 */

const AMBER = hexToRgb(PALETTE.amber);
const GREEN2 = hexToRgb(PALETTE.green2);
const GREY = hexToRgb(PALETTE.grey);
const PAPER = hexToRgb(PALETTE.paper);
const INK = hexToRgb(PALETTE.ink);
const GREEN = hexToRgb(PALETTE.green);
const RED = hexToRgb(PALETTE.red);

const STAGE_KINDS = new Set(["stage"]);
const ENTRY_KINDS = new Set(["entrance", "exit"]);

/** Attractor dots — same register as the festival schema layers (stages = amber crowd
 *  magnets, entrances = green sources, amenities = faint grey). */
function attractorLayers(attractors: ScenarioAttractor[]): Layer[] {
  const stages = attractors.filter((a) => STAGE_KINDS.has(a.kind));
  const entries = attractors.filter((a) => ENTRY_KINDS.has(a.kind));
  const amenities = attractors.filter((a) => !STAGE_KINDS.has(a.kind) && !ENTRY_KINDS.has(a.kind));
  return [
    new ScatterplotLayer<ScenarioAttractor>({
      id: "scn-amenities",
      data: amenities,
      getPosition: (d) => [d.lon, d.lat],
      getFillColor: [...GREY, 150],
      radiusUnits: "pixels",
      getRadius: 3,
    }),
    new ScatterplotLayer<ScenarioAttractor>({
      id: "scn-entries",
      data: entries,
      getPosition: (d) => [d.lon, d.lat],
      getFillColor: [...GREEN2, 230],
      getLineColor: [...PAPER, 230],
      lineWidthMinPixels: 1.5,
      stroked: true,
      radiusUnits: "pixels",
      getRadius: 5,
    }),
    new ScatterplotLayer<ScenarioAttractor>({
      id: "scn-stages",
      data: stages,
      getPosition: (d) => [d.lon, d.lat],
      getFillColor: [...AMBER, 240],
      getLineColor: [...INK, 220],
      lineWidthMinPixels: 1.5,
      stroked: true,
      radiusUnits: "pixels",
      getRadius: 7,
    }),
  ];
}

function priorityColor(rank: number): [number, number, number] {
  if (rank <= 2) return RED;
  if (rank === 3) return [...AMBER] as [number, number, number];
  return GREEN2;
}

/** Ranked footprint polygons (the accept surface), coloured like PlacementStage. */
function zonePolys(zones: ScenarioZone[], accepted: number[], hovered: number | null): Layer[] {
  return [
    new PolygonLayer<ScenarioZone>({
      id: "scn-zones",
      data: zones,
      getPolygon: (d) => d.footprint,
      getFillColor: (d) =>
        accepted.includes(d.rank)
          ? [...GREEN, 190]
          : [...priorityColor(d.rank), hovered === d.rank ? 150 : 95],
      getLineColor: (d) => (accepted.includes(d.rank) ? [...GREEN, 255] : [245, 245, 245, 255]),
      getLineWidth: (d) => (hovered === d.rank ? 5 : accepted.includes(d.rank) ? 4 : 2),
      lineWidthUnits: "pixels",
      stroked: true,
      filled: true,
      parameters: { depthCompare: "always" },
      updateTriggers: { getFillColor: [accepted, hovered], getLineWidth: [accepted, hovered] },
    }),
  ];
}

/** HTML name labels for the attractors (leader-lined map callouts, like SchemaLabels). */
function ScenarioLabels({ attractors }: { attractors: ScenarioAttractor[] }) {
  return (
    <>
      {attractors.map((p, i) => {
        const isStage = STAGE_KINDS.has(p.kind);
        const isEntry = ENTRY_KINDS.has(p.kind);
        const cue = isStage ? "var(--amber)" : isEntry ? "var(--green2)" : "var(--grey)";
        return (
          <Marker key={`${p.name}-${i}`} longitude={p.lon} latitude={p.lat} anchor="left">
            <span className="pointer-events-none flex select-none items-center">
              <span
                aria-hidden
                style={{
                  width: isStage ? 6 : 5,
                  height: isStage ? 6 : 5,
                  borderRadius: 9,
                  background: cue,
                  flexShrink: 0,
                  boxShadow: `0 0 0 2px color-mix(in srgb, ${cue} 22%, transparent)`,
                }}
              />
              <span aria-hidden style={{ width: 14, height: 1, flexShrink: 0, background: `color-mix(in srgb, ${cue} 55%, transparent)` }} />
              <span
                className="whitespace-nowrap font-mono uppercase leading-none"
                style={{
                  background: "color-mix(in srgb, var(--black) 86%, transparent)",
                  color: isStage ? "var(--paper)" : isEntry ? "var(--green2)" : "var(--grey)",
                  fontSize: isStage ? 9.5 : 8.5,
                  fontWeight: isStage ? 600 : 500,
                  letterSpacing: "0.13em",
                  padding: isStage ? "3px 6px" : "2.5px 5px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid color-mix(in srgb, var(--grey) 22%, transparent)",
                  boxShadow: "0 1px 5px rgba(0,0,0,0.5)",
                  backdropFilter: "blur(2px)",
                }}
              >
                {p.name}
              </span>
            </span>
          </Marker>
        );
      })}
    </>
  );
}

/** Numbered rank chips on the map (accept surface, cross-highlights with the panel). */
function ScenarioZoneMarkers({
  zones,
  accepted,
  hovered,
  onToggle,
  onHover,
}: {
  zones: ScenarioZone[];
  accepted: number[];
  hovered: number | null;
  onToggle: (rank: number) => void;
  onHover: (rank: number | null) => void;
}) {
  return (
    <>
      {zones.map((z) => {
        const isAccepted = accepted.includes(z.rank);
        const hot = hovered === z.rank;
        const danger = z.rank <= 2 && !isAccepted;
        const base = z.rank === 1 ? 30 : z.rank === 2 ? 27 : 24;
        const size = hot ? base + 5 : base;
        const bg = isAccepted ? PALETTE.green : danger ? PALETTE.heat : PALETTE.ink;
        const ring = isAccepted ? PALETTE.green2 : danger ? PALETTE.heat : "rgba(242,240,237,0.55)";
        return (
          <Marker key={z.rank} longitude={z.center[0]} latitude={z.center[1]} anchor="center">
            <button
              type="button"
              onClick={() => onToggle(z.rank)}
              onMouseEnter={() => onHover(z.rank)}
              onMouseLeave={() => onHover(null)}
              aria-label={`Shade spot rank ${z.rank}${isAccepted ? ", kept" : ""}`}
              aria-pressed={isAccepted}
              className="relative flex items-center justify-center font-mono font-bold transition-all duration-150"
              style={{
                width: size,
                height: size,
                background: bg,
                color: "#FFFFFF",
                borderRadius: "999px",
                border: `1.5px solid ${hot ? "#FFFFFF" : ring}`,
                fontSize: hot ? base / 2 + 1 : z.rank === 1 ? 14 : 12,
                lineHeight: 1,
                boxShadow: hot
                  ? `0 0 0 4px color-mix(in srgb, ${bg} 30%, transparent), 0 4px 14px rgba(0,0,0,0.7)`
                  : danger
                    ? "0 2px 10px rgba(0,0,0,0.65)"
                    : "0 1px 6px rgba(0,0,0,0.6)",
                cursor: "pointer",
              }}
            >
              {isAccepted ? <Check width={size * 0.55} height={size * 0.55} strokeWidth={2.6} /> : z.rank}
            </button>
          </Marker>
        );
      })}
    </>
  );
}

/** Slim scenario rail — a static visual echo of the festival rail (Site → Timeline →
 *  Shade), with a Back door. No gating; this is a single-screen concept view. */
function BeyondRail({ onExit }: { onExit: () => void }) {
  const items = [
    { label: "Site", icon: MapPin },
    { label: "Daytime", icon: SunLight },
    { label: "Shade", icon: GridMinus, active: true },
  ];
  return (
    <nav
      aria-label="Scenario stages"
      className="flex h-full w-16 shrink-0 flex-col"
      style={{ background: "var(--ink)", borderRight: "1px solid color-mix(in srgb, var(--paper) 15%, transparent)" }}
    >
      <button
        type="button"
        onClick={onExit}
        aria-label="Back to welcome"
        className="flex h-14 flex-col items-center justify-center gap-1.5 border-b transition-colors hover:bg-white/5"
        style={{ borderColor: "color-mix(in srgb, var(--paper) 12%, transparent)" }}
      >
        <ArrowLeft className="size-4" style={{ color: "var(--paper)" }} strokeWidth={1.6} />
        <PixelMark tone="paper" cell={3} gap={1.5} />
      </button>
      <ol className="flex flex-1 flex-col items-center gap-1 py-3">
        {items.map((it, i) => {
          const Icon = it.icon;
          return (
            <li key={i} className="w-full">
              <div
                className="relative flex w-full flex-col items-center gap-0.5 py-2.5"
                style={it.active ? { borderLeft: "2px solid var(--green)" } : { borderLeft: "2px solid transparent" }}
              >
                <Icon className="size-5" style={{ color: it.active ? "var(--paper)" : "var(--grey)" }} strokeWidth={1.5} />
                <span className="font-mono text-[9px] font-semibold" style={{ color: it.active ? "var(--grey)" : "color-mix(in srgb, var(--grey) 50%, transparent)" }}>
                  {pad(i + 1)}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
const pad = (n: number) => String(n).padStart(2, "0");

function ScenarioInner({ scenario, onExit }: { scenario: Scenario; onExit: () => void }) {
  const { setBaseLayers, setLayers, mapRef } = useMapCanvas();
  const [accepted, setAccepted] = useState<number[]>([]);
  const [hovered, setHovered] = useState<number | null>(null);

  const { data } = useQuery({
    queryKey: ["scenario", scenario.id],
    queryFn: async () => {
      const res = await fetch(scenario.animUrl);
      if (!res.ok) throw new Error(`scenario ${scenario.id} not found`);
      return (await res.json()) as ScenarioData;
    },
    staleTime: Infinity,
  });

  // Dark thermal well for the whole scenario view (placement-like), restored on exit.
  useEffect(() => {
    document.documentElement.dataset.theme = "dark";
    return () => {
      document.documentElement.dataset.theme = "light";
    };
  }, []);

  // Publish attractor context + ranked footprints onto the shared map overlay.
  useEffect(() => {
    if (!data) return;
    setBaseLayers(attractorLayers(data.attractors));
  }, [data, setBaseLayers]);
  useEffect(() => {
    if (!data) return;
    setLayers(zonePolys(data.zones, accepted, hovered));
  }, [data, accepted, hovered, setLayers]);

  // Jump the basemap to the scenario site once the map instance exists (avoids a
  // Fòrum flash). Polls briefly for mapRef, then settles.
  useEffect(() => {
    if (!data) return;
    let tries = 0;
    const id = setInterval(() => {
      const m = mapRef.current;
      if (m) {
        m.jumpTo({ center: data.center, zoom: data.zoom });
        clearInterval(id);
      } else if (++tries > 40) {
        clearInterval(id);
      }
    }, 100);
    return () => clearInterval(id);
  }, [data, mapRef]);

  const toggle = (rank: number) =>
    setAccepted((a) => (a.includes(rank) ? a.filter((r) => r !== rank) : [...a, rank]));

  return (
    <div className="flex h-screen w-full overflow-hidden" style={{ background: "var(--bg)", color: "var(--text-primary)" }}>
      <BeyondRail onExit={onExit} />
      <div className="relative flex min-w-0 flex-1">
        {/* Map column */}
        <div className="relative min-w-0 flex-1">
          <MapCanvas>
            {data && <DaytimeField bounds={data.bounds} animData={data} clockLabel={data.clockLabel} />}
            {data && <ScenarioLabels attractors={data.attractors} />}
            {data && (
              <ScenarioZoneMarkers zones={data.zones} accepted={accepted} hovered={hovered} onToggle={toggle} onHover={setHovered} />
            )}
          </MapCanvas>

          {/* Site chip (top-left) */}
          <div
            className="pointer-events-none absolute left-4 top-4 z-20 flex items-center gap-2 px-3 py-2 backdrop-blur"
            style={{
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              background: "color-mix(in srgb, var(--surface) 90%, transparent)",
            }}
          >
            <MapPin className="size-3.5 shrink-0" style={{ color: "var(--teal)" }} strokeWidth={1.5} />
            <span className="font-mono text-xs" style={{ color: "var(--text-primary)" }}>
              {scenario.site}
            </span>
          </div>

          {/* "Beyond Festivals" badge (top-right) */}
          <div
            className="absolute right-4 top-4 z-20 flex items-center gap-2 px-3 py-2"
            style={{
              border: "1px solid color-mix(in srgb, var(--teal) 45%, transparent)",
              borderRadius: "var(--radius-sm)",
              background: "color-mix(in srgb, var(--black) 60%, transparent)",
              backdropFilter: "blur(8px)",
            }}
          >
            <span className="font-mono text-[10px] uppercase tracking-[0.16em]" style={{ color: "var(--teal)" }}>
              Beyond Festivals · {scenario.label}
            </span>
          </div>
        </div>

        {/* Aside — the scenario placement panel */}
        <aside
          aria-label="Scenario controls"
          className="flex w-[400px] shrink-0 flex-col"
          style={{ borderLeft: "1px solid var(--border)", background: "var(--bg)" }}
        >
          <motion.div
            key={scenario.id}
            className="flex min-h-0 flex-1 flex-col"
            initial={{ opacity: 0, x: 18 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.34, ease: EASE.out }}
          >
            {data ? (
              <ScenarioPlacementPanel
                scenario={scenario}
                data={data}
                accepted={accepted}
                hovered={hovered}
                onToggle={toggle}
                onHover={setHovered}
              />
            ) : (
              <div className="flex h-full items-center justify-center">
                <span className="font-mono text-xs" style={{ color: "var(--grey)" }}>
                  preparing the day…
                </span>
              </div>
            )}
          </motion.div>
        </aside>
      </div>
    </div>
  );
}

export function BeyondShell({ scenario, onExit }: { scenario: Scenario; onExit: () => void }) {
  // Keyed remount per scenario so switching domains fully resets local state + map.
  return useMemo(
    () => (
      <MapProvider>
        <ScenarioInner scenario={scenario} onExit={onExit} />
      </MapProvider>
    ),
    [scenario, onExit],
  );
}
