import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { useHeatGuard } from "@/lib/heatguard-store";
import { getMaterialsProvider, materialIllustrationUrl } from "@/lib/materials-provider";
import { recommendMaterials } from "@/lib/materials-recommend";
import {
  getStructureZones,
  getFestivalSchema,
  getHeatArtifact,
  getAcceptance,
} from "@/lib/heatguard-api";
import { schemaPoints, nearestFeature } from "@/lib/festival-schema-layers";
import { downloadHeatShadePlan } from "../HeatShadePlanPdf";
import { useMapCanvas } from "../PersistentMapCanvas";
import { PixelMark } from "../PixelMark";
import { Checkbox } from "@/components/ui/checkbox";
import {
  ShieldAlt,
  Check,
  Download,
  ArrowLeft,
  CalendarCheck,
  SunLight,
  Packages,
} from "iconoir-react";
import { EASE, DUR } from "@/lib/motion";

/**
 * S10+S11 MERGED — "The Plan": the single editorial deliverable (owner, 2026-06-24).
 *
 * Handoff (the architect's brief) and Report (the receipt) are now ONE scrolling
 * editorial column — the one document the organiser keeps and the architect builds from.
 * Rendered on the DARK deliverable surface (WizardShell sets data-theme="dark" for this
 * stage), centered in a max-w-3xl column. Tokens only, so the stark-white editorial
 * design re-points cleanly onto dark: headlines/rules use --text-primary (was --ink),
 * body uses --text-muted, accents are rationed (green = relief / primary action).
 *
 * Sections (top→bottom):
 *   Masthead "The Plan" (PixelMark accent)
 *   Hero datum — % of in-heat crowd now under shade (HONEST pctShaded; no fabricated before/after)
 *   01 · The structures to design — rank · near X · coverage target · orientation (NO m²/footprint)
 *   02 · Creative direction — the project theme
 *   03 · Recommended materials (3–5) — recommendMaterials() on the catalogue, with `why` + thumb
 *   04 · Timeline
 *   05 · Why it holds up — the defence + a qualitative receipt (NO price)
 *   Action block — Download plan PDF (no cost) · acknowledgement gate · Request architect design
 *   Colophon — the method line
 *
 * NO PRICE anywhere (the service fee is handled separately). No worst-hour language; no
 * provenance pills. Cooling comes from the real Phase-5b acceptance gate (utci_delta_c).
 */

const TRUST_COPY =
  "These placements are a climate-and-crowd decision aid. Any built structure requires sign-off by a licensed structural engineer and on-site safety review before construction.";
const ACK_COPY =
  "I understand these are indicative placements requiring licensed engineering sign-off.";

// Worked-fixture milestones — the deadline drives sourcing + fabrication lead time.
const TIMELINE: { phase: string; label: string; date: string }[] = [
  { phase: "01", label: "Design due", date: "12 Jul" },
  { phase: "02", label: "Source + fabricate", date: "20 Jul" },
  { phase: "03", label: "Install", date: "28 Jul" },
  { phase: "04", label: "Event", date: "30 Jul" },
];
const DAYS_TO_DESIGN = 18;

export function HandoffStage() {
  const { state, dispatch } = useHeatGuard();
  const { setLayerUI } = useMapCanvas();
  const reduce = useReducedMotion();
  const accepted = state.acceptedRanks;
  const [ack, setAck] = useState(false);
  const [sent, setSent] = useState(false);

  // The full datasheet-sourced catalogue — same provider used everywhere. We rank it to
  // the final 3–5 recommendation (cost · CO₂ · assembly), all from real datasheet fields.
  const { data: catalogue } = useQuery({
    queryKey: ["catalogue"],
    queryFn: () => getMaterialsProvider().queryCatalogue(),
  });
  const recommended = useMemo(
    () => recommendMaterials(catalogue?.items ?? [], { min: 3, max: 5 }),
    [catalogue],
  );
  const materialCount = recommended.length;
  // Transport carbon of the recommended set (transport-only, kgCO₂e). Honest sum over
  // whatever the datasheet exposes; per-unit when a total isn't available.
  const recommendedCarbon = useMemo(
    () =>
      recommended.reduce(
        (s, r) => s + (r.item.transportCarbonKg ?? r.item.transportCarbonPerUnitKg ?? 0),
        0,
      ),
    [recommended],
  );

  const { data: zonesData } = useQuery({
    queryKey: ["zones", state.simRunId],
    queryFn: () => getStructureZones(state.simRunId!),
    enabled: state.simRunId !== null,
    staleTime: Infinity,
  });
  const { data: schema } = useQuery({
    queryKey: ["festival-schema"],
    queryFn: getFestivalSchema,
    staleTime: Infinity,
  });
  const features = useMemo(() => (schema ? schemaPoints(schema.features) : []), [schema]);
  const acceptedStructures = useMemo(
    () => (zonesData?.structures ?? []).filter((z) => accepted.includes(z.rank)),
    [zonesData, accepted],
  );
  // Hottest feels-like (for the PDF + the inputs note) — real artifact.
  const { data: heat } = useQuery({
    queryKey: ["heat", state.simRunId],
    queryFn: () => getHeatArtifact(state.simRunId!),
    enabled: state.simRunId !== null,
    staleTime: Infinity,
  });
  // Real modeled cooling from the Phase-5b acceptance gate — never hardcoded.
  const { data: acceptance } = useQuery({
    queryKey: ["acceptance", state.simRunId],
    queryFn: () => getAcceptance(state.simRunId!),
    enabled: state.simRunId !== null,
    staleTime: Infinity,
    retry: false,
  });

  // ── The honest hero metric: share of the in-heat crowd now under shade. ──────
  const totalDemand = zonesData?.total_demand ?? 0;
  const peopleShaded = Math.round(
    acceptedStructures.reduce((s, z) => s + z.marginal_demand, 0),
  );
  const pctShaded = totalDemand > 0 ? Math.round((peopleShaded / totalDemand) * 100) : 0;
  const residualPct = Math.max(0, 100 - pctShaded);
  // Real modeled cooling from the Phase-5b acceptance gate ONLY — never a fabricated
  // fallback. null when the gate hasn't reported, so the UI shows "—" not a fake number.
  const coolingC = acceptance?.utci_delta_c ?? null;

  function exportPlan() {
    // NO cost passed — the PDF helper omits the cost section when costLow/High are absent.
    downloadHeatShadePlan({
      site: "Parc del Fòrum, Barcelona",
      generatedAt: new Date().toLocaleString(),
      hottestC: heat ? Math.round(heat.utci_max_c) : 0,
      zones: acceptedStructures.map((z) => ({
        rank: z.rank,
        name: features.length ? nearestFeature(z.center, features) : null,
        coverage_pct: z.coverage_pct,
        orientation: "block the afternoon sun · SW",
      })),
      peopleInHeat: Math.round(totalDemand),
      peopleShaded,
      pctShaded,
      coolingC: coolingC ?? undefined,
      // Architect-spec materials: name + the datasheet specs the studio designs from.
      materials: recommended.map((r) => ({
        name: r.item.name,
        quantity: r.item.quantity,
        unit: r.item.unit,
        distanceKm: r.item.distanceKm,
        role: r.item.type,
        shadePct: r.item.shadePct,
        maxSpanMeters: r.item.maxSpanMeters,
        transportCarbonKg: r.item.transportCarbonKg,
        why: r.why,
      })),
      transportCarbonKg: Math.round(recommendedCarbon),
    });
  }

  useEffect(() => {
    setLayerUI({ rows: [], onToggle: () => {} });
  }, [setLayerUI]);

  // ── Empty state ───────────────────────────────────────────────────────────
  if (accepted.length === 0) {
    return (
      <div>
        <Kicker>06 · THE PLAN</Kicker>
        <h1 className="text-hero mt-3" style={{ color: "var(--text-primary)", lineHeight: 0.92 }}>
          The Plan
        </h1>
        <p className="text-editorial mt-5" style={{ color: "var(--text-muted)", maxWidth: "52ch" }}>
          The one document you keep — the brief, the relief, and the receipt in one. But there
          is nothing to commit yet.
        </p>
        <div
          className="mt-8 px-6 py-10 text-center"
          style={{ border: "1px dashed var(--border)", borderRadius: "var(--radius-sm)" }}
        >
          <p className="text-subhead" style={{ color: "var(--text-primary)" }}>
            No accepted placements
          </p>
          <p className="mx-auto mt-2 text-sm leading-relaxed" style={{ color: "var(--text-muted)", maxWidth: "44ch" }}>
            Accept at least one shade placement before commissioning the architect's design.
          </p>
        </div>
        <button
          type="button"
          className="mt-5 flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider transition-opacity hover:opacity-70"
          style={{ color: "var(--text-muted)" }}
          onClick={() => dispatch({ type: "setStage", stage: "placement" })}
        >
          <ArrowLeft className="size-3.5" strokeWidth={2} />
          Back to placements
        </button>
      </div>
    );
  }

  // ── Sent / confirmation state ─────────────────────────────────────────────
  if (sent) {
    return (
      <motion.div
        initial={reduce ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: DUR.stage / 1000, ease: EASE.out }}
      >
        <Kicker>06 · THE PLAN · SENT</Kicker>
        <div className="mt-6 flex items-baseline gap-4">
          <span
            className="flex size-12 shrink-0 items-center justify-center"
            style={{ background: "var(--green)", borderRadius: "var(--radius-sm)" }}
          >
            <Check className="size-7" style={{ color: "var(--white)" }} strokeWidth={2.5} />
          </span>
          <h1 className="text-hero" style={{ color: "var(--text-primary)", lineHeight: 0.92 }}>
            Plan on its way
          </h1>
        </div>
        <p className="text-editorial mt-6" style={{ color: "var(--text-muted)", maxWidth: "56ch" }}>
          The studio responds within three business days. Your exported plan carries the line:
          "Decision-support output — not for construction without licensed engineering review."
        </p>
        <div className="mt-8" style={{ borderTop: "2px solid var(--text-primary)" }} />
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            className="flex flex-1 items-center justify-center gap-2 py-3 font-sans font-semibold text-sm transition-opacity hover:opacity-80"
            style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-primary)" }}
            onClick={exportPlan}
          >
            <Download className="size-4" strokeWidth={1.5} />
            Download the Plan (PDF)
          </button>
          <button
            type="button"
            className="flex flex-1 items-center justify-center gap-2 py-3 font-sans font-semibold text-sm transition-opacity hover:opacity-90"
            style={{ background: "var(--green)", color: "var(--white)", borderRadius: "var(--radius-sm)" }}
            onClick={() => setSent(false)}
          >
            ← Back to the Plan
          </button>
        </div>
      </motion.div>
    );
  }

  // ── The Plan document ───────────────────────────────────────────────────────
  const nStruct = acceptedStructures.length;

  // Per-section reveal. Each section animates as it scrolls into view (its inner rows
  // carry their own stagger), so the section wrapper itself just rises once.
  const reveal = reduce
    ? {}
    : {
        initial: { opacity: 0, y: 18 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true, margin: "-72px" },
        transition: { duration: DUR.stage / 1000, ease: EASE.out },
      };

  return (
    <div>
      {/* ░░ MASTHEAD ░░ */}
      <motion.header
        initial={reduce ? false : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: DUR.stage / 1000, ease: EASE.out }}
      >
        <div className="flex items-center gap-2.5">
          <PixelMark tone="paper" cell={4} gap={2} />
          <Kicker>06 · THE PLAN · CLIMATE × CROWD DELIVERABLE</Kicker>
        </div>
        <h1 className="text-hero mt-4" style={{ color: "var(--text-primary)", lineHeight: 0.9 }}>
          The Plan
        </h1>
        <p className="text-editorial mt-7" style={{ color: "var(--text-muted)", maxWidth: "58ch" }}>
          The one document you keep — the brief, the relief, and the receipt in one. Everything
          the architect needs to design, everything the safety group needs to sign off, and
          nothing the architect doesn't own.
        </p>

        {/* Hero datum — the HONEST metric: share of the in-heat crowd now under shade. */}
        <div className="mt-12 grid grid-cols-2" style={{ borderTop: "2px solid var(--text-primary)" }}>
          <HeroDatum
            value={`${pctShaded}`}
            unit="%"
            label="of the in-heat crowd now under shade"
            accent="var(--green)"
            reduce={!!reduce}
            delay={0.1}
          />
          <HeroDatum
            value={String(nStruct).padStart(2, "0")}
            label={`structure${nStruct === 1 ? "" : "s"} to design`}
            reduce={!!reduce}
            delay={0.18}
            borderLeft
          />
        </div>
        <p className="mt-3 text-editorial" style={{ color: "var(--text-muted)", maxWidth: "58ch" }}>
          ~{peopleShaded.toLocaleString()} people moved under shade
          {coolingC !== null && (
            <>
              , about{" "}
              <span style={{ color: "var(--text-primary)" }}>{coolingC.toFixed(1)} °C cooler</span> on
              the covered crowd
            </>
          )}
          . The remaining {residualPct}% the shade did not reach is co-located
          with water and medical provision.
        </p>
        <p className="mt-3 font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
          Parc del Fòrum, Barcelona{state.project.date ? ` · ${state.project.date}` : ""}
        </p>
      </motion.header>

      {/* ░░ 01 · THE STRUCTURES ░░ */}
      <motion.section className="mt-20" {...reveal}>
        <Kicker>01 · The structures to design</Kicker>
        <div className="mt-6" style={{ borderTop: "1px solid var(--text-primary)" }}>
          {acceptedStructures.map((z, i) => {
            const name = features.length ? nearestFeature(z.center, features) : null;
            return (
              <motion.article
                key={z.rank}
                initial={reduce ? false : { opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-48px" }}
                transition={{ delay: i * 0.07, duration: DUR.card / 1000, ease: EASE.out }}
                className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 py-7"
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                {/* Giant rank numeral */}
                <span
                  className="font-sans tabular-nums"
                  style={{
                    color: i === 0 ? "var(--text-primary)" : "var(--grey)",
                    fontSize: "clamp(3rem, 9vw, 5.5rem)",
                    fontWeight: 700,
                    lineHeight: 0.8,
                    letterSpacing: "-0.03em",
                  }}
                >
                  {String(z.rank).padStart(2, "0")}
                </span>

                <div className="min-w-0">
                  <h3 className="text-subhead" style={{ color: "var(--text-primary)" }}>
                    {name ? `Near ${name}` : `Structure ${String(z.rank).padStart(2, "0")}`}
                  </h3>

                  <dl className="mt-3 grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
                    <Field label="Coverage target">
                      {Math.round(z.coverage_pct)}% of crowd demand
                    </Field>
                    <Field label="Orientation" icon={<SunLight className="size-3" strokeWidth={1.5} />}>
                      block the afternoon sun · SW
                    </Field>
                  </dl>
                </div>
              </motion.article>
            );
          })}
        </div>
      </motion.section>

      {/* ░░ 02 · RECOMMENDED MATERIALS (3–5) ░░ */}
      <motion.section className="mt-20" {...reveal}>
        <Kicker icon={<Packages className="size-3" strokeWidth={1.5} />}>02 · Recommended materials</Kicker>
        <div
          className="mt-6 flex items-baseline justify-between gap-4 pb-3"
          style={{ borderBottom: "1px solid var(--text-primary)" }}
        >
          <p className="text-subhead" style={{ color: "var(--text-primary)" }}>
            {materialCount > 0
              ? `${materialCount} locally-reclaimed materials, ranked for the job`
              : "Sourcing the local reclaimed stock"}
          </p>
          <span className="font-mono text-[11px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
            cost · CO₂ · assembly
          </span>
        </div>

        <div className="mt-2">
          {recommended.map((r, i) => (
            <motion.article
              key={r.item.id}
              initial={reduce ? false : { opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-48px" }}
              transition={{ delay: i * 0.06, duration: DUR.card / 1000, ease: EASE.out }}
              className="grid grid-cols-[auto_1fr_auto] items-center gap-x-5 py-5"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              {/* Archetype thumbnail — AI illustration, degrades to a token tile on error. */}
              <span
                className="relative block size-16 shrink-0 overflow-hidden"
                style={{
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border)",
                  background: "var(--surface)",
                }}
              >
                <img
                  src={r.item.illustrationUrl ?? materialIllustrationUrl(r.item.id)}
                  alt=""
                  loading="lazy"
                  className="size-full object-cover"
                  onError={(e) => {
                    (e.currentTarget as HTMLImageElement).style.visibility = "hidden";
                  }}
                />
              </span>

              <div className="min-w-0">
                <h3 className="font-sans font-semibold" style={{ color: "var(--text-primary)", fontSize: "0.98rem" }}>
                  {r.item.name}
                </h3>
                <p className="mt-1 font-mono text-[11px] uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                  {r.why}
                </p>
                {r.item.distanceKm != null && (
                  <p className="mt-0.5 font-mono text-[10px]" style={{ color: "var(--grey)" }}>
                    {r.item.type === "membr" ? "membrane" : "structure"} · ~{Math.round(r.item.distanceKm)} km away
                  </p>
                )}
              </div>

              {/* Combined recommendation score — quiet, mono, right-aligned. */}
              <span
                className="font-sans tabular-nums"
                style={{
                  color: i === 0 ? "var(--green)" : "var(--text-primary)",
                  fontSize: "clamp(1.4rem, 4vw, 2rem)",
                  fontWeight: 700,
                  lineHeight: 1,
                  letterSpacing: "-0.02em",
                }}
              >
                {Math.round(r.score * 100)}
              </span>
            </motion.article>
          ))}
        </div>
      </motion.section>

      {/* ░░ 03 · TIMELINE ░░ */}
      <motion.section className="mt-20" {...reveal}>
        <Kicker icon={<CalendarCheck className="size-3" strokeWidth={1.5} />}>03 · Timeline</Kicker>
        <div className="mt-6" style={{ borderTop: "1px solid var(--text-primary)" }}>
          {TIMELINE.map((t, i) => (
            <motion.div
              key={t.phase}
              initial={reduce ? false : { opacity: 0, x: -8 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: "-48px" }}
              transition={{ delay: i * 0.07, duration: DUR.card / 1000, ease: EASE.out }}
              className="grid grid-cols-[auto_1fr_auto] items-baseline gap-4 py-4"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <span className="font-mono text-[11px]" style={{ color: i === 0 ? "var(--green)" : "var(--text-muted)" }}>
                {t.phase}
              </span>
              <span
                className="font-sans"
                style={{ color: "var(--text-primary)", fontWeight: i === 0 ? 700 : 500, fontSize: "clamp(0.95rem, 1.6vw, 1.15rem)" }}
              >
                {t.label}
              </span>
              <span
                className="font-sans tabular-nums"
                style={{ color: i === 0 ? "var(--text-primary)" : "var(--grey)", fontSize: "clamp(1.3rem, 3vw, 2rem)", fontWeight: 700, lineHeight: 1, letterSpacing: "-0.02em" }}
              >
                {t.date}
              </span>
            </motion.div>
          ))}
        </div>
        <p className="mt-3 font-mono text-[11px] leading-relaxed" style={{ color: "var(--text-muted)", maxWidth: "60ch" }}>
          The design deadline drives everything downstream — sourcing the reclaimed stock and the
          fabrication lead time both key off 12 Jul.
        </p>
      </motion.section>

      {/* ░░ 04 · THE RECEIPT — what it did, no money. Four honest figures. ░░ */}
      <motion.section className="mt-20" {...reveal}>
        <Kicker icon={<ShieldAlt className="size-3" strokeWidth={1.5} />}>04 · The receipt</Kicker>
        <div className="mt-6 grid grid-cols-2 gap-px sm:grid-cols-4" style={{ background: "var(--border)" }}>
          <Receipt value={peopleShaded.toLocaleString()} label="people shaded" accent="var(--green)" />
          <Receipt value={coolingC !== null ? `~${coolingC.toFixed(1)}` : "—"} unit={coolingC !== null ? "°C" : ""} label="cooler, covered crowd" />
          <Receipt value={`${Math.round(recommendedCarbon).toLocaleString()}`} unit="kg" label="transport CO₂e" />
          <Receipt value={String(materialCount || "—")} label="reclaimed materials" />
        </div>
        <p className="mt-3 font-mono text-[10px] leading-relaxed" style={{ color: "var(--grey)", maxWidth: "60ch" }}>
          Modeled, not measured. The service fee is quoted separately and is not part of this plan.
        </p>
      </motion.section>

      {/* ░░ ACTION BLOCK ░░ */}
      <motion.section className="mt-16" {...reveal}>
        {/* PDF export — carries NO cost. */}
        <button
          type="button"
          className="flex w-full items-center justify-center gap-2 py-3 font-sans font-semibold text-sm transition-opacity hover:opacity-80"
          style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-primary)" }}
          onClick={exportPlan}
        >
          <Download className="size-4" strokeWidth={1.5} />
          Download the Plan (PDF)
        </button>
        <p className="mt-1.5 text-center font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
          One-page summary for the safety plan, licensing authority, or insurer.
        </p>

        {/* Trust strip */}
        <div
          className="mt-6 flex items-start gap-3 px-4 py-3.5"
          style={{
            borderLeft: "3px solid var(--amber)",
            background: "color-mix(in srgb, var(--amber) 12%, transparent)",
          }}
        >
          <ShieldAlt className="mt-0.5 size-4 shrink-0" style={{ color: "var(--amber)" }} strokeWidth={1.5} />
          <p className="font-mono text-[11px] leading-relaxed" style={{ color: "var(--text-primary)" }}>
            {TRUST_COPY}
          </p>
        </div>

        {/* Acknowledgement gate */}
        <label
          className="mt-3 flex cursor-pointer items-start gap-3 px-4 py-3.5"
          style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)" }}
        >
          <Checkbox checked={ack} onCheckedChange={(v) => setAck(!!v)} className="mt-0.5" />
          <span className="font-sans text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
            {ACK_COPY}
          </span>
        </label>

        {/* Primary CTA */}
        <button
          type="button"
          disabled={!ack}
          className="mt-4 flex h-12 w-full items-center justify-center font-sans font-bold tracking-wide transition-opacity hover:opacity-90 disabled:opacity-40"
          style={{
            background: ack ? "var(--green)" : "var(--grey)",
            color: "var(--white)",
            borderRadius: "var(--radius-sm)",
            letterSpacing: "0.04em",
            fontSize: "0.9rem",
          }}
          onClick={() => setSent(true)}
        >
          Request architect design
        </button>
        {!ack && (
          <p className="mt-2 text-center font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
            Tick the acknowledgement to send.
          </p>
        )}
      </motion.section>

      {/* ░░ COLOPHON — the method, the standing line ░░ */}
      <motion.footer className="mt-16 pt-6" {...reveal} style={{ borderTop: "2px solid var(--text-primary)" }}>
        <div className="flex items-start gap-3">
          <PixelMark tone="paper" cell={3} gap={1.5} className="mt-1" />
          <p className="text-editorial" style={{ color: "var(--text-muted)", maxWidth: "60ch" }}>
            The site boundary you drew → a real infrared.city heat grid → crowd flow simulated
            across the day → the hottest, busiest spots ranked for shade.
          </p>
        </div>
      </motion.footer>
    </div>
  );
}

/** Mono kicker label — uppercase, tracked, optional leading icon. */
function Kicker({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <p
      className="flex items-center gap-1.5 font-mono text-[11px] uppercase"
      style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
    >
      {icon}
      {children}
    </p>
  );
}

/** Giant headline datum with tiny mono caption. */
function HeroDatum({
  value,
  unit,
  label,
  accent,
  reduce,
  delay,
  borderLeft,
}: {
  value: string;
  unit?: string;
  label: string;
  accent?: string;
  reduce: boolean;
  delay: number;
  borderLeft?: boolean;
}) {
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: DUR.bloom / 1000, ease: EASE.out }}
      className="py-6 pr-6"
      style={borderLeft ? { borderLeft: "1px solid var(--border)", paddingLeft: "1.5rem" } : undefined}
    >
      <div className="flex items-baseline gap-2">
        <span
          className="font-sans tabular-nums"
          style={{ color: accent ?? "var(--text-primary)", fontSize: "clamp(3.5rem, 13vw, 7rem)", fontWeight: 700, lineHeight: 0.78, letterSpacing: "-0.04em" }}
        >
          {value}
        </span>
        {unit && (
          <span className="font-sans" style={{ color: accent ?? "var(--text-muted)", fontSize: "clamp(1.4rem, 3.5vw, 2.4rem)", fontWeight: 600 }}>
            {unit}
          </span>
        )}
      </div>
      <p className="mt-2 font-mono text-[11px] uppercase" style={{ color: "var(--text-muted)", letterSpacing: "0.1em", maxWidth: "24ch" }}>
        {label}
      </p>
    </motion.div>
  );
}

/** Editorial field: tiny mono label over the value. */
function Field({
  label,
  icon,
  children,
}: {
  label: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
        {icon}
        {label}
      </dt>
      <dd className="mt-1 font-sans text-[13px]" style={{ color: "var(--text-primary)" }}>
        {children}
      </dd>
    </div>
  );
}

/** Qualitative receipt cell — a single honest figure (NO money). */
function Receipt({
  value,
  unit,
  label,
  accent,
}: {
  value: string;
  unit?: string;
  label: string;
  accent?: string;
}) {
  return (
    <div className="px-4 py-5" style={{ background: "var(--bg)" }}>
      <div className="flex items-baseline gap-1">
        <span
          className="font-sans tabular-nums"
          style={{ color: accent ?? "var(--text-primary)", fontSize: "clamp(1.5rem, 4vw, 2.1rem)", fontWeight: 700, lineHeight: 1, letterSpacing: "-0.02em" }}
        >
          {value}
        </span>
        {unit && (
          <span className="font-mono text-[11px]" style={{ color: "var(--grey)" }}>
            {unit}
          </span>
        )}
      </div>
      <p className="mt-1.5 font-mono text-[9.5px] uppercase tracking-[0.08em]" style={{ color: "var(--text-muted)" }}>
        {label}
      </p>
    </div>
  );
}
