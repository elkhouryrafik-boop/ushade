import { useMemo, useState } from "react";
import { Marker } from "react-map-gl/mapbox";
import { useQuery } from "@tanstack/react-query";
import { getFestivalSchema } from "@/lib/heatguard-api";
import { schemaPoints, labelledSchemaPoints, type SchemaPoint } from "@/lib/festival-schema-layers";

/**
 * HTML name labels for the festival's stages + entrances (the navigation anchors),
 * rendered as react-map-gl <Marker>s pinned to coordinates. Mounted inside <Map>.
 *
 * DECLUTTER PASS (2026-06-24): the placement map was a label soup — ~19 leader-lined
 * tags (stages named after sponsors + entrances) all shouting at the same weight,
 * overlapping each other and fighting the bright heat field. The fix establishes a
 * clear two-register hierarchy + de-overlap, WITHOUT dropping real info:
 *
 *   1. STAGES are the primary anchors (the crowd magnets the placer reasons about),
 *      so they stay PROMINENT: amber anchor dot, leader, tracked mono tag on a
 *      strong near-opaque plate that reads over even 46 °C heat.
 *   2. ENTRANCES are demoted to a QUIET secondary register: a small green dot at
 *      rest with no plate, and the name revealed only on hover. This kills most of
 *      the visual noise while keeping every entrance discoverable.
 *   3. A deterministic lon/lat de-overlap nudges clustered stage tags apart
 *      vertically (alternating up/down) so leader-lined tags never stack.
 *
 * Non-interactive plates (the label never steals clicks from the zone chips); only
 * the quiet entrance markers accept hover, and that's pointer-events scoped to the
 * dot so it still won't block the chips beneath. No props (signature preserved).
 */

const LEADER_LEN = 14; // px the connector steps out from the anchor dot

// Cluster radius in degrees (~ a few tens of metres at this latitude). Stage tags
// whose anchors fall within this of an earlier-placed tag get nudged vertically so
// their plates don't overlap. Deterministic: order-stable, no layout measurement.
const DEOVERLAP_DEG = 0.0016;
const NUDGE_PX = 15; // vertical step applied per collision, alternating sign

type Placed = SchemaPoint & { dy: number };

/**
 * Greedy vertical de-overlap over the stage tags. Walks points in order; for each,
 * counts how many already-placed stage tags sit within DEOVERLAP_DEG and assigns an
 * alternating up/down offset of increasing magnitude. Pure, deterministic, cheap.
 */
function deoverlapStages(stages: SchemaPoint[]): Placed[] {
  const placed: Placed[] = [];
  for (const p of stages) {
    let collisions = 0;
    for (const q of placed) {
      const d = Math.hypot(p.lon - q.lon, p.lat - q.lat);
      if (d < DEOVERLAP_DEG) collisions++;
    }
    // 0 → 0px, 1 → +15, 2 → −30, 3 → +45 … keeps plates from stacking.
    const step = Math.ceil(collisions / 2);
    const sign = collisions % 2 === 1 ? 1 : -1;
    placed.push({ ...p, dy: collisions === 0 ? 0 : sign * step * NUDGE_PX });
  }
  return placed;
}

export function SchemaLabels() {
  const { data } = useQuery({
    queryKey: ["festival-schema"],
    queryFn: getFestivalSchema,
    staleTime: Infinity,
  });

  const all = data ? labelledSchemaPoints(schemaPoints(data.features)) : [];
  const stages = useMemo(
    () => deoverlapStages(all.filter((p) => p.kind === "stage")),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data],
  );
  const entries = useMemo(
    () => all.filter((p) => p.kind !== "stage"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data],
  );

  if (!data) return null;

  return (
    <>
      {/* QUIET register — entrances: a small dot at rest, name on hover only. */}
      {entries.map((p, i) => (
        <Marker key={`entry-${p.name}-${i}`} longitude={p.lon} latitude={p.lat} anchor="left">
          <EntranceTag name={p.name} />
        </Marker>
      ))}

      {/* PROMINENT register — stages: leader-lined tag on a strong plate, de-overlapped. */}
      {stages.map((p, i) => (
        <Marker key={`stage-${p.name}-${i}`} longitude={p.lon} latitude={p.lat} anchor="left">
          <span
            className="pointer-events-none flex select-none items-center"
            style={{ transform: p.dy ? `translateY(${p.dy}px)` : undefined }}
          >
            {/* anchor dot — sits ON the coordinate even when the tag is nudged */}
            <span
              aria-hidden
              style={{
                width: 7,
                height: 7,
                borderRadius: 9,
                background: "var(--amber)",
                flexShrink: 0,
                boxShadow: "0 0 0 2px color-mix(in srgb, var(--amber) 26%, transparent)",
                transform: p.dy ? `translateY(${-p.dy}px)` : undefined,
              }}
            />
            {/* hairline leader — when nudged, it slants from the dot toward the tag */}
            <span
              aria-hidden
              style={{
                width: LEADER_LEN,
                height: 1,
                flexShrink: 0,
                background: "color-mix(in srgb, var(--amber) 60%, transparent)",
                transform: p.dy ? `translateY(${-p.dy / 2}px)` : undefined,
              }}
            />
            {/* the tracked mono tag — strong near-opaque plate for heat legibility */}
            <span
              className="whitespace-nowrap font-mono uppercase leading-none"
              style={{
                background: "color-mix(in srgb, var(--black) 94%, transparent)",
                color: "var(--paper)",
                fontSize: 9.5,
                fontWeight: 600,
                letterSpacing: "0.13em",
                padding: "3.5px 6.5px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid color-mix(in srgb, var(--amber) 34%, transparent)",
                boxShadow: "0 1px 6px rgba(0,0,0,0.6)",
                backdropFilter: "blur(2px)",
              }}
            >
              {p.name}
            </span>
          </span>
        </Marker>
      ))}
    </>
  );
}

/**
 * Quiet entrance marker: a small green source dot at rest; the name fades in on
 * hover (CSS group-hover, settles instantly — no JS, no infinite loop). The dot is
 * the only pointer-events surface and it sits on the entrance coordinate, so it
 * never covers the zone chips. The hover plate is non-interactive.
 */
function EntranceTag({ name }: { name: string }) {
  const [hover, setHover] = useState(false);
  return (
    <span className="flex select-none items-center">
      <span
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          width: 6,
          height: 6,
          borderRadius: 9,
          background: "var(--green2)",
          flexShrink: 0,
          cursor: "default",
          boxShadow: "0 0 0 1.5px color-mix(in srgb, var(--black) 70%, transparent)",
        }}
      />
      {/* leader + label revealed only while hovering this entrance */}
      <span
        aria-hidden
        className="pointer-events-none flex items-center"
        style={{
          opacity: hover ? 1 : 0,
          transform: hover ? "translateX(0)" : "translateX(-3px)",
          transition: "opacity 0.15s ease-out, transform 0.15s ease-out",
        }}
      >
        <span
          style={{
            width: 9,
            height: 1,
            flexShrink: 0,
            background: "color-mix(in srgb, var(--green2) 55%, transparent)",
          }}
        />
        <span
          className="whitespace-nowrap font-mono uppercase leading-none"
          style={{
            background: "color-mix(in srgb, var(--black) 90%, transparent)",
            color: "var(--green2)",
            fontSize: 8,
            fontWeight: 500,
            letterSpacing: "0.12em",
            padding: "2.5px 5px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid color-mix(in srgb, var(--grey) 22%, transparent)",
            boxShadow: "0 1px 5px rgba(0,0,0,0.5)",
            backdropFilter: "blur(2px)",
          }}
        >
          {name}
        </span>
      </span>
    </span>
  );
}
