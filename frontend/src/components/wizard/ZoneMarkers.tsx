import { Marker } from "react-map-gl/mapbox";
import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { Check } from "iconoir-react";
import { getStructureZones } from "@/lib/heatguard-api";
import { useHeatGuard } from "@/lib/heatguard-store";
import { PALETTE } from "@/lib/tokens";
import { EASE } from "@/lib/motion";

/**
 * Ranked shade-priority markers on the dark map well (spec S8 "ranked so the
 * organizer knows where to build first"; UI-SPEC §5.3: priority = colour + rank# +
 * size). Rendered as HTML <Marker>s so the rank stays legible over the glowing heat
 * field.
 *
 * DECLUTTER PASS (2026-06-24): the ranked instrument must win the map — it sits in
 * its own z-band ABOVE the heat field AND the schema labels, so the organizer's eye
 * lands on "where to build" first, never on a sponsor tag. Registers, deliberately:
 *  · RANK 1 is the RECOMMENDED zone — biggest chip, brand ORANGE accent (the new
 *    `--green`/`--green2`), so "build here first" reads at a glance as a positive
 *    call-to-action, distinct from the red danger data-frame around it.
 *  · The top hot×dense placements also carry a DANGER CROSS (s6-danger-cross.png):
 *    a RED square crosshair (heat = data meaning) that frames the cell and pulses a
 *    fixed number of beats, then SETTLES (no infinite loop). The placer ranks zones
 *    by hot×busy product, so the top rank sits on the most dangerous ground.
 *  · Every other zone is a quiet numbered chip — clear rank, tiny weight, one accent.
 *
 * Accepted → green/orange chip with a check. Hovered → lifts. Cross-highlights with
 * the side table through the store's `hoveredZone` (wiring preserved exactly:
 * setHoveredZone in/out, toggleAccept on click).
 */

// Top placements sit on hot×dense ground → danger register. Below that, quiet.
function isDangerRank(rank: number): boolean {
  return rank <= 2;
}

export function ZoneMarkers() {
  const { state, dispatch } = useHeatGuard();
  const { simRunId, acceptedRanks, hoveredZone } = state;
  const reduce = useReducedMotion();
  const { data } = useQuery({
    queryKey: ["zones", simRunId],
    queryFn: () => getStructureZones(simRunId!),
    enabled: simRunId !== null,
    staleTime: Infinity,
    retry: false,
  });
  if (!data) return null;

  return (
    <>
      {data.structures.map((z) => {
        const accepted = acceptedRanks.includes(z.rank);
        const hot = hoveredZone === z.rank;
        const danger = isDangerRank(z.rank) && !accepted;

        // Chip dimensions: rank 1 reads biggest, weight steps down, hover adds a beat.
        const base = z.rank === 1 ? 30 : z.rank === 2 ? 27 : 24;
        const size = hot ? base + 5 : base;
        // RANK 1 is the recommended zone → brand ORANGE accent fill. The danger
        // CROSS around it stays red (data meaning); the chip itself reads positive.
        const recommended = z.rank === 1 && !accepted;
        const bg = accepted
          ? PALETTE.green
          : recommended
            ? PALETTE.green2
            : danger
              ? PALETTE.heat
              : PALETTE.ink;
        const ring = accepted
          ? PALETTE.green2
          : recommended
            ? PALETTE.green
            : danger
              ? PALETTE.heat
              : "rgba(242,240,237,0.55)";

        return (
          <Marker key={z.rank} longitude={z.center[0]} latitude={z.center[1]} anchor="center">
            {/* The ranked instrument owns its own z-band ABOVE heat + schema labels,
                so chips never read behind a sponsor tag. Hovered chip lifts highest. */}
            <div
              className="relative flex items-center justify-center"
              style={{ width: size, height: size, zIndex: hot ? 30 : z.rank === 1 ? 22 : 20 }}
            >
              {/* DANGER CROSS — RED square crosshair (heat = data meaning) framing
                  the hottest×densest cells. Pulses a fixed number of beats, settles. */}
              {danger && (
                <DangerCross size={size} reduce={!!reduce} emphatic={z.rank === 1} active={hot} />
              )}

              <button
                type="button"
                onClick={() => dispatch({ type: "toggleAccept", rank: z.rank })}
                onMouseEnter={() => dispatch({ type: "setHoveredZone", rank: z.rank })}
                onMouseLeave={() => dispatch({ type: "setHoveredZone", rank: null })}
                title={`Zone ${z.rank} — ${accepted ? "accepted (click to dismiss)" : "click to accept"}`}
                aria-label={`Shade priority zone, rank ${z.rank}${danger ? ", hot and crowded" : ""}${accepted ? ", accepted" : ""}`}
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
                  zIndex: 2,
                }}
              >
                {accepted ? (
                  <Check width={size * 0.55} height={size * 0.55} strokeWidth={2.6} />
                ) : (
                  z.rank
                )}
              </button>
            </div>
          </Marker>
        );
      })}
    </>
  );
}

/**
 * The RED square crosshair from s6-danger-cross.png (heat colour = data meaning,
 * kept distinct from the orange recommended chip it frames). Four corner brackets +
 * tick marks framing the cell. Breathes for a fixed count of beats then settles to
 * a calm steady state — never an infinite CPU loop. Hover re-asserts a brighter frame.
 */
function DangerCross({
  size,
  reduce,
  emphatic,
  active,
}: {
  size: number;
  reduce: boolean;
  emphatic: boolean;
  active: boolean;
}) {
  // Frame is ~2.1× the chip so corner brackets sit clear of the numeral.
  const box = Math.round(size * 2.1);
  const corner = Math.round(box * 0.26);
  const t = 1.6;
  const color = PALETTE.heat;

  // A fixed-count breathe (emphatic #1 pulses a few beats; others a single settle),
  // then it rests. repeat is a finite integer, so the animation always settles.
  const beats = reduce ? 0 : emphatic ? 4 : 1;

  return (
    <motion.div
      aria-hidden
      className="pointer-events-none absolute"
      style={{ width: box, height: box, left: "50%", top: "50%", x: "-50%", y: "-50%", zIndex: 1 }}
      initial={reduce ? false : { scale: 1.18, opacity: 0 }}
      animate={
        active
          ? { scale: 1, opacity: 1 }
          : reduce
            ? { scale: 1, opacity: 0.9 }
            : { scale: [1.06, 1, 1.06], opacity: [0.55, 1, 0.55] }
      }
      transition={
        active || reduce
          ? { duration: 0.25, ease: EASE.out }
          : { duration: t, ease: EASE.inOut, repeat: beats, repeatType: "loop" }
      }
    >
      {/* four corner brackets */}
      {(
        [
          { top: 0, left: 0, bt: t, bl: t, br: 0, bb: 0 },
          { top: 0, right: 0, bt: t, br: t, bl: 0, bb: 0 },
          { bottom: 0, left: 0, bb: t, bl: t, bt: 0, br: 0 },
          { bottom: 0, right: 0, bb: t, br: t, bt: 0, bl: 0 },
        ] as const
      ).map((c, i) => (
        <span
          key={i}
          style={{
            position: "absolute",
            top: c.top,
            left: c.left,
            right: c.right,
            bottom: c.bottom,
            width: corner,
            height: corner,
            borderTop: `${c.bt}px solid ${color}`,
            borderLeft: `${c.bl}px solid ${color}`,
            borderRight: `${c.br}px solid ${color}`,
            borderBottom: `${c.bb}px solid ${color}`,
          }}
        />
      ))}
      {/* faint full square so the cell reads as boxed, not just cornered */}
      <span
        style={{
          position: "absolute",
          inset: 0,
          border: `1px solid color-mix(in srgb, ${color} 28%, transparent)`,
        }}
      />
    </motion.div>
  );
}
