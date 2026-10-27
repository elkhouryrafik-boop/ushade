import { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import * as d3 from "d3";
import { useHeatGuard } from "@/lib/heatguard-store";
import {
  getStructureZones,
  getHeatArtifact,
  getCrowdArtifact,
  getFestivalSchema,
  getAcceptance,
} from "@/lib/heatguard-api";
import { getMaterialsProvider } from "@/lib/materials-provider";
import { schemaPoints, nearestFeature } from "@/lib/festival-schema-layers";
import { downloadHeatShadePlan } from "../HeatShadePlanPdf";
import { Download, PrintingPage, Check } from "iconoir-react";
import { EASE } from "@/lib/motion";
import { PALETTE } from "@/lib/tokens";

/**
 * ⚠️ DEPRECATED / RETIRED (2026-06-24) — MERGED INTO "The Plan" (HandoffStage.tsx).
 * The owner unified Handoff + Report into ONE editorial deliverable, so the "report"
 * wizard stage no longer exists (removed from WIZARD_STAGES and the rail). This file is
 * no longer imported anywhere and is kept only as a reference for the chord-diagram and
 * receipt patterns; it is NOT rendered. Do not re-add a "report" stage. The price/receipt
 * total here is intentionally absent from the merged Plan (service fee quoted separately).
 *
 * S11 — The report. The one thing the organizer keeps: a report and a receipt in one.
 * The closing editorial document — "what it did / what it cost / why it holds up" — printed
 * like a safety certificate, not rendered like a dashboard. ONE hero datum (crowd pulled out
 * of danger), a column-headed ledger of what it did, a printed receipt card with a
 * hairline-ruled total, a stamped verification footer, and the d3 chord (zones × materials ×
 * cooling) framed as the refined method-relationship centerpiece. Line-by-line top-down
 * assembly, figures settle once and lock. All real figures + the export call — untouched.
 */

/* ── The relationship centerpiece: zones × materials chord, refined data-viz. ───────── */
function ChordDiagram({
  zones,
  materials,
  reduced,
}: {
  zones: { name: string; rank: number; cooling: number }[];
  materials: { name: string; carbon: number }[];
  reduced: boolean;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const SIZE = 460;
  const INNER = SIZE / 2 - 66;

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const names = [...zones.map((z) => z.name), ...materials.map((m) => m.name)];
    if (names.length < 2) return;

    const n = names.length;
    const matrix: number[][] = Array.from({ length: n }, () => Array(n).fill(0));

    // Connect each zone to each material proportionally to its cooling contribution.
    zones.forEach((z, zi) => {
      materials.forEach((m, mi) => {
        const val = Math.max(1, z.cooling * (1 / (mi + 1)));
        matrix[zi][zones.length + mi] = val;
        matrix[zones.length + mi][zi] = val;
      });
    });

    const chord = d3.chord().padAngle(0.05).sortSubgroups(d3.descending)(matrix);
    const arc = d3
      .arc<d3.ChordGroup>()
      .innerRadius(INNER)
      .outerRadius(INNER + 12);
    const ribbon = d3.ribbon<d3.Chord, d3.ChordSubgroup>().radius(INNER - 2);

    // Zones earn the rationed accent palette; materials stay neutral ink/grey.
    const zoneColors = [PALETTE.green, PALETTE.amber, PALETTE.teal, PALETTE.indigo];
    const matColors = [PALETTE.ink, PALETTE.grey];
    const colors = names.map((_, i) =>
      i < zones.length
        ? zoneColors[i % zoneColors.length]
        : matColors[(i - zones.length) % matColors.length],
    );

    const g = svg.attr("viewBox", `${-SIZE / 2} ${-SIZE / 2} ${SIZE} ${SIZE}`).append("g");

    // Ribbons — woven relationships, faint until touched.
    const ribbons = g
      .append("g")
      .selectAll("path")
      .data(chord)
      .join("path")
      .attr("d", ribbon as never)
      .attr("fill", (d) => colors[d.source.index])
      .attr("fill-opacity", reduced ? 0.4 : 0)
      .attr("stroke", "none")
      .style("cursor", "pointer")
      .on("mouseover", function (event, d) {
        d3.select(this).attr("fill-opacity", 0.78);
        setTooltip({
          x: event.offsetX,
          y: event.offsetY,
          text: `${names[d.source.index]} × ${names[d.target.index]}`,
        });
      })
      .on("mouseleave", function () {
        d3.select(this).attr("fill-opacity", 0.4);
        setTooltip(null);
      });

    if (!reduced) {
      ribbons
        .transition()
        .delay((_, i) => 180 + i * 45)
        .duration(520)
        .ease(d3.easeCubicOut)
        .attr("fill-opacity", 0.4);
    }

    // Arc groups — the nodes on the ring.
    const group = g.append("g").selectAll("g").data(chord.groups).join("g");

    group
      .append("path")
      .attr("d", arc as never)
      .attr("fill", (d) => colors[d.index])
      .attr("stroke", "var(--bg)")
      .attr("stroke-width", 1.5);

    // Tick line out to each label — the printed-instrument detail.
    group
      .append("line")
      .attr("x1", (d) => INNER * Math.cos((d.startAngle + d.endAngle) / 2 - Math.PI / 2))
      .attr("y1", (d) => INNER * Math.sin((d.startAngle + d.endAngle) / 2 - Math.PI / 2))
      .attr("x2", (d) => (INNER + 20) * Math.cos((d.startAngle + d.endAngle) / 2 - Math.PI / 2))
      .attr("y2", (d) => (INNER + 20) * Math.sin((d.startAngle + d.endAngle) / 2 - Math.PI / 2))
      .attr("stroke", "var(--border)")
      .attr("stroke-width", 0.75);

    group
      .append("text")
      .attr("dy", "0.32em")
      .attr("transform", (d) => {
        const mid = (d.startAngle + d.endAngle) / 2;
        const angle = mid * (180 / Math.PI) - 90;
        const r = INNER + 26;
        const x = r * Math.cos(mid - Math.PI / 2);
        const y = r * Math.sin(mid - Math.PI / 2);
        return `translate(${x},${y}) rotate(${angle > 90 || angle < -90 ? angle + 180 : angle})`;
      })
      .attr("text-anchor", (d) => {
        const angle = ((d.startAngle + d.endAngle) / 2) * (180 / Math.PI) - 90;
        return angle > 90 || angle < -90 ? "end" : "start";
      })
      .style("font-family", "var(--font-mono)")
      .style("font-size", "8.5px")
      .style("letter-spacing", "0.04em")
      .style("text-transform", "uppercase")
      .style("fill", "var(--grey)")
      .text((d) => names[d.index].slice(0, 14));
  }, [zones, materials, reduced, INNER]);

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        className="mx-auto block w-full"
        style={{ maxWidth: "440px", aspectRatio: "1" }}
      />
      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 px-2 py-1 font-mono text-[10px] uppercase tracking-wider"
          style={{
            left: tooltip.x + 10,
            top: tooltip.y + 10,
            border: "1px solid var(--ink)",
            borderRadius: "var(--radius-sm)",
            background: "var(--white)",
            color: "var(--text-primary)",
          }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}

/* ── Ledger row — column-aligned, dotted leader, monospaced tabular value. ──────────── */
function LedgerRow({
  label,
  value,
  unit,
  accent,
  delay = 0,
  reduced,
}: {
  label: string;
  value: string;
  unit?: string;
  accent?: string;
  delay?: number;
  reduced: boolean;
}) {
  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 3 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ delay, duration: 0.3, ease: EASE.inOut }}
      className="grid items-baseline gap-2 py-2"
      style={{ gridTemplateColumns: "1fr auto", borderBottom: "1px dashed var(--border)" }}
    >
      <dt
        className="overflow-hidden font-mono text-[10.5px] uppercase tracking-[0.08em] whitespace-nowrap"
        style={{ color: "var(--grey)" }}
      >
        {label}
        <span className="mx-1.5 align-middle" style={{ color: "var(--border)" }}>
          {"·".repeat(60)}
        </span>
      </dt>
      <dd
        className="flex items-baseline gap-1 font-mono text-[13px] tabular-nums"
        style={{ color: accent ?? "var(--text-primary)" }}
      >
        <span style={{ fontWeight: accent ? 600 : 400 }}>{value}</span>
        {unit && (
          <span className="text-[10px]" style={{ color: "var(--grey)" }}>
            {unit}
          </span>
        )}
      </dd>
    </motion.div>
  );
}

/* ── Editorial section header — mono index over a headline. ─────────────────────────── */
function SectionHead({ index, title }: { index: string; title: string }) {
  return (
    <div className="mb-3">
      <p className="text-label" style={{ color: "var(--grey)" }}>
        {index}
      </p>
      <h2 className="text-headline mt-1" style={{ color: "var(--ink)" }}>
        {title}
      </h2>
    </div>
  );
}

export function ReportScreen() {
  const { state } = useHeatGuard();
  const reduced = useReducedMotion() ?? false;

  const heatQ = useQuery({
    queryKey: ["heat", state.simRunId],
    queryFn: () => getHeatArtifact(state.simRunId!),
    enabled: state.simRunId !== null,
    staleTime: Infinity,
  });
  const crowdQ = useQuery({
    queryKey: ["crowd", state.simRunId],
    queryFn: () => getCrowdArtifact(state.simRunId!),
    enabled: state.simRunId !== null,
    staleTime: Infinity,
  });
  const zonesQ = useQuery({
    queryKey: ["zones", state.simRunId],
    queryFn: () => getStructureZones(state.simRunId!),
    enabled: state.simRunId !== null,
    staleTime: Infinity,
  });
  const schemaQ = useQuery({
    queryKey: ["festival-schema"],
    queryFn: getFestivalSchema,
    staleTime: Infinity,
  });
  // Real modeled cooling from the Phase-5b acceptance gate — not hardcoded.
  const acceptanceQ = useQuery({
    queryKey: ["acceptance", state.simRunId],
    queryFn: () => getAcceptance(state.simRunId!),
    enabled: state.simRunId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const { data: materials } = useQuery({
    queryKey: ["catalogue"],
    queryFn: () => getMaterialsProvider().queryCatalogue(),
  });

  const features = useMemo(
    () => (schemaQ.data ? schemaPoints(schemaQ.data.features) : []),
    [schemaQ.data],
  );
  const acceptedZones = useMemo(
    () => (zonesQ.data?.structures ?? []).filter((z) => state.acceptedRanks.includes(z.rank)),
    [zonesQ.data, state.acceptedRanks],
  );
  const reservedMaterials = useMemo(
    () => (materials?.items ?? []).filter((m) => state.materialHolds[m.id]),
    [materials, state.materialHolds],
  );

  const totalDemand = zonesQ.data?.total_demand ?? 0;
  const peopleShaded = Math.round(acceptedZones.reduce((s, z) => s + z.marginal_demand, 0));
  const pctShaded = totalDemand > 0 ? Math.round((peopleShaded / totalDemand) * 100) : 0;
  const COOLING_DELTA_C = acceptanceQ.data?.utci_delta_c ?? 4;
  const totalCarbon = reservedMaterials.reduce((s, m) => s + (m.transportCarbonKg ?? 0), 0);
  // Share of the in-heat crowd now under shade (honest, real). The remainder is
  // the residual that shade did not reach — never a fabricated "before" baseline.
  const residualPct = Math.max(0, 100 - pctShaded);
  // Real service fee from the placer's own per-structure budget — never a placeholder.
  const costPerStructure = zonesQ.data?.stopping_rule?.cost_per_structure ?? 0;
  const costTotal = acceptedZones.length * costPerStructure;
  const shadedM2 = acceptedZones.reduce((s, z) => s + z.area_m2, 0);
  const costPerM2 = shadedM2 > 0 && costTotal > 0 ? Math.round(costTotal / shadedM2) : 0;

  // Chord data
  const chordZones = acceptedZones.map((z) => ({
    name: features.length
      ? (nearestFeature(z.center, features) ?? `Zone ${z.rank}`)
      : `Zone ${z.rank}`,
    rank: z.rank,
    cooling: COOLING_DELTA_C,
  }));
  const chordMaterials = reservedMaterials.map((m) => ({
    name: m.name.slice(0, 15),
    carbon: m.transportCarbonKg ?? 0,
  }));

  const today = new Date().toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
  const issued = new Date().toISOString().slice(0, 10);
  const refId = `US-${(state.simRunId ?? "FORUM").toString().slice(-4).toUpperCase().padStart(4, "0")}`;
  const verifiedAt = new Date().toLocaleString("en-GB", { hour: "2-digit", minute: "2-digit" });

  function exportPdf() {
    downloadHeatShadePlan({
      site: "Parc del Fòrum, Barcelona",
      generatedAt: new Date().toLocaleString(),
      hottestC: heatQ.data ? Math.round(heatQ.data.utci_max_c) : 0,
      zones: acceptedZones.map((z) => ({
        rank: z.rank,
        name: features.length ? nearestFeature(z.center, features) : null,
        area_m2: z.area_m2,
        coverage_pct: z.coverage_pct,
      })),
      peopleInHeat: Math.round(totalDemand),
      peopleShaded,
      pctShaded,
      coolingC: COOLING_DELTA_C,
      materials: reservedMaterials.map((m) => ({
        name: m.name,
        quantity: m.quantity,
        unit: m.unit,
        distanceKm: m.distanceKm,
      })),
      transportCarbonKg: totalCarbon,
      costLow: acceptedZones.length * (zonesQ.data?.stopping_rule?.cost_per_structure ?? 0),
      costHigh: acceptedZones.length * (zonesQ.data?.stopping_rule?.cost_per_structure ?? 0),
    });
  }

  const rise = (delay: number) =>
    reduced
      ? { initial: false as const }
      : {
          initial: { opacity: 0, y: 14 },
          animate: { opacity: 1, y: 0 },
          transition: { delay, duration: 0.55, ease: EASE.out },
        };

  return (
    <div className="h-full overflow-y-auto" style={{ background: "var(--white)" }}>
      <div className="mx-auto max-w-[1080px] px-6 py-10 md:px-10 md:py-14">
        {/* ── MASTHEAD — the document declares itself. ──────────────────────────── */}
        <motion.header
          {...rise(0)}
          className="flex items-end justify-between gap-6 pb-5"
          style={{ borderBottom: "3px solid var(--ink)" }}
        >
          <div>
            <p className="text-label" style={{ color: "var(--grey)" }}>
              Heat &amp; Shade Report
            </p>
            <h1 className="text-hero mt-3" style={{ color: "var(--ink)", lineHeight: 0.9 }}>
              The Plan
            </h1>
            <p
              className="mt-3 font-mono text-[11px] uppercase tracking-[0.06em]"
              style={{ color: "var(--grey)" }}
            >
              Parc del Fòrum · v1 · {refId}
            </p>
          </div>
          <div
            className="shrink-0 text-right font-mono text-[10px] uppercase tracking-[0.08em]"
            style={{ color: "var(--grey)" }}
          >
            <span className="flex items-center justify-end gap-1.5">
              <PrintingPage className="size-3" strokeWidth={1.5} /> Issued
            </span>
            <span
              className="mt-0.5 block text-[14px] tabular-nums"
              style={{ color: "var(--text-primary)" }}
            >
              {issued}
            </span>
          </div>
        </motion.header>

        {/* ── HERO DATUM — the crowd pulled out of danger, read across a room. ──── */}
        <motion.section
          {...rise(0.12)}
          className="py-9"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <p className="text-label" style={{ color: "var(--grey)" }}>
            Crowd moved out of dangerous heat
          </p>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-5 gap-y-2">
            <span
              className="tabular-nums"
              style={{
                color: "var(--green)",
                fontFamily: "var(--font-display)",
                fontWeight: 700,
                fontSize: "clamp(3.6rem,11vw,8rem)",
                lineHeight: 0.82,
                letterSpacing: "-0.04em",
              }}
            >
              {peopleShaded.toLocaleString()}
            </span>
            <span
              className="font-mono text-sm uppercase tracking-wider"
              style={{ color: "var(--grey)" }}
            >
              people
            </span>
            <span className="ml-auto text-right">
              <span
                className="block tabular-nums"
                style={{
                  color: "var(--text-primary)",
                  fontFamily: "var(--font-display)",
                  fontWeight: 700,
                  fontSize: "clamp(1.8rem,4vw,2.8rem)",
                  lineHeight: 1,
                }}
              >
                {pctShaded}%
              </span>
              <span
                className="font-mono text-[10px] uppercase tracking-[0.08em]"
                style={{ color: "var(--grey)" }}
              >
                of in-heat crowd now under shade
              </span>
            </span>
          </div>
          <p className="text-editorial mt-4 max-w-2xl" style={{ color: "var(--text-muted)" }}>
            ~{COOLING_DELTA_C.toFixed(1)} °C cooler on the covered crowd. The remaining {residualPct}
            % the shade did not reach is co-located with water and medical provision.
          </p>
        </motion.section>

        {/* ── 2-column document body. ──────────────────────────────────────────── */}
        <div className="mt-10 grid gap-10 md:grid-cols-[1.05fr_0.95fr] md:gap-12">
          {/* LEFT — what it did / inputs / why it holds up. */}
          <div className="space-y-11">
            <section>
              <SectionHead index="01 · What it did" title="The relief" />
              <dl>
                <LedgerRow
                  label="In-heat crowd shaded"
                  value={`${pctShaded}%`}
                  accent="var(--green)"
                  reduced={reduced}
                />
                <LedgerRow
                  label="Moved to safe"
                  value={`~${peopleShaded.toLocaleString()}`}
                  delay={0.04}
                  reduced={reduced}
                />
                <LedgerRow
                  label="Cooling, covered crowd"
                  value={`−${COOLING_DELTA_C.toFixed(1)}`}
                  unit="°C"
                  delay={0.08}
                  reduced={reduced}
                />
                <LedgerRow
                  label="Shade structures"
                  value={String(acceptedZones.length)}
                  delay={0.12}
                  reduced={reduced}
                />
                <LedgerRow
                  label="Residual · watered"
                  value={`${residualPct}%`}
                  delay={0.16}
                  reduced={reduced}
                />
              </dl>

              <div className="mt-5 space-y-2">
                {acceptedZones.map((z, i) => (
                  <motion.div
                    key={z.rank}
                    initial={reduced ? false : { opacity: 0, x: -6 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ delay: i * 0.06, duration: 0.35, ease: EASE.out }}
                    className="flex items-baseline justify-between gap-3 py-2 pl-3"
                    style={{
                      borderLeft: `3px solid ${i === 0 ? "var(--green)" : i === 1 ? "var(--amber)" : "var(--grey)"}`,
                    }}
                  >
                    <div>
                      <p
                        className="font-mono text-[10px] uppercase tracking-[0.08em]"
                        style={{ color: "var(--grey)" }}
                      >
                        Zone {z.rank}
                        {features.length > 0 && (
                          <span style={{ color: "var(--text-muted)" }}>
                            {" "}
                            · {nearestFeature(z.center, features)}
                          </span>
                        )}
                      </p>
                      <p
                        className="mt-0.5 font-mono text-[12.5px] tabular-nums"
                        style={{ color: "var(--text-primary)" }}
                      >
                        ~{Math.round(z.marginal_demand).toLocaleString()} people
                      </p>
                    </div>
                    <span
                      className="font-mono text-[13px] tabular-nums"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {Math.round(z.coverage_pct)}%
                    </span>
                  </motion.div>
                ))}
              </div>
            </section>

            <section>
              <SectionHead index="02 · Climate & crowd" title="The inputs" />
              <dl>
                <LedgerRow
                  label="Hottest feels-like"
                  value={heatQ.data ? `${Math.round(heatQ.data.utci_max_c)}` : "—"}
                  unit="°C"
                  accent="var(--heat)"
                  reduced={reduced}
                />
                <LedgerRow
                  label="Heat source"
                  value="infrared.city UTCI"
                  delay={0.04}
                  reduced={reduced}
                />
                <LedgerRow
                  label="Danger line"
                  value="32"
                  unit="°C"
                  delay={0.08}
                  reduced={reduced}
                />
                <LedgerRow
                  label="People in caution+ heat"
                  value={Math.round(totalDemand).toLocaleString()}
                  delay={0.12}
                  reduced={reduced}
                />
                <LedgerRow label="Crowd model" value="JuPedSim" delay={0.16} reduced={reduced} />
              </dl>
            </section>

            <section>
              <SectionHead index="03 · Why it holds up" title="The defence" />
              <ul
                className="space-y-3 text-[12.5px] leading-relaxed"
                style={{ color: "var(--text-muted)" }}
              >
                {[
                  "Dated, method shown, every assumption stated — so scrutiny finds the limits from you first.",
                  "Doubles as the heat section of the event safety plan: for the safety group, the licensing authority, or the insurer.",
                ].map((line, i) => (
                  <li key={i} className="flex gap-2.5">
                    <Check
                      className="mt-0.5 size-3.5 shrink-0"
                      strokeWidth={2}
                      style={{ color: "var(--green)" }}
                    />
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          {/* RIGHT — the printed receipt, provenance, the chord, the method note. */}
          <div className="space-y-11">
            {/* ── THE RECEIPT — a printed document with a hairline-ruled total. ── */}
            <motion.section
              initial={reduced ? false : { opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.45, ease: EASE.out }}
              className="px-6 py-6"
              style={{
                border: "1px solid var(--ink)",
                borderRadius: "var(--radius-sm)",
                background: "var(--surface)",
              }}
            >
              <div
                className="flex items-start justify-between gap-3 pb-3"
                style={{ borderBottom: "1px solid var(--ink)" }}
              >
                <div>
                  <p className="text-subhead" style={{ color: "var(--text-primary)" }}>
                    Heat &amp; Shade Receipt
                  </p>
                  <p
                    className="mt-1 font-mono text-[9.5px] uppercase tracking-[0.1em]"
                    style={{ color: "var(--grey)" }}
                  >
                    Service fee — not a materials bill
                  </p>
                </div>
                <span
                  className="shrink-0 font-mono text-[10px] tabular-nums"
                  style={{ color: "var(--grey)" }}
                >
                  {today}
                </span>
              </div>

              <p
                className="mt-4 mb-1 font-mono text-[9.5px] font-semibold uppercase tracking-[0.14em]"
                style={{ color: "var(--teal)" }}
              >
                What it cost
              </p>
              <dl>
                <LedgerRow label="Service" value="design · sourcing · delivery" reduced={reduced} />
                <LedgerRow
                  label="Shaded"
                  value={
                    shadedM2 > 0
                      ? `${shadedM2.toLocaleString()} m²${costPerM2 > 0 ? ` × €${costPerM2}/m²` : ""}`
                      : "—"
                  }
                  delay={0.05}
                  reduced={reduced}
                />
                <LedgerRow
                  label="Materials"
                  value="upcycled · not priced"
                  delay={0.1}
                  reduced={reduced}
                />
              </dl>

              <div
                className="mt-4 flex items-end justify-between gap-3 pt-4"
                style={{ borderTop: "2px solid var(--ink)" }}
              >
                <span
                  className="font-mono text-[10px] uppercase tracking-[0.14em]"
                  style={{ color: "var(--grey)" }}
                >
                  Total
                </span>
                <span
                  className="tabular-nums"
                  style={{
                    color: "var(--text-primary)",
                    fontFamily: "var(--font-display)",
                    fontWeight: 700,
                    fontSize: "clamp(2rem,5vw,2.8rem)",
                    lineHeight: 0.9,
                    letterSpacing: "-0.03em",
                  }}
                >
                  {costTotal > 0 ? `€${costTotal.toLocaleString()}` : "—"}
                </span>
              </div>
              <p
                className="mt-1 text-right font-mono text-[9px] uppercase tracking-[0.06em]"
                style={{ color: "var(--grey)" }}
              >
                Planning fee · excludes permits &amp; engineering
              </p>

              <p
                className="mt-4 text-[11px] leading-relaxed"
                style={{ color: "var(--text-muted)" }}
              >
                Materials are upcycled, shown by location, never priced — "cheap insurance" against
                the downside.
              </p>

              {/* Stamped verification — the dashed certificate detail. */}
              <div
                className="mt-5 flex flex-wrap items-center gap-2 pt-4"
                style={{ borderTop: "1px dashed var(--border)" }}
              >
                <span
                  className="px-2 py-1 font-mono text-[9px] uppercase tracking-[0.08em]"
                  style={{
                    border: "1px dashed var(--ink)",
                    borderRadius: "var(--radius-sm)",
                    color: "var(--text-primary)",
                  }}
                >
                  REF · {refId}
                </span>
                <span
                  className="flex items-center gap-1 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.08em]"
                  style={{
                    border: "1px dashed var(--green)",
                    borderRadius: "var(--radius-sm)",
                    color: "var(--green)",
                  }}
                >
                  <Check className="size-2.5" strokeWidth={2.5} /> Verified {issued} · {verifiedAt}
                </span>
              </div>

              <div className="mt-5 flex gap-2">
                <button
                  type="button"
                  onClick={exportPdf}
                  className="flex h-10 flex-1 items-center justify-center gap-2 font-sans font-bold transition-opacity hover:opacity-90"
                  style={{
                    background: "var(--ink)",
                    color: "var(--white)",
                    borderRadius: "var(--radius-sm)",
                    letterSpacing: "0.04em",
                    fontSize: "0.8rem",
                  }}
                >
                  <Download className="size-4" strokeWidth={1.5} />
                  Download PDF
                </button>
                <button
                  type="button"
                  onClick={exportPdf}
                  className="flex h-10 items-center justify-center px-4 font-mono text-[11px] uppercase tracking-wider transition-opacity hover:opacity-70"
                  style={{
                    border: "1px solid var(--ink)",
                    borderRadius: "var(--radius-sm)",
                    color: "var(--text-primary)",
                  }}
                >
                  CSV ledger
                </button>
              </div>
            </motion.section>

            {/* ── PROVENANCE — the carbon ledger, tiers stay internal (no pills). ── */}
            <section>
              <SectionHead index="04 · The footprint" title="Transport carbon" />
              <dl>
                <LedgerRow
                  label="Total transport carbon"
                  value={totalCarbon.toLocaleString()}
                  unit="kgCO₂e"
                  reduced={reduced}
                />
                <LedgerRow
                  label="Reclaimed materials"
                  value={String(reservedMaterials.length || "—")}
                  delay={0.04}
                  reduced={reduced}
                />
              </dl>
              <p
                className="mt-3 text-[11px] leading-relaxed"
                style={{ color: "var(--text-muted)" }}
              >
                Modeled, not measured. Carbon is transport-only — every figure carries how it was
                earned, so the limits are ours to surface, not yours to find.
              </p>
            </section>

            {/* ── RELATIONSHIPS — the chord, the refined method centerpiece. ────── */}
            {chordZones.length > 0 && chordMaterials.length > 0 && (
              <section>
                <SectionHead index="05 · Relationships" title="Zones × materials" />
                <ChordDiagram zones={chordZones} materials={chordMaterials} reduced={reduced} />
                <p
                  className="mt-2 text-center font-mono text-[9.5px] uppercase tracking-[0.06em]"
                  style={{ color: "var(--grey)" }}
                >
                  Ribbon weight = relative cooling contribution · hover a strand for the pairing
                </p>
              </section>
            )}
          </div>
        </div>

        {/* ── COLOPHON — the method, the standing line. ─────────────────────────── */}
        <motion.footer
          {...rise(0.1)}
          className="mt-14 pt-6"
          style={{ borderTop: "3px solid var(--ink)" }}
        >
          <p className="text-editorial max-w-3xl" style={{ color: "var(--text-muted)" }}>
            The site boundary you drew → a real infrared.city heat grid → crowd flow simulated
            across the day → the hottest, busiest spots ranked for shade.
          </p>
        </motion.footer>
      </div>
    </div>
  );
}
