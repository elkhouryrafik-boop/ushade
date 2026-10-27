import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { useHeatGuard } from "@/lib/heatguard-store";
import { getMaterialsProvider } from "@/lib/materials-provider";
import { recommendMaterials, type MaterialScore } from "@/lib/materials-recommend";
import { useMapCanvas } from "../PersistentMapCanvas";
import { MaterialPassportCard } from "../MaterialPassportCard";
import { MaterialsLocationsMap } from "../MaterialsLocationsMap";
import { PixelMark } from "../PixelMark";
import { EASE } from "@/lib/motion";
import { Leaf, Sparks, Coins, Snow, Packages, SendDiagonal, MapsArrow } from "iconoir-react";

/**
 * S9 — Materials, rebuilt Airbnb-style: a full-bleed TWO-PANE split.
 *
 *   LEFT  — a scrollable column of MaterialPassportCards: a RECOMMENDED (3–5) section
 *           on top (U-Shade's shortlist ranked on cost · CO₂ · assembly, each with its
 *           `why`), then the rest of the local reclaimed catalogue, browsable.
 *   RIGHT — a self-contained Mapbox map (MaterialsLocationsMap) pinning every source's
 *           true location around Parc del Fòrum.
 *
 * Hover/focus a card ↔ its map pin lifts + brightens (and vice-versa) — Airbnb-style
 * cross-highlight via a single shared `hovered` id.
 *
 * CONTENT MODEL (owner directive): the client REVIEWS the locally-available reclaimed
 * stock; U-Shade RECOMMENDS the 3–5 shortlist. No per-zone selection, no holds/reserve,
 * no "U-Shade selected" wording beyond the recommendation framing. Materials are shown
 * BY LOCATION, not as a shop — cost is only a recommendation axis.
 *
 * Dark theme: the whole screen reads dark. We scope `data-theme="dark"` on our own root
 * so the dark tokens apply regardless of the shell's setting; text uses --text-primary /
 * --paper (correct on dark), the map uses mapbox dark-v11.
 *
 * Map state: the shared PersistentMapCanvas sits hidden under this full-page document.
 * We clear its layers/UI once on mount so its shared state never holds a stale layer —
 * but the visible map here is the self-contained MaterialsLocationsMap, not that canvas.
 */

// Parc del Fòrum centroid — hub when no boundary is drawn.
const FORUM_CENTER: [number, number] = [2.2275, 41.4065];

export function MaterialsStage() {
  const { state, dispatch } = useHeatGuard();
  const { setLayers, setLayerUI } = useMapCanvas();
  const reduce = useReducedMotion();
  const [hovered, setHovered] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["catalogue"],
    queryFn: () => getMaterialsProvider().queryCatalogue(),
  });

  const items = useMemo(() => data?.items ?? [], [data]);

  // Site center from the drawn boundary if present, else the Fòrum default.
  const siteCenter = useMemo((): [number, number] => {
    const boundary = state.project.shapes.find((s) => s.kind === "boundary" && s.points.length >= 3);
    if (!boundary) return FORUM_CENTER;
    const lons = boundary.points.map((p) => p[0]);
    const lats = boundary.points.map((p) => p[1]);
    return [
      lons.reduce((a, b) => a + b, 0) / lons.length,
      lats.reduce((a, b) => a + b, 0) / lats.length,
    ];
  }, [state.project.shapes]);

  // The WHOLE live-scraped haul — every distinct supplier listing, region-wide (far
  // stock included on purpose). Separate from the curated catalogue above.
  const { data: liveData } = useQuery({
    queryKey: ["live-listings", siteCenter[0], siteCenter[1]],
    queryFn: () => getMaterialsProvider().queryLiveListings({ center: siteCenter }),
  });
  const liveItems = useMemo(() => liveData?.items ?? [], [liveData]);

  // ── U-Shade recommendation: the 3–5 shortlist on cost · CO₂ · assembly. ──
  const recommended: MaterialScore[] = useMemo(
    () => recommendMaterials(items),
    [items],
  );
  const recommendedIds = useMemo(
    () => new Set(recommended.map((r) => r.item.id)),
    [recommended],
  );
  const rankById = useMemo(
    () => new Map(recommended.map((r, i) => [r.item.id, i + 1])),
    [recommended],
  );

  // Merged source set = curated catalogue + live-scraped sources, de-duped by id (owner:
  // merge the two into ONE list, 2026-06-25). The screen masthead, the browse list, and
  // the map all read this single set.
  const allItems = useMemo(() => {
    const seen = new Set(items.map((m) => m.id));
    return [...items, ...liveItems.filter((m) => !seen.has(m.id))];
  }, [items, liveItems]);
  const mapItems = allItems; // the map pins the full merged set

  // Everything not in the shortlist — the browsable remainder (catalogue + live scraped).
  const rest = useMemo(
    () => allItems.filter((m) => !recommendedIds.has(m.id)),
    [allItems, recommendedIds],
  );

  // Farthest source across the merged set — the span the palette covers (owner wants the
  // RANGE, not the nearest). Live stock pushes this out to ~30 km. Per-item carbon is
  // unchanged — it's computed from each item's own distance, not this label.
  const farthestKm = useMemo(() => {
    const ds = allItems.map((m) => m.distanceKm).filter((d): d is number => d != null);
    return ds.length ? Math.round(Math.max(...ds)) : null;
  }, [allItems]);

  // The persistent (hidden) canvas: clear its layers/UI once so nothing downstream
  // holds a stale material-pin layer. The visible map is the self-contained one below.
  useEffect(() => {
    setLayers([]);
    setLayerUI({ rows: [], onToggle: () => {} });
  }, [setLayers, setLayerUI]);

  const reveal = (i: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 14 },
          whileInView: { opacity: 1, y: 0 },
          viewport: { once: true, margin: "-40px" },
          transition: { delay: i * 0.04, duration: 0.45, ease: EASE.out },
        };

  return (
    // Scope dark tokens to this screen so it reads dark regardless of the shell setting.
    <div
      data-theme="dark"
      className="flex h-screen w-full flex-col lg:flex-row"
      style={{ background: "var(--bg)", color: "var(--text-primary)" }}
    >
      {/* ░░ LEFT PANE — masthead + recommended shortlist + browsable catalogue ░░ */}
      <div className="flex min-h-0 w-full flex-col lg:w-[clamp(440px,46%,680px)]">
        {/* Masthead — sticky-feel header band with the IAAC pixel motif. */}
        <header
          className="shrink-0 px-7 pb-5 pt-7"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}
        >
          <div className="flex items-center gap-2.5">
            <PixelMark tone="paper" cell={4} gap={2} />
            <Kicker icon={<Leaf className="size-3" strokeWidth={1.5} />}>05 · Materials</Kicker>
          </div>
          <h1
            className="mt-3 font-sans"
            style={{
              color: "var(--text-primary)",
              fontSize: "clamp(1.9rem, 4vw, 2.9rem)",
              fontWeight: 700,
              lineHeight: 0.95,
              letterSpacing: "-0.02em",
            }}
          >
            Reclaimed stock,
            <br />
            mapped around the site
          </h1>
          <p
            className="mt-3.5 text-sm leading-relaxed"
            style={{ color: "var(--text-muted)", maxWidth: "54ch" }}
          >
            Every reclaimed material near Parc del Fòrum, placed on the map by its true
            source. U-Shade recommends the strongest 3–5 below — ranked
            on cost, CO₂ and ease of assembly. The architect designs your shade from this
            local palette; nothing is reserved here.
          </p>

          {/* Twin hero data — total sources (catalogue + live) + the distance they span. */}
          <div
            className="mt-5 flex items-stretch"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            <HeroDatum
              value={allItems.length > 0 ? String(allItems.length).padStart(2, "0") : "—"}
              label="sources mapped"
            />
            <span style={{ width: 1, background: "var(--border)" }} aria-hidden />
            <HeroDatum
              value={farthestKm != null ? String(farthestKm) : "—"}
              unit={farthestKm != null ? "km" : undefined}
              label="to the farthest"
              padded
            />
          </div>
        </header>

        {/* Scroll region — recommended shortlist, then the rest of the catalogue. */}
        <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
          {isLoading ? (
            <div className="grid grid-cols-1 gap-5">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-72 animate-pulse"
                  style={{ background: "var(--surface)", borderRadius: "var(--radius-sm)" }}
                />
              ))}
            </div>
          ) : items.length === 0 ? (
            <EmptyState />
          ) : (
            <>
              {/* ── RECOMMENDED (3–5) ── */}
              {recommended.length > 0 && (
                <section>
                  <div className="flex items-center gap-2">
                    <Sparks className="size-3.5" strokeWidth={1.6} style={{ color: "var(--green2)" }} />
                    <Kicker>Recommended · {recommended.length} of {allItems.length}</Kicker>
                    <span className="ml-auto flex items-center gap-1.5">
                      <PixelMark tone="paper" cell={3} gap={2} />
                    </span>
                  </div>

                  <ol className="mt-5 grid grid-cols-1 gap-5">
                    {recommended.map((r, i) => (
                      <motion.li key={r.item.id} {...reveal(i)} className="list-none">
                        <RecommendedCard
                          score={r}
                          rank={i + 1}
                          active={hovered === r.item.id}
                          onPick={setHovered}
                        />
                      </motion.li>
                    ))}
                  </ol>
                </section>
              )}

              {/* ── EVERY OTHER SOURCE — curated catalogue + live scraped, one merged list ── */}
              {rest.length > 0 && (
                <section className="mt-10">
                  <div className="flex items-center gap-2">
                    <Packages className="size-3.5" strokeWidth={1.6} style={{ color: "var(--grey)" }} />
                    <Kicker>Also available · {rest.length}</Kicker>
                  </div>
                  {liveItems.length > 0 && liveData?.rawCount != null && liveData?.listingCount != null && (
                    <p
                      className="mt-1.5 font-mono text-[10.5px] leading-relaxed"
                      style={{ color: "var(--grey)", maxWidth: "60ch" }}
                    >
                      Includes {liveItems.length} live-scraped sources — {liveData.rawCount} raw
                      listings ({liveData.listingCount} after variant-dedup) grouped to {liveItems.length}{" "}
                      materials. A card's listing count is how much of that material is around;
                      far stock is included on purpose.
                    </p>
                  )}
                  <div className="mt-4 grid grid-cols-1 gap-5">
                    {rest.map((m, i) => (
                      <motion.div
                        key={m.id}
                        {...reveal(i)}
                        className={hovered === m.id ? "mlm-card-active" : undefined}
                        style={
                          hovered === m.id
                            ? { outline: "2px solid var(--teal)", outlineOffset: 2, borderRadius: "var(--radius-sm)" }
                            : undefined
                        }
                      >
                        <MaterialPassportCard item={m} rank={i + 1} onPick={setHovered} />
                      </motion.div>
                    ))}
                  </div>
                </section>
              )}

              <p
                className="mt-8 font-mono text-[10.5px] leading-relaxed"
                style={{ color: "var(--grey)", maxWidth: "60ch" }}
              >
                Specs come from real datasheets and EPDs; distances are OSRM road routes to
                the site. The architect selects from this local reclaimed stock when designing
                your shade.
              </p>

              {/* CTA — hand the palette to the architect. */}
              <button
                type="button"
                className="mt-5 flex h-12 w-full items-center justify-center gap-2 font-sans font-bold transition-opacity hover:opacity-90"
                style={{
                  background: "var(--green)",
                  color: "var(--paper)",
                  borderRadius: "var(--radius-sm)",
                  letterSpacing: "0.04em",
                  fontSize: "0.9rem",
                }}
                onClick={() => dispatch({ type: "setStage", stage: "handoff" })}
              >
                Send the architect brief
                <SendDiagonal className="size-4" strokeWidth={2} />
              </button>
              <p className="mt-2 text-center font-mono text-[10px]" style={{ color: "var(--grey)" }}>
                The brief carries this palette as the reclaimed stock to design from.
              </p>
            </>
          )}
        </div>
      </div>

      {/* ░░ RIGHT PANE — the locations map (sticky full-height) ░░ */}
      <div
        className="relative min-h-[340px] w-full flex-1 lg:min-h-0"
        style={{ borderLeft: "1px solid var(--border)" }}
      >
        <MaterialsLocationsMap
          items={mapItems}
          siteCenter={siteCenter}
          recommendedIds={recommendedIds}
          rankById={rankById}
          hoveredId={hovered}
          onHover={setHovered}
        />
      </div>
    </div>
  );
}

/** A recommended pick: the passport card wrapped with a rank chip + a why-ribbon
 * (cost · CO₂ · assembly read). REVIEW-only — no actions. */
function RecommendedCard({
  score,
  rank,
  active,
  onPick,
}: {
  score: MaterialScore;
  rank: number;
  active: boolean;
  onPick: (id: string | null) => void;
}) {
  return (
    <div
      className="relative"
      style={
        active
          ? { outline: "2px solid var(--green2)", outlineOffset: 2, borderRadius: "var(--radius-sm)" }
          : undefined
      }
    >
      {/* Rank chip — overlaps the card's top-left corner. */}
      <span
        className="absolute -left-1.5 -top-2.5 z-10 flex items-center gap-1 px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.1em]"
        style={{
          background: "var(--green2)",
          color: "var(--black)",
          borderRadius: "var(--radius-sm)",
          boxShadow: "0 4px 12px -4px rgba(0,0,0,0.6)",
        }}
      >
        <Sparks className="size-2.5" strokeWidth={2} />
        Pick {rank}
      </span>

      <MaterialPassportCard item={score.item} rank={rank} onPick={onPick} />

      {/* Why-ribbon — the three honest recommendation axes + the rationale. */}
      <div
        className="mt-px flex flex-col gap-2 px-3.5 py-3"
        style={{
          background: "color-mix(in srgb, var(--green2) 10%, var(--surface))",
          borderRightWidth: "1px",
          borderRightStyle: "solid",
          borderRightColor: "color-mix(in srgb, var(--green2) 32%, var(--border))",
          borderBottomWidth: "1px",
          borderBottomStyle: "solid",
          borderBottomColor: "color-mix(in srgb, var(--green2) 32%, var(--border))",
          borderLeftWidth: "1px",
          borderLeftStyle: "solid",
          borderLeftColor: "color-mix(in srgb, var(--green2) 32%, var(--border))",
          borderBottomLeftRadius: "var(--radius-sm)",
          borderBottomRightRadius: "var(--radius-sm)",
        }}
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <AxisRead icon={<Coins className="size-3" strokeWidth={1.6} />} label="Cost" v={score.cost} />
          <AxisRead icon={<Snow className="size-3" strokeWidth={1.6} />} label="CO₂" v={score.co2} />
          <AxisRead icon={<MapsArrow className="size-3" strokeWidth={1.6} />} label="Assembly" v={score.assembly} />
          <span
            className="ml-auto font-mono text-[10px] tabular-nums"
            style={{ color: "var(--green2)" }}
          >
            score {Math.round(score.score * 100)}
          </span>
        </div>
        <p className="font-mono text-[10.5px] leading-snug" style={{ color: "var(--text-muted)" }}>
          Why: {score.why}.
        </p>
      </div>
    </div>
  );
}

/** One recommendation axis: icon + label + a 4-pip score read (0–1 → 0–4 pips). */
function AxisRead({ icon, label, v }: { icon: React.ReactNode; label: string; v: number }) {
  const pips = Math.max(0, Math.min(4, Math.round(v * 4)));
  return (
    <span className="flex items-center gap-1.5">
      <span style={{ color: "var(--grey)" }}>{icon}</span>
      <span className="font-mono text-[10px] uppercase tracking-[0.08em]" style={{ color: "var(--grey)" }}>
        {label}
      </span>
      <span className="flex items-center gap-0.5" aria-label={`${label} score ${pips} of 4`}>
        {[0, 1, 2, 3].map((p) => (
          <span
            key={p}
            className="inline-block size-1.5"
            style={{
              borderRadius: 999,
              background: p < pips ? "var(--green2)" : "color-mix(in srgb, var(--grey) 35%, transparent)",
            }}
          />
        ))}
      </span>
    </span>
  );
}

/** Mono kicker — uppercase, tracked, optional leading icon. */
function Kicker({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <p
      className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase"
      style={{ color: "var(--grey)", letterSpacing: "0.14em" }}
    >
      {icon}
      {children}
    </p>
  );
}

/** Compact hero datum for the masthead band. */
function HeroDatum({
  value,
  unit,
  label,
  padded,
}: {
  value: string;
  unit?: string;
  label: string;
  padded?: boolean;
}) {
  return (
    <div className="flex-1 py-3" style={padded ? { paddingLeft: "1.25rem" } : undefined}>
      <div className="flex items-baseline gap-1.5">
        <span
          className="font-sans tabular-nums"
          style={{
            color: "var(--text-primary)",
            fontSize: "clamp(2.2rem, 6vw, 3.2rem)",
            fontWeight: 700,
            lineHeight: 0.85,
            letterSpacing: "-0.03em",
          }}
        >
          {value}
        </span>
        {unit && (
          <span className="font-sans" style={{ color: "var(--grey)", fontSize: "1rem", fontWeight: 500 }}>
            {unit}
          </span>
        )}
      </div>
      <p className="mt-1.5 font-mono text-[10px] uppercase" style={{ color: "var(--grey)", letterSpacing: "0.1em" }}>
        {label}
      </p>
    </div>
  );
}

/** Honest empty state — U-Shade never shows material it can't source. */
function EmptyState() {
  return (
    <div
      className="px-6 py-12 text-center"
      style={{ border: "1px dashed var(--border)", borderRadius: "var(--radius-sm)" }}
    >
      <p className="font-sans text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
        No reclaimed materials near this site yet
      </p>
      <p
        className="mx-auto mt-2 text-sm leading-relaxed"
        style={{ color: "var(--text-muted)", maxWidth: "46ch" }}
      >
        U-Shade never shows material it can't source. As suppliers onboard their reclaimed
        stock nearby, this map and shortlist fill in.
      </p>
    </div>
  );
}
