import { useEffect, useRef } from "react";
import { useReducedMotion, animate } from "framer-motion";
import { useHeatGuard } from "@/lib/heatguard-store";
import { useForumSite } from "@/lib/forum-site";
import { useMapCanvas } from "../PersistentMapCanvas";
import { StageScaffold, EmptyState } from "../StageScaffold";
import { EASE, DUR } from "@/lib/motion";
import { EditPencil, Position, Globe, Crop, MapPin, WarningTriangle } from "iconoir-react";

/**
 * S2 — Site. Draw / confirm the boundary on the persistent canvas.
 * IAAC editorial: the site readout reads like a precise instrument — a hero area
 * datum framed in corner brackets, tiny mono readout rows, ruled dividers.
 * All API wiring unchanged — boundary is managed by mapbox-gl-draw (in Shell).
 */
export function SiteStage() {
  const { state, dispatch } = useHeatGuard();
  const { setLayers, setLayerUI } = useMapCanvas();
  const areaM2 = state.project.siteAreaM2;
  const hasBoundary = areaM2 > 0;
  const reduce = useReducedMotion();

  useEffect(() => {
    setLayers([]);
    setLayerUI({ rows: [], onToggle: () => {} });
  }, [setLayers, setLayerUI]);

  const ha = areaM2 / 10000;

  return (
    <StageScaffold
      index="02 / SITE"
      title="Set your festival boundary"
      lede="The polygon you draw is the actual ground the engine reasons over. Real from the first click."
      cta={
        hasBoundary
          ? {
              label: "Place the layout →",
              onClick: () => dispatch({ type: "setStage", stage: "layout" }),
            }
          : undefined
      }
    >
      {!hasBoundary ? (
        <div className="space-y-7">
          <ForumShortcut />
          <DrawState />
        </div>
      ) : (
        <SiteReadout ha={ha} areaM2={areaM2} reduce={!!reduce} />
      )}
    </StageScaffold>
  );
}

/* ── One-click demo-site loader ─────────────────────────────────────────────
 * Drops the REAL Parc del Fòrum boundary + reads in the festival points of
 * interest (stages, entrances, amenities) so the architect can skip drawing.
 */
function ForumShortcut() {
  const { load, loading, error } = useForumSite();
  return (
    <div
      className="px-5 py-5"
      style={{
        background: "color-mix(in srgb, var(--green) 6%, transparent)",
        border: "1px solid color-mix(in srgb, var(--green) 35%, var(--border))",
        borderRadius: "var(--radius-sm)",
      }}
    >
      <div className="flex items-center gap-2">
        <MapPin className="size-3.5" strokeWidth={1.5} style={{ color: "var(--green)" }} />
        <p className="text-label" style={{ color: "var(--grey)" }}>
          Demo site · Parc del Fòrum
        </p>
      </div>
      <p className="mt-2 text-sm leading-snug" style={{ color: "var(--text-primary)" }}>
        Skip drawing — load the real Parc del Fòrum boundary with its stages, entrances and
        amenities already on the map.
      </p>
      <button
        type="button"
        onClick={() => load()}
        disabled={loading}
        className="mt-3.5 flex h-11 w-full items-center justify-center gap-2 font-sans font-bold transition-opacity hover:opacity-90 disabled:opacity-60"
        style={{
          background: "var(--green)",
          color: "var(--paper)",
          borderRadius: "var(--radius-sm)",
          letterSpacing: "0.03em",
          fontSize: "0.875rem",
        }}
      >
        <MapPin className="size-4" strokeWidth={2} />
        {loading ? "Loading Parc del Fòrum…" : "Load Parc del Fòrum site"}
      </button>
      {error && (
        <p className="mt-2.5 flex items-center gap-1.5 font-mono text-[11px]" style={{ color: "var(--red)" }}>
          <WarningTriangle className="size-3.5" strokeWidth={1.5} />
          {error}
        </p>
      )}
    </div>
  );
}

/* ── Empty / draw affordance — instrument instructions, not a card ─────────── */
function DrawState() {
  return (
    <div className="space-y-6">
      <EmptyState
        title="Draw your festival site to begin"
        body="Use the polygon tool on the map to trace the event boundary. We never auto-complete — finish the shape to lock it in."
        icon={<EditPencil className="size-12" strokeWidth={1} />}
      />

      {/* Procedure — numbered, mono, ruled like a field manual */}
      <div>
        <p className="text-label" style={{ color: "var(--grey)" }}>
          Procedure
        </p>
        <ol className="mt-3">
          {[
            ["01", "Select the polygon tool, top-left of the map."],
            ["02", "Click to place each vertex around the site."],
            ["03", "Double-click the first point to close the ring."],
          ].map(([n, txt], i) => (
            <li
              key={n}
              className="flex items-baseline gap-3 py-2.5"
              style={{
                borderTop: i === 0 ? "1px solid var(--text-primary)" : "1px solid var(--border)",
              }}
            >
              <span
                className="font-mono text-[11px] tabular-nums"
                style={{ color: "var(--grey)", minWidth: "1.5rem" }}
              >
                {n}
              </span>
              <span className="text-sm leading-snug" style={{ color: "var(--text-primary)" }}>
                {txt}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

/* ── Site readout — the precise instrument ─────────────────────────────────── */
function SiteReadout({ ha, areaM2, reduce }: { ha: number; areaM2: number; reduce: boolean }) {
  return (
    <div className="space-y-6">
      {/* Header breadcrumb — like the s2-readout ref */}
      <div className="flex items-center gap-2">
        <Position className="size-3.5" strokeWidth={1.5} style={{ color: "var(--green)" }} />
        <p className="text-label" style={{ color: "var(--grey)" }}>
          Site readout · live geometry
        </p>
      </div>

      {/* Hero datum framed in corner brackets — instrument readout */}
      <BracketFrame>
        <p className="text-label" style={{ color: "var(--grey)" }}>
          Site area
        </p>
        <div className="mt-2 flex items-end gap-2.5">
          <CountUpHa value={ha} reduce={reduce} />
          <span className="text-headline mb-1" style={{ color: "var(--grey)", fontWeight: 600 }}>
            ha
          </span>
        </div>
      </BracketFrame>

      {/* Mono readout rows — area / datum / status */}
      <dl>
        <ReadoutRow
          icon={<Crop className="size-3.5" strokeWidth={1.5} />}
          label="Surface"
          value={`${areaM2.toLocaleString(undefined, { maximumFractionDigits: 0 })} m²`}
          first
        />
        <ReadoutRow
          icon={<Globe className="size-3.5" strokeWidth={1.5} />}
          label="Datum"
          value="WGS 84"
        />
        <ReadoutRow
          icon={
            <span
              className="inline-block size-1.5 rounded-full"
              style={{ background: "var(--green)" }}
            />
          }
          label="Status"
          value="Boundary locked"
          valueColor="var(--green)"
        />
      </dl>

      <p
        className="text-xs leading-relaxed"
        style={{ color: "var(--grey)", fontFamily: "var(--font-mono)" }}
      >
        Re-draw or drag a vertex on the map to adjust — the area updates live. Continue to find
        locally-reclaimed material near this site.
      </p>
    </div>
  );
}

/* Corner-bracket frame — the instrument bezel from the readout ref. */
function BracketFrame({ children }: { children: React.ReactNode }) {
  const corner = "1px solid color-mix(in srgb, var(--green) 55%, transparent)";
  const len = "14px";
  return (
    <div
      className="relative px-5 py-5"
      style={{ background: "color-mix(in srgb, var(--green) 5%, transparent)" }}
    >
      {/* four L-shaped corners */}
      <span className="pointer-events-none absolute left-0 top-0" style={{ width: len, height: len, borderTop: corner, borderLeft: corner }} />
      <span className="pointer-events-none absolute right-0 top-0" style={{ width: len, height: len, borderTop: corner, borderRight: corner }} />
      <span className="pointer-events-none absolute bottom-0 left-0" style={{ width: len, height: len, borderBottom: corner, borderLeft: corner }} />
      <span className="pointer-events-none absolute bottom-0 right-0" style={{ width: len, height: len, borderBottom: corner, borderRight: corner }} />
      {children}
    </div>
  );
}

/* The big counting area number — display scale, tabular. */
function CountUpHa({ value, reduce }: { value: number; reduce: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduce) {
      el.textContent = value.toFixed(2);
      return;
    }
    const controls = animate(0, value, {
      duration: DUR.countUp / 1000,
      ease: EASE.out,
      onUpdate: (v) => {
        el.textContent = v.toFixed(2);
      },
    });
    return () => controls.stop();
  }, [value, reduce]);

  return (
    <span
      ref={ref}
      className="text-display tabular-nums"
      style={{ color: "var(--text-primary)", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}
    >
      {value.toFixed(2)}
    </span>
  );
}

function ReadoutRow({
  icon,
  label,
  value,
  valueColor,
  first,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  valueColor?: string;
  first?: boolean;
}) {
  return (
    <div
      className="flex items-center justify-between py-2.5"
      style={{ borderTop: first ? "1px solid var(--text-primary)" : "1px solid var(--border)" }}
    >
      <dt className="flex items-center gap-2 text-label" style={{ color: "var(--grey)" }}>
        <span className="flex w-4 justify-center" style={{ color: "var(--grey)" }}>
          {icon}
        </span>
        {label}
      </dt>
      <dd
        className="font-mono text-sm tabular-nums"
        style={{ color: valueColor ?? "var(--text-primary)" }}
      >
        {value}
      </dd>
    </div>
  );
}
