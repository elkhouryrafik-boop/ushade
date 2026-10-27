import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import type { MaterialItem } from "@/lib/materials-provider";
import { PALETTE } from "@/lib/tokens";

/**
 * S9e — Sourcing proximity instrument.
 *
 * A radial/orbital diagram, not a generic spoke chart: the SITE sits at the centre
 * (a glowing ink/teal hub); every reclaimed source is placed by its TRUE BEARING
 * from the site and its TRUE DISTANCE (mapped onto concentric distance rings labelled
 * in km), so proximity reads instantly — closest stock hugs the centre.
 *
 *   · Distance rings fade + scale in on mount; km ticks sit on the 0° (north) axis.
 *   · Spokes DRAW IN from the hub outward (stroke-dashoffset transition); closer
 *     sources get a thicker, brighter spoke.
 *   · Source dots pop in staggered. Live-stock (bindable) sources read teal with a
 *     soft pulse halo; reference sources read grey + ghost ring.
 *   · Hover cross-highlights (honours the onHover prop contract) + a dark-glass tooltip
 *     (name · km · type).
 *
 * Settles after the entry transition — the only ongoing motion is a CSS pulse on
 * live-stock halos (cheap, compositor-only). Props/exports are unchanged.
 */

interface SourcingMapProps {
  items: MaterialItem[];
  holds: Record<string, { expiresAt: number; holdId: string }>;
  siteCenter: [number, number]; // [lon, lat]
  hoveredId?: string | null;
  onHover?: (id: string | null) => void;
}

interface Point {
  id: string;
  name: string;
  distanceKm: number;
  /** bearing from site, radians, 0 = north, clockwise */
  bearing: number;
  /** live, bindable stock (teal) vs reference (grey) */
  live: boolean;
  type: "struct" | "membr";
}

const W = 520;
const H = 460;
const CX = W / 2;
const CY = H / 2 + 6;
const R_MAX = 188; // outer ring radius in px

/** Haversine distance (km) between two [lon,lat] points. */
function haversineKm(a: [number, number], b: [number, number]): number {
  const R = 6371;
  const dLat = ((b[1] - a[1]) * Math.PI) / 180;
  const dLon = ((b[0] - a[0]) * Math.PI) / 180;
  const la1 = (a[1] * Math.PI) / 180;
  const la2 = (b[1] * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Initial bearing (radians, 0 = north, clockwise) from `from` to `to`. */
function bearingRad(from: [number, number], to: [number, number]): number {
  const la1 = (from[1] * Math.PI) / 180;
  const la2 = (to[1] * Math.PI) / 180;
  const dLon = ((to[0] - from[0]) * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos(la2);
  const x = Math.cos(la1) * Math.sin(la2) - Math.sin(la1) * Math.cos(la2) * Math.cos(dLon);
  return Math.atan2(y, x); // 0 = north, +clockwise
}

/** Choose 4 "nice" ring values that bracket the farthest source. */
function ringValues(maxKm: number): number[] {
  const top = Math.max(5, Math.ceil(maxKm / 5) * 5);
  const step = top / 4;
  return [step, step * 2, step * 3, step * 4].map((v) => Math.round(v * 10) / 10);
}

export function SourcingMap({ items, holds, siteCenter, hoveredId, onHover }: SourcingMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; name: string; km: string; type: string } | null>(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // ── Build points: bearing + distance from the site, live vs reference. ──
    const points: Point[] = items
      .filter((m) => m.lonLat)
      .map((m) => {
        const km = m.distanceKm ?? haversineKm(siteCenter, m.lonLat);
        return {
          id: m.id,
          name: m.name,
          distanceKm: km,
          bearing: bearingRad(siteCenter, m.lonLat),
          // live = bindable live/onboarded stock; holds also count as live.
          live: !!holds[m.id] || m.bindable === true || m.bindSource === "scrape" || m.bindSource === "onboarded",
          type: m.type,
        };
      });

    if (!points.length) return;

    const maxKm = Math.max(...points.map((p) => p.distanceKm), 1);
    const rings = ringValues(maxKm);
    const ringTop = rings[rings.length - 1];
    // radial scale: 0 km → centre, ringTop → outer ring. sqrt eases crowding near site.
    const rScale = d3.scaleSqrt().domain([0, ringTop]).range([16, R_MAX]);

    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const DUR = prefersReduced ? 0 : 1;

    // position helper (0° = north / up, clockwise)
    const pos = (bearing: number, km: number): [number, number] => {
      const r = rScale(km);
      return [CX + r * Math.sin(bearing), CY - r * Math.cos(bearing)];
    };

    const defs = svg.append("defs");
    // Radial glow for the hub.
    const grad = defs.append("radialGradient").attr("id", "sm-hub-glow");
    grad.append("stop").attr("offset", "0%").attr("stop-color", PALETTE.teal).attr("stop-opacity", 0.28);
    grad.append("stop").attr("offset", "100%").attr("stop-color", PALETTE.teal).attr("stop-opacity", 0);

    const root = svg.append("g");

    // ── 1 · Distance rings (fade + scale in). ──────────────────────────────
    const ringsG = root.append("g").attr("data-layer", "rings");
    rings.forEach((km, i) => {
      const r = rScale(km);
      const ring = ringsG
        .append("circle")
        .attr("cx", CX)
        .attr("cy", CY)
        .attr("r", r)
        .attr("fill", "none")
        .attr("stroke", "var(--border)")
        .attr("stroke-width", i === rings.length - 1 ? 1.25 : 0.75)
        .attr("stroke-dasharray", i === rings.length - 1 ? "none" : "2 5")
        .attr("opacity", 0);
      ring
        .transition()
        .delay(i * 70 * DUR)
        .duration(420 * DUR)
        .attr("opacity", i === rings.length - 1 ? 0.9 : 0.55)
        .ease(d3.easeCubicOut);

      // km tick label — sit just inside each ring on the north axis, nudged clear
      // of the vertical N guide so the numeral never overlaps the dashed line.
      // The unit ("km") is a dimmer tspan so the value reads first.
      const label = ringsG
        .append("text")
        .attr("x", CX + 7)
        .attr("y", CY - r + 11)
        .attr("text-anchor", "start")
        .style("font-family", "var(--font-mono)")
        .style("font-size", "9px")
        .style("letter-spacing", "0.04em")
        .style("fill", "var(--grey)")
        .style("opacity", 0)
        .text(`${km}`);
      label.append("tspan").style("opacity", 0.55).text(" km");
      label.transition().delay(i * 70 * DUR + 200 * DUR).duration(360 * DUR).style("opacity", 0.85);
    });

    // faint vertical N axis line for orientation
    const axis = root
      .append("line")
      .attr("x1", CX)
      .attr("y1", CY - rScale(ringTop))
      .attr("x2", CX)
      .attr("y2", CY + 16)
      .attr("stroke", "var(--border)")
      .attr("stroke-width", 0.5)
      .attr("stroke-dasharray", "1 6")
      .attr("opacity", 0);
    axis.transition().delay(120 * DUR).duration(400 * DUR).attr("opacity", 0.5);
    const nLabel = root
      .append("text")
      .attr("x", CX)
      .attr("y", CY - rScale(ringTop) - 8)
      .attr("text-anchor", "middle")
      .style("font-family", "var(--font-mono)")
      .style("font-size", "8px")
      .style("letter-spacing", "0.18em")
      .style("fill", "var(--grey)")
      .style("opacity", 0)
      .text("N");
    nLabel.transition().delay(300 * DUR).duration(400 * DUR).style("opacity", 0.7);

    // ── 2 · Spokes (draw in, hub → source). ────────────────────────────────
    const spokesG = root.append("g").attr("data-layer", "spokes");
    points.forEach((p, i) => {
      const [px, py] = pos(p.bearing, p.distanceKm);
      const isHover = hoveredId === p.id;
      // closer = thicker + brighter. Range ~ 0.75..3px.
      const closeness = 1 - Math.min(1, p.distanceKm / ringTop);
      const baseW = 0.75 + closeness * 2.25;
      const len = Math.hypot(px - CX, py - CY);

      const line = spokesG
        .append("line")
        .attr("x1", CX)
        .attr("y1", CY)
        .attr("x2", px)
        .attr("y2", py)
        .attr("stroke", p.live ? PALETTE.teal : PALETTE.grey)
        .attr("stroke-width", isHover ? baseW + 1.5 : baseW)
        .attr("stroke-linecap", "round")
        .attr("stroke-dasharray", p.live ? "none" : "1.5 4")
        .attr("opacity", 0)
        .attr("data-spoke", p.id)
        .style("transition", "stroke 0.18s, stroke-width 0.18s, opacity 0.18s");

      if (p.live) {
        // animate the solid spoke drawing outward
        line
          .attr("stroke-dasharray", len)
          .attr("stroke-dashoffset", len)
          .attr("opacity", isHover ? 1 : closeness * 0.5 + 0.35)
          .transition()
          .delay(360 * DUR + i * 45 * DUR)
          .duration(620 * DUR)
          .ease(d3.easeCubicOut)
          .attr("stroke-dashoffset", 0)
          .on("end", function () {
            d3.select(this).attr("stroke-dasharray", "none");
          });
      } else {
        // dashed reference spoke — just fade in (keep its dash pattern)
        line
          .transition()
          .delay(360 * DUR + i * 45 * DUR)
          .duration(500 * DUR)
          .attr("opacity", isHover ? 0.9 : 0.4);
      }
    });

    // ── 3 · Source dots (staggered pop-in). ────────────────────────────────
    const dotsG = root.append("g").attr("data-layer", "dots");
    points.forEach((p, i) => {
      const [px, py] = pos(p.bearing, p.distanceKm);
      const isHover = hoveredId === p.id;
      const color = p.live ? PALETTE.teal : PALETTE.grey;
      const g = dotsG
        .append("g")
        .attr("transform", `translate(${px},${py})`)
        .style("cursor", "pointer")
        .attr("data-dot", p.id);

      // live-stock pulse halo (CSS keyframe — settles into a gentle loop, cheap).
      if (p.live) {
        g.append("circle")
          .attr("r", 7)
          .attr("fill", "none")
          .attr("stroke", PALETTE.teal)
          .attr("stroke-width", 1)
          .attr("class", "sm-pulse")
          .style("transform-origin", "center")
          .style("transform-box", "fill-box");
      } else {
        // reference: static ghost ring
        g.append("circle")
          .attr("r", 8)
          .attr("fill", "none")
          .attr("stroke", PALETTE.grey)
          .attr("stroke-width", 0.75)
          .attr("opacity", 0.5);
      }

      const dot = g
        .append("circle")
        .attr("r", 0)
        .attr("fill", p.live ? color : "var(--bg)")
        .attr("stroke", color)
        .attr("stroke-width", p.live ? 1.5 : 1.5)
        .attr("data-core", p.id);

      const targetR = isHover ? 6.5 : p.live ? 5 : 4;
      dot
        .transition()
        .delay(560 * DUR + i * 50 * DUR)
        .duration(420 * DUR)
        .ease(d3.easeBackOut.overshoot(2))
        .attr("r", targetR);

      // hover hit-area (invisible, generous) + tooltip + cross-highlight
      g.append("circle")
        .attr("r", 13)
        .attr("fill", "transparent")
        .on("mouseenter", function (event: MouseEvent) {
          onHover?.(p.id);
          const [mx, my] = d3.pointer(event, svgRef.current);
          setTooltip({
            x: mx,
            y: my,
            name: p.name,
            km: `${Math.round(p.distanceKm * 10) / 10} km`,
            type: p.type === "struct" ? "Structural" : "Membrane",
          });
        })
        .on("mousemove", function (event: MouseEvent) {
          const [mx, my] = d3.pointer(event, svgRef.current);
          setTooltip((t) => (t ? { ...t, x: mx, y: my } : t));
        })
        .on("mouseleave", function () {
          onHover?.(null);
          setTooltip(null);
        });
    });

    // ── 4 · The hub — festival site. ───────────────────────────────────────
    const hub = root.append("g").attr("transform", `translate(${CX},${CY})`);
    hub
      .append("circle")
      .attr("r", 46)
      .attr("fill", "url(#sm-hub-glow)")
      .attr("opacity", 0)
      .transition()
      .duration(700 * DUR)
      .attr("opacity", 1);

    hub
      .append("circle")
      .attr("r", 0)
      .attr("fill", PALETTE.ink)
      .attr("stroke", PALETTE.teal)
      .attr("stroke-width", 2)
      .transition()
      .duration(500 * DUR)
      .ease(d3.easeBackOut.overshoot(1.6))
      .attr("r", 9);

    hub
      .append("circle")
      .attr("r", 3)
      .attr("fill", PALETTE.teal)
      .attr("opacity", 0)
      .transition()
      .delay(300 * DUR)
      .duration(400 * DUR)
      .attr("opacity", 1);

    const siteLabel = hub
      .append("text")
      .attr("x", 0)
      .attr("y", 26)
      .attr("text-anchor", "middle")
      .style("font-family", "var(--font-mono)")
      .style("font-size", "9px")
      .style("font-weight", "600")
      .style("letter-spacing", "0.18em")
      .style("fill", "var(--text-primary)")
      .style("opacity", 0)
      .text("SITE");
    siteLabel.transition().delay(420 * DUR).duration(400 * DUR).style("opacity", 1);
  }, [items, holds, siteCenter, hoveredId, onHover]);

  return (
    <div className="relative w-full">
      <style>{`
        @keyframes sm-pulse-kf {
          0%   { transform: scale(1);   opacity: 0.55; }
          70%  { transform: scale(2.4); opacity: 0;    }
          100% { transform: scale(2.4); opacity: 0;    }
        }
        .sm-pulse { animation: sm-pulse-kf 2.6s cubic-bezier(0.16,1,0.3,1) infinite; }
        @media (prefers-reduced-motion: reduce) {
          .sm-pulse { animation: none; opacity: 0.4; }
        }
      `}</style>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full"
        role="img"
        aria-label="Sourcing proximity diagram — reclaimed material sources by distance and bearing from the site"
        style={{ maxWidth: "100%", height: "auto" }}
      />
      {tooltip && (
        <div
          className="pointer-events-none absolute z-10"
          style={{
            left: `${(tooltip.x / W) * 100}%`,
            top: `${(tooltip.y / H) * 100}%`,
            // Flip the tooltip to the left of the cursor on the right half so it
            // never clips off the instrument's edge.
            transform:
              tooltip.x > W * 0.62
                ? "translate(calc(-100% - 14px), -50%)"
                : "translate(14px, -50%)",
          }}
        >
          <div
            className="px-2.5 py-1.5"
            style={{
              border: "1px solid color-mix(in srgb, var(--teal) 40%, transparent)",
              borderRadius: "var(--radius-sm)",
              background: "color-mix(in srgb, var(--ink) 92%, transparent)",
              backdropFilter: "blur(6px)",
              boxShadow: "0 6px 24px -8px rgba(0,0,0,0.5)",
            }}
          >
            <p className="font-sans text-[12px] font-semibold leading-tight" style={{ color: "var(--white)" }}>
              {tooltip.name}
            </p>
            <p className="mt-0.5 flex items-center gap-1.5 font-mono text-[10px]" style={{ color: "var(--grey)" }}>
              <span className="tabular-nums" style={{ color: "var(--teal)" }}>{tooltip.km}</span>
              <span style={{ opacity: 0.5 }}>·</span>
              <span className="uppercase tracking-[0.08em]">{tooltip.type}</span>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
