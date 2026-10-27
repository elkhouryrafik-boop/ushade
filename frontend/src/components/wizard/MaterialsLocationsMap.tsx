import { useEffect, useMemo, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import type { MaterialItem } from "@/lib/materials-provider";
import { PALETTE } from "@/lib/tokens";
import { Pin } from "iconoir-react";

/**
 * MaterialsLocationsMap — the Airbnb-style RIGHT pane.
 *
 * A SELF-CONTAINED Mapbox GL JS instance (its own `mapboxgl.Map`, NOT the shared
 * PersistentMapCanvas / deck.gl overlay) that drops one pin per reclaimed-material
 * source around Parc del Fòrum, placed by each item's true `lonLat`. The site itself
 * is a glowing teal hub at the Fòrum centroid.
 *
 * Cross-highlight is bidirectional, Airbnb-style: hovering a card on the left
 * enlarges + lifts its pin here (driven by `hoveredId`); hovering a pin here calls
 * `onHover` so the matching card highlights. Recommended picks read ORANGE (the brand
 * accent, `--green2`) with a rank chip; reference/non-recommended sources read a quieter
 * teal so the picks pop but everything stays legible on the dark basemap.
 *
 * FRAMING: the Fòrum sits on the coast, so a symmetric fit leaves half the frame as
 * empty dark sea. We bias the camera INLAND (north-west) — the populated cluster is
 * always toward the city — with asymmetric padding so the data fills the view and the
 * sea is pushed to the edge. Far pins still render and stay pannable.
 *
 * Dark map style (`mapbox/dark-v11`) per the dark theme. The token is the SAME env
 * var the rest of the app uses (`VITE_MAPBOX_TOKEN`); missing → an honest message.
 * The map instance is fully cleaned up on unmount and the load is awaited before any
 * marker work so nothing churns or leaks.
 */

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined;
const MAP_STYLE = "mapbox://styles/mapbox/dark-v11";
/** Parc del Fòrum, Barcelona — the hub the sources orbit. */
const FORUM_CENTER: [number, number] = [2.2275, 41.4065];

interface MaterialsLocationsMapProps {
  items: MaterialItem[];
  /** Center the map (drawn-boundary centroid or the Fòrum default). */
  siteCenter?: [number, number];
  /** Ids of the recommended 3–5 — these pins read accented + carry a rank chip. */
  recommendedIds?: Set<string>;
  /** id → rank (1-based) among the recommended shortlist, for the pin chip. */
  rankById?: Map<string, number>;
  /** Currently cross-highlighted card/pin (from card hover or pin hover). */
  hoveredId?: string | null;
  onHover?: (id: string | null) => void;
}

interface PinRecord {
  el: HTMLButtonElement;
  marker: mapboxgl.Marker;
  recommended: boolean;
}

export function MaterialsLocationsMap({
  items,
  siteCenter,
  recommendedIds,
  rankById,
  hoveredId,
  onHover,
}: MaterialsLocationsMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const pinsRef = useRef<Map<string, PinRecord>>(new Map());
  const siteMarkerRef = useRef<mapboxgl.Marker | null>(null);
  const [ready, setReady] = useState(false);

  // Latest onHover without forcing the marker effect to re-run on every parent render.
  const onHoverRef = useRef(onHover);
  onHoverRef.current = onHover;

  const center = siteCenter ?? FORUM_CENTER;
  // Keep the live center in a ref so the create-once effect never reads a stale value.
  const centerRef = useRef(center);
  centerRef.current = center;

  // Only the geolocated items get pins.
  const geoItems = useMemo(() => items.filter((m) => m.lonLat), [items]);

  // ── 1 · Create the map ONCE — but only AFTER the container has real height. ──
  // The map mounts inside the document "rise" animation, so on the first frame the
  // flex pane can still be collapsed (≈0–46px). Mapbox bakes the container size into
  // its projection transform AT CREATION and a later resize() does NOT fully recover
  // it — the result is a map that only paints a top sliver (looks like a black screen).
  // So we WAIT for clientHeight to settle, then create. This is the real fix.
  useEffect(() => {
    if (!MAPBOX_TOKEN || !containerRef.current) return;
    mapboxgl.accessToken = MAPBOX_TOKEN;
    const container = containerRef.current;

    let map: mapboxgl.Map | null = null;
    let ro: ResizeObserver | null = null;
    let settleTimer: ReturnType<typeof setTimeout> | undefined;

    const onLoad = (m: mapboxgl.Map) => {
      // Parc del Fòrum is coastal — on the default dark-v11 the Mediterranean renders
      // near-black, so a sea-heavy frame reads as "broken/black". Recolor water + land
      // to distinguishable dark tones so the frame always reads as an actual map.
      const trySet = (layer: string, prop: string, val: string) => {
        try {
          if (m.getLayer(layer)) m.setPaintProperty(layer, prop, val);
        } catch {
          /* layer not in this style version — ignore */
        }
      };
      trySet("water", "fill-color", "#13202b"); // visible dark slate-blue sea
      trySet("land", "background-color", "#0b0d11");
      m.resize();
      setReady(true);
    };

    const createMap = () => {
      if (map) return;
      const created = new mapboxgl.Map({
        container,
        style: MAP_STYLE,
        center: centerRef.current,
        zoom: 12.6,
        attributionControl: false,
        dragRotate: false,
        pitchWithRotate: false,
      });
      map = created;
      mapRef.current = created;
      created.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "bottom-right");
      created.on("load", () => onLoad(created));
      // After creation, keep the GL canvas synced to any further container resizes.
      ro = new ResizeObserver(() => created.resize());
      ro.observe(container);
    };

    // Create now if the container already has real height; otherwise WAIT for the rise
    // animation to give it height (observe until clientHeight settles), then create once.
    if (container.clientHeight > 120) {
      createMap();
    } else {
      const waitRo = new ResizeObserver(() => {
        if (container.clientHeight > 120) {
          waitRo.disconnect();
          createMap();
        }
      });
      waitRo.observe(container);
      // Fallback: create after the rise settles even if RO never reports >120 (e.g. reduced motion).
      settleTimer = setTimeout(() => {
        waitRo.disconnect();
        createMap();
      }, 500);
    }

    return () => {
      clearTimeout(settleTimer);
      ro?.disconnect();
      pinsRef.current.forEach((p) => p.marker.remove());
      pinsRef.current.clear();
      siteMarkerRef.current?.remove();
      siteMarkerRef.current = null;
      map?.remove();
      map = null;
      mapRef.current = null;
      setReady(false);
    };
    // Created once; recenters/fits are handled by the marker + fit effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── 2 · Site hub marker (once map is ready / when center changes). ──────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    siteMarkerRef.current?.remove();
    const el = document.createElement("div");
    el.className = "mlm-site";
    el.setAttribute("aria-hidden", "true");
    // Label sits ABOVE the hub so it never disappears under a source pin (pins anchor
    // bottom, i.e. they grow upward from their point — keeping the label up clears them).
    el.innerHTML = `<span class="mlm-site-label">SITE</span><span class="mlm-site-core"></span><span class="mlm-site-pulse"></span>`;
    const marker = new mapboxgl.Marker({ element: el, anchor: "center" })
      .setLngLat(center)
      .addTo(map);
    siteMarkerRef.current = marker;
  }, [ready, center]);

  // ── 3 · Source pins — rebuild when the geo items / recommendation set change. ─
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    // Fully clear existing pins before re-adding so re-renders never double markers.
    pinsRef.current.forEach((p) => p.marker.remove());
    pinsRef.current.clear();

    // Only the CLOSE cluster informs framing. Catalogue sources span Catalonia (10–80 km),
    // and the Fòrum sits on the coast — fitting scattered sources zooms out to a regional
    // smear that's mostly sea (reads as a black screen). Instead we sit on the site at a
    // readable city zoom; far pins still render and stay pannable.
    const nearCluster = geoItems.filter((m) => (m.distanceKm ?? 999) <= 5);

    geoItems.forEach((m) => {
      const recommended = !!recommendedIds?.has(m.id);
      const rank = rankById?.get(m.id);

      // Mapbox writes `transform: translate(...)` onto the marker's ROOT element every
      // frame to position it. So the root must be a bare wrapper with NO transform
      // transition — otherwise the pin ANIMATES toward each new position on pan/zoom/fit
      // (drifts, briefly lands in the sea, "glitches"). The button (with its hover-lift
      // transition) lives INSIDE the wrapper, fully isolated from Mapbox's positioning.
      const root = document.createElement("div");
      root.className = "mlm-pin-wrap";

      const el = document.createElement("button");
      el.type = "button";
      el.className = `mlm-pin${recommended ? " mlm-pin--rec" : ""}`;
      el.setAttribute(
        "aria-label",
        `${m.name}${m.distanceKm != null ? ` — ${Math.round(m.distanceKm * 10) / 10} km from site` : ""}`,
      );
      el.innerHTML = `
        <span class="mlm-pin-dot"></span>
        ${rank != null ? `<span class="mlm-pin-rank">${rank}</span>` : ""}
        <span class="mlm-pin-tip">
          <span class="mlm-pin-tip-name">${escapeHtml(m.name)}</span>
          <span class="mlm-pin-tip-meta">${
            m.distanceKm != null ? `${Math.round(m.distanceKm * 10) / 10} km` : "distance n/a"
          } · ${m.type === "struct" ? "Structural" : "Membrane"}</span>
        </span>`;

      // Raise this marker above its neighbours while interacting so overlapping pins
      // never fully hide each other and the tooltip is never occluded.
      const raise = () => {
        el.parentElement && (el.parentElement.style.zIndex = "6");
        onHoverRef.current?.(m.id);
      };
      const lower = () => {
        el.parentElement && (el.parentElement.style.zIndex = "");
        onHoverRef.current?.(null);
      };
      el.addEventListener("mouseenter", raise);
      el.addEventListener("mouseleave", lower);
      el.addEventListener("focus", raise);
      el.addEventListener("blur", lower);

      root.appendChild(el);
      const marker = new mapboxgl.Marker({ element: root, anchor: "bottom" })
        .setLngLat(m.lonLat)
        .addTo(map);

      // `el.parentElement` is now the wrapper Mapbox positions — raising its z-index
      // (in raise()/lower() and the cross-highlight effect) lifts THIS pin only.
      pinsRef.current.set(m.id, { el, marker, recommended });
    });

    // Site-centred city view, biased INLAND (north-west) so the city fills the frame and
    // the sea sits low. If a tight cluster of sources is right here, fit to it; otherwise
    // sit on the site at a readable city zoom. Settles once — no loop.
    if (nearCluster.length >= 2) {
      const bounds = new mapboxgl.LngLatBounds();
      bounds.extend([center[0] - 0.012, center[1] + 0.012]); // inland anchor
      bounds.extend(center);
      nearCluster.forEach((m) => m.lonLat && bounds.extend(m.lonLat));
      map.fitBounds(bounds, {
        padding: { top: 56, left: 56, bottom: 130, right: 130 },
        maxZoom: 13.5,
        duration: 700,
      });
    } else {
      // Nudge the look-at inland (north-west) so land fills the view, sea low-right.
      map.easeTo({ center: [center[0] - 0.018, center[1] + 0.016], zoom: 13, duration: 600 });
    }
  }, [ready, geoItems, recommendedIds, rankById, center]);

  // ── 4 · Cross-highlight: reflect `hoveredId` onto the pin DOM (cheap class toggle). ─
  useEffect(() => {
    pinsRef.current.forEach((p, id) => {
      const active = id === hoveredId;
      p.el.classList.toggle("mlm-pin--active", active);
      // Raise the active marker's wrapper so the card→pin direction also lifts/reveals.
      if (p.el.parentElement) p.el.parentElement.style.zIndex = active ? "6" : "";
    });
  }, [hoveredId, ready, geoItems]);

  if (!MAPBOX_TOKEN) {
    return (
      <div
        className="absolute inset-0 flex items-center justify-center p-8"
        style={{ background: "var(--surface-sunken)" }}
      >
        <p
          className="flex max-w-xs flex-col items-center gap-3 text-center font-mono text-[11px] leading-relaxed"
          style={{ color: "var(--grey)" }}
        >
          <Pin className="size-5" strokeWidth={1.5} />
          Missing VITE_MAPBOX_TOKEN — add a public, URL-restricted Mapbox token to
          frontend/.env.local (see .env.example) to show the sourcing map. Never hardcode it.
        </p>
      </div>
    );
  }

  return (
    // `absolute inset-0` (the right pane is `relative`) so the map fills the pane by
    // box-offset, NOT by `%`-height which collapses against a flex parent → 46px sliver.
    <div className="absolute inset-0" style={{ background: "var(--surface-sunken)" }}>
      <style>{MAP_CSS}</style>
      {/* Mapbox's own stylesheet forces `.mapboxgl-map { position: relative }`, which beats
          Tailwind's `absolute` and collapses the container to content height (~46px → black
          sliver). Inline `position:absolute` + inset wins over the stylesheet, so the GL
          container always fills the pane. */}
      <div
        ref={containerRef}
        style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}
      />
      {/* Quiet on-map legend — recommended vs source. */}
      <div
        className="pointer-events-none absolute left-4 top-4 z-10 flex flex-col gap-1.5 px-3 py-2.5"
        style={{
          background: "color-mix(in srgb, var(--black) 64%, transparent)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          backdropFilter: "blur(8px)",
          WebkitBackdropFilter: "blur(8px)",
        }}
      >
        <span
          className="font-mono text-[9px] uppercase tracking-[0.16em]"
          style={{ color: "var(--grey)" }}
        >
          Reclaimed sources · Parc del Fòrum
        </span>
        <span className="flex items-center gap-2 font-mono text-[10px]" style={{ color: "var(--paper)" }}>
          <span
            className="inline-block size-2.5"
            style={{ background: PALETTE.green2, borderRadius: 999, boxShadow: `0 0 6px ${PALETTE.green2}` }}
          />
          Recommended
        </span>
        <span className="flex items-center gap-2 font-mono text-[10px]" style={{ color: "var(--grey)" }}>
          <span
            className="inline-block size-2.5"
            style={{ background: PALETTE.teal, borderRadius: 999, opacity: 0.85 }}
          />
          Other nearby stock
        </span>
      </div>
    </div>
  );
}

/** Minimal HTML-escape for marker tooltip text injected via innerHTML. */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Marker DOM is created imperatively (Mapbox markers live outside React), so its
// styling lives in a scoped <style>. Tokens only; sharp 2px corners; the pulse is a
// short, FINITE compositor animation (3 iterations) that respects reduced motion.
const MAP_CSS = `
  /* Mapbox-positioned wrapper: NO transition/transform of our own, so the marker snaps
     exactly to its lon/lat each frame instead of gliding (the old drift bug). */
  .mlm-pin-wrap { line-height: 0; }
  .mlm-pin {
    position: relative;
    width: 22px; height: 22px;
    padding: 0; margin: 0; border: 0; background: transparent;
    cursor: pointer;
    transform: translateY(0);
    transition: transform .18s cubic-bezier(0.16,1,0.3,1);
  }
  /* Non-hovered pins read slightly quieter + smaller so overlapping markers don't
     fully hide one another; the recommended/active ones come forward (below). */
  .mlm-pin-dot {
    position: absolute; left: 50%; bottom: 0;
    width: 15px; height: 15px; margin-left: -7.5px;
    border-radius: 999px;
    background: var(--teal);
    border: 2px solid var(--black);
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--teal) 45%, transparent),
                0 2px 8px -2px rgba(0,0,0,0.8);
    opacity: 0.92;
    transition: width .18s, height .18s, margin-left .18s, background .18s, box-shadow .18s, opacity .18s;
  }
  .mlm-pin--rec .mlm-pin-dot {
    width: 18px; height: 18px; margin-left: -9px;
    background: ${PALETTE.green2};
    border-color: var(--black);
    box-shadow: 0 0 0 3px color-mix(in srgb, ${PALETTE.green2} 38%, transparent),
                0 0 12px -1px color-mix(in srgb, ${PALETTE.green2} 70%, transparent),
                0 2px 10px -2px rgba(0,0,0,0.85);
    opacity: 1;
  }
  .mlm-pin-rank {
    position: absolute; left: 50%; bottom: 20px;
    transform: translateX(-50%) scale(0.92);
    transform-origin: center bottom;
    min-width: 16px; height: 16px; padding: 0 4px;
    display: flex; align-items: center; justify-content: center;
    font-family: var(--font-mono); font-size: 9px; font-weight: 700;
    color: var(--black); background: ${PALETTE.green2};
    border: 1px solid var(--black);
    border-radius: 2px;
    box-shadow: 0 2px 6px -2px rgba(0,0,0,0.8);
    opacity: 0; transition: opacity .18s, transform .18s;
    pointer-events: none; white-space: nowrap;
  }
  .mlm-pin--rec .mlm-pin-rank { opacity: 1; }
  .mlm-pin:hover, .mlm-pin--active { transform: translateY(-3px); z-index: 5; }
  .mlm-pin:hover .mlm-pin-dot, .mlm-pin--active .mlm-pin-dot {
    width: 20px; height: 20px; margin-left: -10px; opacity: 1;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--teal) 50%, transparent),
                0 2px 10px -2px rgba(0,0,0,0.85);
  }
  .mlm-pin--rec:hover .mlm-pin-dot, .mlm-pin--rec.mlm-pin--active .mlm-pin-dot {
    box-shadow: 0 0 0 4px color-mix(in srgb, ${PALETTE.green2} 45%, transparent),
                0 0 16px 0 color-mix(in srgb, ${PALETTE.green2} 80%, transparent),
                0 2px 10px -2px rgba(0,0,0,0.9);
  }
  .mlm-pin--active .mlm-pin-rank, .mlm-pin:hover .mlm-pin-rank {
    transform: translateX(-50%) scale(1);
  }
  .mlm-pin-tip {
    position: absolute; left: 50%; bottom: 28px;
    transform: translateX(-50%) translateY(4px);
    display: flex; flex-direction: column; gap: 1px;
    padding: 6px 9px;
    /* Wrap instead of nowrap + cap width so the tip can't run off the map edge. */
    width: max-content; max-width: 168px;
    background: color-mix(in srgb, var(--black) 92%, transparent);
    border: 1px solid color-mix(in srgb, var(--teal) 38%, transparent);
    border-radius: 2px;
    box-shadow: 0 8px 24px -10px rgba(0,0,0,0.9);
    opacity: 0; pointer-events: none;
    transition: opacity .15s, transform .15s;
  }
  .mlm-pin--rec .mlm-pin-tip {
    border-color: color-mix(in srgb, ${PALETTE.green2} 45%, transparent);
  }
  .mlm-pin:hover .mlm-pin-tip, .mlm-pin--active .mlm-pin-tip,
  .mlm-pin:focus-visible .mlm-pin-tip {
    opacity: 1; transform: translateX(-50%) translateY(0);
  }
  .mlm-pin-tip-name { font-family: var(--font-sans); font-size: 11px; font-weight: 600; color: var(--paper); }
  .mlm-pin-tip-meta { font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.04em; color: var(--grey); }

  .mlm-site { position: relative; width: 18px; height: 18px; }
  .mlm-site-core {
    position: absolute; left: 50%; top: 50%;
    width: 13px; height: 13px; margin: -6.5px 0 0 -6.5px;
    border-radius: 999px; background: var(--ink);
    border: 2px solid var(--teal);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--teal) 26%, transparent),
                0 0 10px -1px color-mix(in srgb, var(--teal) 60%, transparent);
  }
  .mlm-site-pulse {
    position: absolute; left: 50%; top: 50%;
    width: 13px; height: 13px; margin: -6.5px 0 0 -6.5px;
    border-radius: 999px; border: 1px solid var(--teal);
    animation: mlm-site-pulse-kf 2.6s cubic-bezier(0.16,1,0.3,1) 3;
    animation-fill-mode: forwards;
  }
  .mlm-site-label {
    position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%);
    z-index: 2;
    font-family: var(--font-mono); font-size: 8px; font-weight: 700;
    letter-spacing: 0.18em; color: var(--paper); white-space: nowrap;
    padding: 1px 4px; border-radius: 2px;
    background: color-mix(in srgb, var(--black) 70%, transparent);
    text-shadow: 0 1px 4px rgba(0,0,0,0.9);
  }
  @keyframes mlm-site-pulse-kf {
    0%   { transform: scale(1); opacity: 0.6; }
    70%  { transform: scale(3); opacity: 0; }
    100% { transform: scale(3); opacity: 0; }
  }
  @media (prefers-reduced-motion: reduce) {
    .mlm-site-pulse { animation: none; opacity: 0; }
    .mlm-pin, .mlm-pin-dot, .mlm-pin-tip, .mlm-pin-rank { transition: none; }
  }
  /* Quiet the default mapbox dark controls so they don't shout over the data. */
  .mapboxgl-ctrl-bottom-right .mapboxgl-ctrl { margin: 0 8px 8px 0; }
`;
