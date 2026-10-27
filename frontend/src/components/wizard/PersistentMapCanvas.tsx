import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import Map, { useControl, type MapRef } from "react-map-gl/mapbox";
import type { LngLatBounds } from "mapbox-gl";
import { MapboxOverlay, type MapboxOverlayProps } from "@deck.gl/mapbox";
import type { Layer } from "@deck.gl/core";
import type { LayerRow } from "./LayerToggle";
import "mapbox-gl/dist/mapbox-gl.css";

/**
 * The single persistent Mapbox canvas (UI-SPEC P1) — mounted ONCE, survives the
 * whole Site→Materials→Placement→Handoff journey. Split in two so the right-side
 * stage panels (which live OUTSIDE the <Map>) can still push deck.gl layers:
 *
 *   <MapProvider>            ← holds mapRef + bounds + layer state, wraps the shell
 *      <WizardRail/>
 *      <MapCanvas>…</MapCanvas>   ← the one <Map> + deck.gl overlay; in-map controls as children
 *      <SidePanel>{stages}</SidePanel>   ← stages call useMapCanvas().setLayers(...)
 *   </MapProvider>
 *
 * Field rendering is the deck.gl overlay path (heat/crowd/bivariate + ranked
 * footprints) — never a naive additive double-overlay (UI-SPEC §4.2).
 */

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined;
/** Dark cartographic base so data layers read on top (UI-SPEC §2.7). */
const MAP_STYLE = "mapbox://styles/mapbox/dark-v11";
/** Parc del Fòrum, Barcelona — fixture demo center (engine is site-general). */
const INITIAL_VIEW = { longitude: 2.2275, latitude: 41.4065, zoom: 15.4 };

export type LayerUI = { rows: LayerRow[]; onToggle: (id: string) => void };

type MapCtx = {
  mapRef: React.RefObject<MapRef | null>;
  bounds: LngLatBounds | null;
  setBounds: (b: LngLatBounds | null) => void;
  /** Always-on context layers (festival schema) — drawn UNDER stage layers. */
  baseLayers: Layer[];
  setBaseLayers: (layers: Layer[]) => void;
  layers: Layer[];
  setLayers: (layers: Layer[]) => void;
  /** The active stage publishes its LayerToggle rows here; the shell renders them. */
  layerUI: LayerUI;
  setLayerUI: (ui: LayerUI) => void;
};

const Ctx = createContext<MapCtx | null>(null);

export function useMapCanvas() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useMapCanvas outside MapProvider");
  return v;
}

const EMPTY_UI: LayerUI = { rows: [], onToggle: () => {} };

export function MapProvider({ children }: { children: ReactNode }) {
  const mapRef = useRef<MapRef | null>(null);
  const [bounds, setBounds] = useState<LngLatBounds | null>(null);
  const [baseLayers, setBaseLayers] = useState<Layer[]>([]);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [layerUI, setLayerUI] = useState<LayerUI>(EMPTY_UI);
  return (
    <Ctx.Provider
      value={{ mapRef, bounds, setBounds, baseLayers, setBaseLayers, layers, setLayers, layerUI, setLayerUI }}
    >
      {children}
    </Ctx.Provider>
  );
}

/** UTCI → plain heat-stress band label (mirrors UTCI_BANDS; inline to keep the
 *  overlay free of placement-stage imports). */
function heatBand(c: number): string {
  if (c < 26) return "Comfortable";
  if (c < 32) return "Caution";
  if (c < 38) return "Dangerous";
  if (c < 46) return "Severe";
  return "Emergency";
}

/** Click/hover-to-inspect any cell (Forma pattern) — the recommendation is
 *  auditable, not a black-box blob. Branches on the picked layer id. */
function inspectTooltip(info: { object?: unknown; layer?: { id?: string } | null }) {
  const o = info.object as Record<string, unknown> | undefined;
  if (!o) return null;
  const id = info.layer?.id ?? "";
  let body: string | null = null;
  if (id === "heat" && typeof o.utci_c === "number")
    body = `${Math.round(o.utci_c)}°C feels-like · ${heatBand(o.utci_c)}`;
  else if (id === "crowd" && typeof o.density === "number")
    body = `${Math.round(o.density)} people here`;
  else if (id === "zones" && typeof o.rank === "number")
    body = `Shade spot #${o.rank} · ${Math.round((o.coverage_pct as number) ?? 0)}% crowd cover`;
  else if (id.startsWith("material") && typeof o.name === "string")
    body = String(o.name);
  else if ((id === "schema-stages" || id === "schema-entries") && typeof o.name === "string")
    body = String(o.name);
  if (!body) return null;
  return {
    text: body,
    style: {
      background: "rgba(10,10,10,0.9)",
      color: "#F2F0ED",
      fontSize: "11px",
      fontFamily: "IBM Plex Mono, monospace",
      padding: "4px 7px",
      borderRadius: "4px",
    },
  };
}

/** deck.gl overlay wired through react-map-gl's useControl (shares the GL context). */
function DeckOverlay(props: MapboxOverlayProps) {
  // Overlaid mode (not interleaved): deck renders in its own canvas above the
  // basemap — more reliable for TextLayer/SDF labels than interleaving into GL.
  const overlay = useControl<MapboxOverlay>(
    () => new MapboxOverlay({ ...props, interleaved: false, getTooltip: inspectTooltip }),
  );
  overlay.setProps({ ...props, getTooltip: inspectTooltip });
  return null;
}

export function MapCanvas({ children }: { children?: ReactNode }) {
  const { mapRef, setBounds, baseLayers, layers } = useMapCanvas();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  useEffect(() => {
    if (!mounted) return;
    const id = setTimeout(() => {
      mapRef.current?.resize();
      // a11y (P0): the deck.gl overlay canvas is a nameless, no-op tab stop — take
      // it out of the tab order + hide from AT (it's a decorative overlay; the
      // ranked side list is the accessible path to every placement).
      document.querySelectorAll<HTMLCanvasElement>("#deckgl-overlay, .deck-canvas").forEach((c) => {
        c.setAttribute("tabindex", "-1");
        c.setAttribute("aria-hidden", "true");
      });
    }, 300);
    return () => clearTimeout(id);
  }, [mounted, mapRef]);

  function emitBounds() {
    const m = mapRef.current;
    setBounds(m ? (m.getBounds() as LngLatBounds | null) : null);
  }

  if (!mounted) {
    return (
      <div className="absolute inset-0 flex items-center justify-center bg-surface-sunken">
        <span className="font-mono text-xs text-text-muted">Loading site basemap…</span>
      </div>
    );
  }
  if (!MAPBOX_TOKEN) {
    return (
      <div className="absolute inset-0 flex items-center justify-center bg-surface-sunken p-6">
        <p className="max-w-xs text-center font-mono text-xs text-destructive">
          Missing VITE_MAPBOX_TOKEN — add a public, URL-restricted Mapbox token to
          frontend/.env.local (see .env.example). Never hardcode it.
        </p>
      </div>
    );
  }

  return (
    <div className="absolute inset-0">
      <Map
        ref={mapRef}
        mapboxAccessToken={MAPBOX_TOKEN}
        mapStyle={MAP_STYLE}
        initialViewState={INITIAL_VIEW}
        preserveDrawingBuffer
        attributionControl={false}
        onLoad={() => {
          mapRef.current?.resize();
          emitBounds();
        }}
        onMoveEnd={emitBounds}
        style={{ width: "100%", height: "100%" }}
      >
        <DeckOverlay layers={[...baseLayers, ...layers]} />
        {children}
      </Map>
    </div>
  );
}
