import { useState } from "react";
import { useHeatGuard } from "@/lib/heatguard-store";
import { materialIllustrationUrl, type MaterialItem } from "@/lib/materials-provider";
import { ProvenanceBadge } from "./ProvenanceBadge";
import { Check, Delivery, MediaImageList, MediaImage, Clock } from "iconoir-react";

/**
 * MaterialPassportCard (UI-SPEC §6 / EME + Concular schema, spec S9b) — the
 * reclaimed-material data spine, restyled as an IAAC field-instrument passport:
 * a 4:3 honesty-ladder banner, a mono index + name header, ONE hero datum (the
 * buying metric), a ruled tabular spec ledger (label-left / value-right), a
 * transport-carbon line, and a COLLAPSED, READ-ONLY reserve state at the bottom.
 *
 * PRODUCT TRUTH (spec S9c): **U-Shade selects and reserves the material — the
 * organizer never chooses, swaps, holds, or releases anything.** The client-facing
 * card therefore shows exactly ONE of two read-only states at the bottom — NO buttons,
 * NO decisions:
 *   (a) "Reserved for your project" (green) — when U-Shade has a hold on this archetype;
 *   (b) "Sourcing in progress" (amber) — when it's matched to a zone but not yet held.
 * Cards not selected for any accepted zone show no reserve panel — just the evidence.
 *
 * The full ReserveStateMachine (Available → Placing → Reserved → Released →
 * Double-Booked) still runs server-side; U-Shade operators use it internally. It is
 * NOT a client control here — every number travels with its provenance tier.
 */

/**
 * MaterialImage — the passport banner. Honesty ladder (never fake a real photo):
 *   1) a REAL supplier photo (item.photoUrl) — shown plain, NO badge;
 *   2) else a REPRESENTATIVE reference photo of the archetype (/materials/<id>.webp) —
 *      shown ALWAYS badged "Reference photo" (a web photo of the material TYPE, not the
 *      specific reclaimed lot, and not AI);
 *   3) else (no real photo, reference file missing → onError) an honest placeholder.
 * A missing reference file degrades to (3) via onError — never a broken image.
 */
function MaterialImage({ item }: { item: MaterialItem }) {
  const hasRealPhoto = !!item.photoUrl;
  const reference = item.illustrationUrl ?? materialIllustrationUrl(item.id);
  const initialSrc = item.photoUrl ?? reference;
  const [src, setSrc] = useState<string | null>(initialSrc);
  // Whether the currently-displayed src is the representative reference (drives the badge).
  const showingReference = !!src && !(hasRealPhoto && src === item.photoUrl);

  if (!src) {
    return (
      <div
        className="flex aspect-[4/3] items-center justify-center gap-2"
        style={{
          borderBottom: "1px solid var(--border)",
          background: "var(--muted)",
          color: "var(--grey)",
        }}
      >
        <MediaImageList className="size-4" strokeWidth={1.5} />
        <span className="font-mono text-[11px] uppercase tracking-wider">No image yet</span>
      </div>
    );
  }
  return (
    <div
      className="relative aspect-[4/3] overflow-hidden"
      style={{ borderBottom: "1px solid var(--border)", background: "var(--muted)" }}
    >
      <img
        src={src}
        alt={showingReference ? `${item.name} — reference photo` : item.name}
        loading="lazy"
        className="size-full object-cover"
        onError={() => {
          // Real photo failed → try the reference; reference failed → placeholder.
          if (hasRealPhoto && src === item.photoUrl && reference !== item.photoUrl) {
            setSrc(reference);
          } else {
            setSrc(null);
          }
        }}
      />
      {showingReference && (
        <span
          className="absolute left-2 top-2 inline-flex items-center gap-1 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider backdrop-blur-sm"
          style={{
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            background: "color-mix(in srgb, var(--black) 60%, transparent)",
            color: "var(--paper)",
          }}
        >
          <MediaImage className="size-2.5" strokeWidth={1.5} />
          Reference photo
        </span>
      )}
    </div>
  );
}

export function MaterialPassportCard({
  item,
  rank,
  onPick,
}: {
  item: MaterialItem;
  rank: number;
  /** Hover/focus → cross-highlight the matching map pin. */
  onPick?: (id: string | null) => void;
}) {
  // Reference catalogue entry = real sourced specs but no live stock yet.
  const isReference = item.bindable === false;

  // Per-spec provenance helpers (fallback DECLARED — honest, never UNLABELLED-by-omission).
  const prov = (f: string): "GROUNDED" | "DERIVED" | "ASSUMED" | "DECLARED" =>
    (item.provenance?.[f] as "GROUNDED" | "DERIVED" | "ASSUMED" | "DECLARED") ?? "DECLARED";
  const src = (f: string): string | undefined => item.provenanceSources?.[f];

  // Source status pill (the "Uber for Materials" trust axis) — one deliberate status,
  // top-right, colour-matched to the map pins (scrape=teal/live, onboarded=amber,
  // reference=ghost). Sharp corners, mono label — instrument, not SaaS chip.
  const sourcePill =
    item.bindSource === "scrape"
      ? { label: "Live stock", color: "var(--teal)" }
      : item.bindSource === "onboarded"
        ? { label: "Supplier-listed", color: "var(--amber)" }
        : { label: "Reference", color: "var(--grey)" };

  const costFree = item.costPerUnit === 0;

  // The hero datum — the single number the organiser reviews on, large enough to read
  // across the table. Cooling for membranes, clear span for structure, else role.
  const hero =
    item.shadePct != null
      ? { value: `${item.shadePct}`, suffix: "%", label: "shade", tier: prov("solarTransmissivity"), tip: src("solarTransmissivity") }
      : item.maxSpanMeters != null
        ? { value: `${item.maxSpanMeters}`, suffix: "m", label: "clear span", tier: prov("maxSpanMeters"), tip: src("maxSpanMeters") }
        : { value: item.type === "struct" ? "Frame" : "Cover", suffix: "", label: "role", tier: "GROUNDED" as const, tip: undefined };

  // Quiet support metrics under the hero (distance · cost). GROUNDED = silent default.
  const support = [
    { k: "Distance", v: item.distanceKm != null ? `${Math.round(item.distanceKm * 10) / 10} km` : "—", tier: prov("distanceKm"), tip: "Road route to site" },
    { k: costFree ? "Cost · reclaim" : "Cost", v: costFree ? "Free" : item.costPerUnit != null ? `€${item.costPerUnit}` : "—", tier: prov("costPerUnit"), tip: src("costPerUnit") },
  ];

  return (
    <article
      onMouseEnter={() => onPick?.(item.id)}
      onMouseLeave={() => onPick?.(null)}
      className="overflow-hidden transition-colors"
      style={{
        borderTop: "1px solid var(--border)",
        borderRight: "1px solid var(--border)",
        borderBottom: "1px solid var(--border)",
        borderLeft: "3px solid var(--teal)",
        borderRadius: "var(--radius-sm)",
        background: "var(--surface)",
      }}
    >
      <MaterialImage item={item} />
      <div className="p-4">
        {/* Header: mono rank index · name · type · source-status pill (top-right). */}
        <div className="flex items-start gap-2.5">
          <span
            className="mt-0.5 font-mono text-[11px] font-bold tabular-nums"
            style={{ color: "var(--grey)" }}
          >
            {String(rank).padStart(2, "0")}
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-subhead truncate" style={{ color: "var(--text-primary)" }}>
              {item.name}
            </h3>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="truncate text-[11px]" style={{ color: "var(--text-muted)" }}>
                {item.supplier}
              </span>
              <span className="font-mono text-[9px] uppercase tracking-[0.12em]" style={{ color: "var(--grey)" }}>
                {item.type === "struct" ? "Structural" : "Membrane"}
              </span>
            </p>
          </div>
          <span
            className="inline-flex shrink-0 items-center gap-1.5 px-2 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-[0.1em]"
            style={{
              border: `1px solid ${sourcePill.color}`,
              borderRadius: "var(--radius-sm)",
              color: sourcePill.color,
            }}
          >
            <span className="size-1.5 rounded-full" style={{ background: sourcePill.color }} />
            {sourcePill.label}
          </span>
        </div>

        {/* HERO DATUM — the buying number, big. Quiet support (distance · cost) beside it.
            Exception tiers badged; GROUNDED stays silent. */}
        <div
          className="mt-3.5 flex items-end justify-between gap-3 pb-3.5"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div>
            <div className="flex items-baseline gap-1">
              <span
                className="text-display leading-none tabular-nums"
                style={{ color: "var(--text-primary)", fontSize: "clamp(2rem,5vw,2.6rem)" }}
              >
                {hero.value}
              </span>
              {hero.suffix && (
                <span className="font-mono text-base" style={{ color: "var(--grey)" }}>
                  {hero.suffix}
                </span>
              )}
              {hero.tier !== "GROUNDED" && <ProvenanceBadge tier={hero.tier} source={hero.tip} compact className="self-start" />}
            </div>
            <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: "var(--grey)" }}>
              {hero.label}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1.5 pb-1">
            {support.map((m) => (
              <div key={m.k} className="flex items-center gap-1.5">
                <span className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--grey)" }}>
                  {m.k}
                </span>
                <span className="font-mono text-sm tabular-nums" style={{ color: "var(--text-primary)" }}>
                  {m.v}
                </span>
                {m.tier !== "GROUNDED" && <ProvenanceBadge tier={m.tier} source={m.tip} compact />}
              </div>
            ))}
          </div>
        </div>

        {/* One-line trust summary — confident default. */}
        <p className="mt-3 flex items-center gap-1.5 font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
          <Check className="size-3.5 shrink-0" style={{ color: "var(--green)" }} strokeWidth={2.5} />
          Datasheet-sourced
          {(item.listingCount ?? 0) > 1 && (
            <span className="ml-auto" style={{ color: "var(--grey)" }}>
              {item.listingCount} listings · {item.supplierCount} supplier{item.supplierCount === 1 ? "" : "s"}
            </span>
          )}
        </p>

        {/* Spec ledger — ruled rows, label-left / value-right, tabular. Exceptions badged. */}
        <dl className="mt-3">
          <SpecRow k="Stock" tier={item.quantity != null ? item.quantityTier : undefined}>
            {item.quantity != null ? `${item.quantity.toLocaleString()} ${item.unit}` : "Not stated"}
          </SpecRow>
          {item.unitMassKg != null && (
            <SpecRow k="Mass" tier={prov("unitMassKg")} tip={src("unitMassKg")}>
              {item.unitMassKg} kg/{item.unit}
            </SpecRow>
          )}
          {item.thicknessMm != null && (
            <SpecRow k="Thickness" tier={prov("thicknessMm")} tip={src("thicknessMm")}>
              {item.thicknessMm} mm
            </SpecRow>
          )}
          {item.shadePct != null && (
            <SpecRow k="Solar transmissivity τ" tier={prov("solarTransmissivity")} tip={src("solarTransmissivity")}>
              {item.solarTransmissivity}
            </SpecRow>
          )}
          {item.maxSpanMeters != null && (
            <SpecRow k="Max span" tier={prov("maxSpanMeters")} tip={src("maxSpanMeters")}>
              {item.maxSpanMeters} m
            </SpecRow>
          )}
          <SpecRow k="Origin">{item.origin}</SpecRow>
        </dl>

        {/* Transport carbon — always shown, always ASSUMED (transport-only). */}
        <div
          className="mt-3 flex items-center gap-1.5 px-2.5 py-2 font-mono text-[11px]"
          style={{
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            background: "var(--muted)",
            color: "var(--text-muted)",
          }}
        >
          <Delivery className="size-3.5 shrink-0" strokeWidth={1.5} />
          {item.transportCarbonKg != null ? (
            <span>~<span className="tabular-nums">{item.transportCarbonKg}</span> kgCO₂e transport</span>
          ) : item.transportCarbonPerUnitKg != null ? (
            <span>~<span className="tabular-nums">{item.transportCarbonPerUnitKg}</span> kgCO₂e per {item.unit} transport</span>
          ) : (
            <span>Transport carbon not stated</span>
          )}
          <ProvenanceBadge tier="ASSUMED" source="Transport-only · manufacturing = 0" compact className="ml-auto" />
        </div>

        {/* Availability note — honest, read-only. The architect selects from this stock
            when designing; nothing is reserved here. */}
        {isReference && (
          <p className="mt-3.5 flex items-start gap-1.5 font-mono text-[11px] leading-relaxed" style={{ color: "var(--grey)" }}>
            <Clock className="mt-0.5 size-3 shrink-0" strokeWidth={1.5} />
            Reference spec — real datasheet numbers, no live stock yet. Sourceable once a
            supplier onboards this reclaimed stream.
          </p>
        )}
      </div>
    </article>
  );
}

/** One spec row: label left, value right (tabular), badge only when it's an exception
 * (non-GROUNDED). GROUNDED is the silent default — the marketplace's datasheet promise. */
function SpecRow({
  k,
  tier,
  tip,
  children,
}: {
  k: string;
  tier?: "GROUNDED" | "DERIVED" | "ASSUMED" | "DECLARED";
  tip?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="flex items-center justify-between gap-3 py-1.5"
      style={{ borderBottom: "1px dashed var(--border)" }}
    >
      <dt className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--grey)" }}>
        {k}
      </dt>
      <dd className="flex items-center gap-1.5">
        <span className="font-mono text-[13px] tabular-nums" style={{ color: "var(--text-primary)" }}>
          {children}
        </span>
        {tier && tier !== "GROUNDED" && <ProvenanceBadge tier={tier} source={tip} compact />}
      </dd>
    </div>
  );
}
