/**
 * Heat & Shade Plan — the ARCHITECT'S handout (owner, 2026-06-24).
 *
 * Division of labour: the in-app "The Plan" (HandoffStage) is the ORGANISER-readable
 * deliverable; THIS PDF is the technical handout an ARCHITECT designs from — same data,
 * but the spec the studio needs: where shade goes, the coverage target, orientation, and
 * the recommended reclaimed materials with their real datasheet specs.
 *
 * Styled to match the app UI: dark IAAC surface, ORANGE accent (brand `--green2` = orange
 * now), stark mono labels (Courier), sharp rules, no card-soup. NO footprint/area (owner
 * removed it). NO price (the service fee is quoted separately). Generated CLIENT-ONLY via a
 * dynamic import of @react-pdf/renderer.
 *
 * Honesty (CLAUDE.md): every modeled number is labelled; cooling is modeled not measured;
 * carbon is transport-only; the disclaimer states this is a decision aid, not construction-ready.
 */

export interface PlanZone {
  rank: number;
  name: string | null;
  /** Footprint is intentionally NOT shown (owner removed it); kept optional for callers. */
  area_m2?: number;
  coverage_pct: number;
  /** Design hint for the architect — e.g. "block the afternoon sun · SW". */
  orientation?: string;
}
export interface PlanMaterial {
  name: string;
  /** Null when the supplier feed doesn't expose a stock count (honest, never faked 0). */
  quantity: number | null;
  unit: string;
  distanceKm: number | null;
  /** Architect spec fields (optional — shown when the datasheet exposes them). */
  role?: "struct" | "membr";
  shadePct?: number | null;
  maxSpanMeters?: number | null;
  transportCarbonKg?: number | null;
  why?: string;
}
export interface HeatShadePlanData {
  site: string;
  generatedAt: string; // human-readable timestamp (caller stamps it)
  hottestC: number;
  zones: PlanZone[];
  peopleInHeat: number;
  peopleShaded: number;
  pctShaded: number;
  /** Real modeled cooling (°C) from the acceptance gate. Omitted when not yet reported. */
  coolingC?: number;
  materials: PlanMaterial[];
  transportCarbonKg: number;
  /** Optional. Pricing is handled separately — the plan omits it. */
  costLow?: number;
  costHigh?: number;
}

// Palette mirrors the app tokens (dark surface + orange accent).
const C = {
  bg: "#0E0F13",
  panel: "#16181D",
  paper: "#F2F0ED",
  grey: "#A8AAB6",
  rule: "#2C2E36",
  orange: "#E07D2B",
  orangeDeep: "#B0541A",
  heat: "#E8462A",
  amber: "#DFA22E",
};

const DISCLAIMER =
  "Decision-support output — not for construction without licensed structural-engineering review and on-site safety sign-off. Shade is one mitigation layer; pair it with water, medical and messaging provision.";

/** Build + download the plan PDF. Dynamically imports react-pdf (client-only). */
export async function downloadHeatShadePlan(data: HeatShadePlanData): Promise<void> {
  const { Document, Page, Text, View, StyleSheet, pdf } = await import("@react-pdf/renderer");

  const s = StyleSheet.create({
    page: { padding: 0, fontSize: 9.5, color: C.paper, fontFamily: "Helvetica", backgroundColor: C.bg },
    body: { paddingHorizontal: 40, paddingTop: 28, paddingBottom: 56 },

    // Masthead
    kicker: { fontFamily: "Courier-Bold", fontSize: 8, letterSpacing: 2, color: C.orange },
    h1: { fontSize: 26, fontFamily: "Helvetica-Bold", color: C.paper, marginTop: 6, letterSpacing: -0.5 },
    sub: { fontSize: 8.5, fontFamily: "Courier", color: C.grey, marginTop: 4, marginBottom: 16 },
    ruleHeavy: { borderBottomWidth: 1.5, borderBottomColor: C.paper, marginBottom: 14 },

    // Summary band (orange)
    band: { backgroundColor: C.orange, paddingVertical: 9, paddingHorizontal: 12, marginBottom: 16 },
    bandText: { fontSize: 11, fontFamily: "Helvetica-Bold", color: C.bg, lineHeight: 1.4 },

    // Section
    h2: { fontSize: 8, fontFamily: "Courier-Bold", letterSpacing: 1.5, color: C.orange, marginTop: 16, marginBottom: 6 },
    p: { lineHeight: 1.5, marginBottom: 3, color: C.paper },
    muted: { color: C.grey },

    // Tables
    row: { flexDirection: "row", borderBottomWidth: 0.75, borderBottomColor: C.rule, paddingVertical: 5 },
    headRow: { flexDirection: "row", borderBottomWidth: 0.75, borderBottomColor: C.rule, paddingBottom: 4 },
    th: { fontFamily: "Courier", fontSize: 7, letterSpacing: 1, color: C.grey },
    rank: { width: 22, fontFamily: "Helvetica-Bold", color: C.orange },
    cellName: { flex: 1, color: C.paper },
    cellMid: { width: 120, color: C.paper },
    cellNum: { width: 78, textAlign: "right", color: C.paper, fontFamily: "Courier" },

    // Material line
    matName: { fontFamily: "Helvetica-Bold", color: C.paper, fontSize: 10 },
    matSpec: { fontFamily: "Courier", fontSize: 7.5, color: C.grey, marginTop: 2 },

    assume: { fontSize: 7.5, color: C.amber, borderWidth: 0.75, borderColor: C.amber, padding: 7, marginTop: 14, lineHeight: 1.45 },
    footer: { position: "absolute", bottom: 24, left: 40, right: 40, fontSize: 7, color: C.grey, borderTopWidth: 0.75, borderTopColor: C.rule, paddingTop: 6, lineHeight: 1.4 },
  });

  const Doc = (
    <Document title={`Heat & Shade Plan — ${data.site}`}>
      <Page size="A4" style={s.page}>
        <View style={s.body}>
          {/* Masthead */}
          <Text style={s.kicker}>U-SHADE · ARCHITECT HANDOUT</Text>
          <Text style={s.h1}>Heat &amp; Shade Plan</Text>
          <Text style={s.sub}>
            {data.site} · generated {data.generatedAt} · climate-and-crowd decision aid
          </Text>
          <View style={s.ruleHeavy} />

          {/* Summary band */}
          <View style={s.band}>
            <Text style={s.bandText}>
              {data.zones.length} shade structure{data.zones.length === 1 ? "" : "s"} to design, placed on the
              hottest, busiest ground — protecting about {data.peopleShaded.toLocaleString()} of{" "}
              {data.peopleInHeat.toLocaleString()} people in caution-or-worse heat ({data.pctShaded}%).
            </Text>
          </View>

          {/* Method */}
          <Text style={s.h2}>METHOD</Text>
          <Text style={[s.p, s.muted]}>
            A UTCI "feels-like" heat simulation was crossed with a crowd-density simulation across the
            site. Shade is placed where ground is both hot and busy — never on empty or comfortable
            ground. Hottest feels-like recorded: {data.hottestC}°C. Heat-stress bands: comfortable
            &lt;26°C · caution 26–32°C · dangerous 32–38°C · severe 38–46°C. The 32°C line is where heat
            illness rises sharply.
          </Text>

          {/* Structures — NO footprint. Coverage target + orientation for the architect. */}
          <Text style={s.h2}>STRUCTURES TO DESIGN</Text>
          <View style={s.headRow}>
            <Text style={[s.rank, s.th]}>#</Text>
            <Text style={[s.cellName, s.th]}>LOCATION</Text>
            <Text style={[s.cellMid, s.th]}>ORIENTATION</Text>
            <Text style={[s.cellNum, s.th]}>CROWD COVER</Text>
          </View>
          {data.zones.map((z) => (
            <View style={s.row} key={z.rank}>
              <Text style={s.rank}>{String(z.rank).padStart(2, "0")}</Text>
              <Text style={s.cellName}>{z.name ? `near ${z.name}` : "shade spot"}</Text>
              <Text style={[s.cellMid, s.muted]}>{z.orientation ?? "block the afternoon sun · SW"}</Text>
              <Text style={s.cellNum}>{Math.round(z.coverage_pct)}%</Text>
            </View>
          ))}

          {/* Protection */}
          <Text style={s.h2}>PROTECTION</Text>
          <Text style={s.p}>
            Estimated {data.peopleShaded.toLocaleString()} of {data.peopleInHeat.toLocaleString()}{" "}
            attendees in caution-or-worse heat moved under shade ({data.pctShaded}%)
            {data.coolingC != null
              ? `, cutting their feels-like temperature by about ${data.coolingC.toFixed(1)}°C (modeled, not measured).`
              : ". Modeled cooling for this run is pending the acceptance gate and is not stated here."}
          </Text>

          {/* Recommended materials — architect spec. */}
          <Text style={s.h2}>RECOMMENDED MATERIALS · CLAD FROM THE LOCAL RECLAIMED STOCK</Text>
          {data.materials.length === 0 ? (
            <Text style={[s.p, s.muted]}>No materials sourced yet.</Text>
          ) : (
            data.materials.map((m, i) => {
              const specs: string[] = [];
              specs.push(m.role === "struct" ? "structure" : m.role === "membr" ? "membrane" : "");
              if (m.shadePct != null) specs.push(`${m.shadePct}% shade`);
              if (m.maxSpanMeters != null) specs.push(`${m.maxSpanMeters} m clear span`);
              if (m.transportCarbonKg != null) specs.push(`${Math.round(m.transportCarbonKg)} kg CO₂e transport`);
              if (m.distanceKm != null) specs.push(`~${Math.round(m.distanceKm)} km away`);
              return (
                <View style={{ paddingVertical: 6, borderBottomWidth: 0.75, borderBottomColor: C.rule }} key={i}>
                  <Text style={s.matName}>
                    {String(i + 1).padStart(2, "0")} · {m.name}
                  </Text>
                  <Text style={s.matSpec}>{specs.filter(Boolean).join("  ·  ")}</Text>
                </View>
              );
            })
          )}
          <Text style={[s.p, s.muted, { marginTop: 6 }]}>
            Ranked on cost, transport carbon and ease of assembly. The architect commits the final
            spec — this is the starting palette, not a contract. Transport carbon of the set: ~
            {Math.round(data.transportCarbonKg).toLocaleString()} kgCO₂e (transport-only).
          </Text>

          {/* Assumptions */}
          <Text style={s.assume}>
            ASSUMED / indicative: crowd density uses default weights (not yet validated for this site);
            cooling is modeled (≈3–6°C, shading studies), not measured; carbon is transport-only. Figures
            support a design decision — they are not guarantees.
          </Text>
        </View>

        <Text style={s.footer} fixed>
          {DISCLAIMER} · Generated {data.generatedAt} · U-Shade
        </Text>
      </Page>
    </Document>
  );

  const blob = await pdf(Doc).toBlob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `heat-shade-plan-${data.site.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
