import { useMemo } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Check, Plus, ShieldAlt } from "iconoir-react";
import { StageScaffold } from "./StageScaffold";
import { EASE, DUR } from "@/lib/motion";
import type { Scenario, ScenarioData } from "@/lib/scenarios";

/**
 * Scenario "Where the shade goes" panel — the placement aside for "Beyond Festivals".
 *
 * A faithful re-skin of the festival PlacementStage's ranked-zone list, but fed by the
 * scenario's SYNTHETIC mock zones (data.zones) with purely local accept state — it
 * touches NONE of the backend-coupled festival queries. Same editorial anatomy: one
 * hero datum, the engineering disclaimer, a ruled ranked list with giant rank numerals,
 * accept/keep controls, and a live "who you protect" rollup.
 */
export function ScenarioPlacementPanel({
  scenario,
  data,
  accepted,
  hovered,
  onToggle,
  onHover,
}: {
  scenario: Scenario;
  data: ScenarioData;
  accepted: number[];
  hovered: number | null;
  onToggle: (rank: number) => void;
  onHover: (rank: number | null) => void;
}) {
  const reduce = useReducedMotion();
  const zones = data.zones;

  const acceptedZones = useMemo(
    () => zones.filter((z) => accepted.includes(z.rank)),
    [zones, accepted],
  );
  const peopleInHeat = data.headline.peopleInHeat;
  const peopleShaded = acceptedZones.reduce((s, z) => s + z.marginalDemand, 0);
  const pctShaded = peopleInHeat > 0 ? Math.round((peopleShaded / peopleInHeat) * 100) : 0;
  const coolingAvg =
    acceptedZones.length > 0
      ? acceptedZones.reduce((s, z) => s + z.coolingC, 0) / acceptedZones.length
      : 0;

  return (
    <StageScaffold
      index="04 / SHADE"
      title="Where the shade goes"
      lede={`Hot × busy at ${scenario.site.split("—")[0].split(",")[0].trim()}. Accept the spots that protect the most people.`}
      cta={{
        label: "Clad these zones →",
        onClick: () => {},
        disabled: accepted.length === 0,
        disabledReason: "Accept at least one spot — this is a concept mock; cladding is the next stage.",
      }}
    >
      <div className="space-y-5">
        {/* Hero datum */}
        <div className="pb-1">
          {accepted.length > 0 ? (
            <>
              <p className="text-label" style={{ color: "var(--grey)" }}>
                PEOPLE IN HEAT · NOW COVERED
              </p>
              <motion.p
                key={pctShaded}
                className="text-hero mt-1 tabular-nums leading-[0.9]"
                style={{ color: "var(--paper)" }}
                initial={reduce ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: DUR.card / 1000, ease: EASE.out }}
              >
                {pctShaded}
                <span className="text-display align-top" style={{ color: "var(--teal)" }}>
                  %
                </span>
              </motion.p>
              <div
                className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono text-[11px]"
                style={{ color: "var(--grey)" }}
              >
                <span>
                  <span className="tabular-nums font-medium" style={{ color: "var(--paper)" }}>
                    ~{peopleShaded.toLocaleString()}
                  </span>
                  {" / "}
                  {peopleInHeat.toLocaleString()} PEOPLE
                </span>
                <span>
                  −
                  <span className="tabular-nums font-medium" style={{ color: "var(--paper)" }}>
                    {coolingAvg.toFixed(1)}
                  </span>
                  °C FEELS-LIKE
                </span>
              </div>
            </>
          ) : (
            <>
              <p className="text-label" style={{ color: "var(--grey)" }}>
                PEAK FEELS-LIKE · {data.headline.peakC >= 32 ? "DANGEROUS" : "CAUTION"}
              </p>
              <p className="text-hero mt-1 tabular-nums leading-[0.9]" style={{ color: "var(--heat)" }}>
                {Math.round(data.headline.peakC)}
                <span className="text-display align-top">°C</span>
              </p>
              <p className="mt-2 font-mono text-[11px]" style={{ color: "var(--grey)" }}>
                ~
                <span className="tabular-nums font-medium" style={{ color: "var(--paper)" }}>
                  {peopleInHeat.toLocaleString()}
                </span>{" "}
                PEOPLE IN CAUTION-OR-WORSE HEAT · ACCEPT SPOTS TO SEE WHO YOU PROTECT
              </p>
            </>
          )}
        </div>

        {/* Concept-mock disclaimer (replaces the festival engineering disclaimer) */}
        <div
          className="flex items-start gap-2 px-3 py-2.5"
          style={{
            border: "1px solid color-mix(in srgb, var(--amber) 40%, transparent)",
            borderRadius: "var(--radius-sm)",
            background: "color-mix(in srgb, var(--amber) 8%, transparent)",
          }}
        >
          <ShieldAlt className="mt-0.5 size-4 shrink-0" style={{ color: "var(--amber)" }} strokeWidth={1.5} />
          <p className="font-mono text-[11px] leading-relaxed" style={{ color: "var(--paper)" }}>
            Concept demo — the U-Shade engine running on synthetic {scenario.label.toLowerCase()} data
            to show the same flow beyond festivals. Real placements need measured climate + a
            licensed structural sign-off.
          </p>
        </div>

        <section>
          <div
            className="flex items-baseline justify-between pb-2"
            style={{ borderBottom: "1.5px solid var(--paper)" }}
          >
            <h3 className="text-subhead leading-[0.95]" style={{ color: "var(--paper)" }}>
              Recommended
              <br />
              shade zones
            </h3>
            <span className="font-mono text-[10px] tabular-nums" style={{ color: "var(--grey)" }}>
              {accepted.length}/{zones.length} KEPT
            </span>
          </div>

          <div
            className="grid items-center gap-3 py-1.5 font-mono text-[9px] tracking-[0.14em]"
            style={{ gridTemplateColumns: "1.6rem 1fr auto", color: "var(--grey)", borderBottom: "1px solid var(--border)" }}
          >
            <span>RANK</span>
            <span>WHY HERE?</span>
            <span className="text-right">COOLING</span>
          </div>

          <ul>
            {zones.map((z, i) => {
              const isAccepted = accepted.includes(z.rank);
              const isHovered = hovered === z.rank;
              const danger = z.rank <= 2;
              const numColor = isAccepted ? "var(--green2)" : danger ? "var(--heat)" : "var(--grey)";
              return (
                <motion.li
                  key={z.rank}
                  onMouseEnter={() => onHover(z.rank)}
                  onMouseLeave={() => onHover(null)}
                  className="grid items-center gap-3 transition-colors"
                  initial={reduce ? false : { opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: DUR.card / 1000, ease: EASE.out, delay: Math.min(i, 5) * 0.05 }}
                  style={{
                    gridTemplateColumns: "1.6rem 1fr auto",
                    borderBottom: "1px solid var(--border)",
                    paddingTop: "0.85rem",
                    paddingBottom: "0.85rem",
                    background: isHovered ? "color-mix(in srgb, var(--paper) 5%, transparent)" : "transparent",
                  }}
                >
                  <span
                    className="font-mono font-bold tabular-nums leading-none"
                    style={{ color: numColor, fontSize: "1.45rem" }}
                  >
                    {String(z.rank).padStart(2, "0")}
                  </span>

                  <div className="min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-[13px] tabular-nums font-medium" style={{ color: "var(--heat)" }}>
                        {Math.round(z.peakC)}°C
                      </span>
                      <span className="font-mono text-[10px] uppercase tracking-[0.06em]" style={{ color: "var(--grey)" }}>
                        peak feels-like
                      </span>
                    </div>
                    <p
                      className="mt-0.5 truncate font-mono text-[10px] tracking-[0.04em] uppercase"
                      style={{ color: "var(--grey)" }}
                    >
                      {z.whyHere}
                    </p>
                    <p className="mt-0.5 font-mono text-[10px]" style={{ color: "var(--grey)" }}>
                      SHADES ~
                      <span className="tabular-nums" style={{ color: "var(--paper)" }}>
                        {z.marginalDemand.toLocaleString()}
                      </span>{" "}
                      ·{" "}
                      <span className="tabular-nums" style={{ color: "var(--paper)" }}>
                        {z.crowdShare}%
                      </span>{" "}
                      OF CROWD
                    </p>
                  </div>

                  <div className="flex flex-col items-end gap-1.5">
                    <span
                      className="font-mono text-[13px] tabular-nums font-medium"
                      style={{ color: isAccepted ? "var(--green2)" : "var(--teal)" }}
                    >
                      −{z.coolingC.toFixed(1)}°C
                    </span>
                    <button
                      type="button"
                      onClick={() => onToggle(z.rank)}
                      aria-label={isAccepted ? `Dismiss zone ${z.rank}` : `Accept zone ${z.rank}`}
                      aria-pressed={isAccepted}
                      className="flex h-7 items-center justify-center gap-1 px-2.5 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] transition-colors"
                      style={{
                        background: isAccepted ? "var(--green)" : "transparent",
                        color: isAccepted ? "var(--white)" : "var(--green2)",
                        border: `1px solid ${isAccepted ? "var(--green)" : "color-mix(in srgb, var(--green2) 55%, transparent)"}`,
                        borderRadius: "var(--radius-sm)",
                      }}
                    >
                      {isAccepted ? (
                        <>
                          <Check className="size-3" strokeWidth={2.6} />
                          Kept
                        </>
                      ) : (
                        <>
                          <Plus className="size-3" strokeWidth={2.4} />
                          Keep
                        </>
                      )}
                    </button>
                  </div>
                </motion.li>
              );
            })}
          </ul>
        </section>
      </div>
    </StageScaffold>
  );
}
