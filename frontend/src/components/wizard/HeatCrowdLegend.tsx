import { useMemo, useState } from "react";
import { NavArrowDown, InfoCircle } from "iconoir-react";
import { crowdColor, utciColor } from "@/lib/tokens";

/**
 * Heat × Crowd legend — the map's reading key, spec S7 "Color direction".
 *
 * Re-cut to read like the reference's bottom-right gradient legend (s6-heatmap.png:
 * "SCIENTIFIC URBAN · UTCI LOADING") — a precise thermal instrument, NOT a SaaS
 * chip stack. The ideas, in order:
 *   1. HEAT is a single CONTINUOUS UTCI bar sampled straight from the locked ramp
 *      (utciColor) across 9–46 °C — the same colours the field paints, so the legend
 *      IS the data. Band breakpoints sit as hairline ticks underneath; the 32 °C
 *      dangerous line is the one labelled contour, drawn over the bar.
 *   2. CROWD is a distinct cool teal→indigo ramp so it never reads as heat.
 *   3. The hero teaching: HOT × BUSY is where shade goes — stated quietly.
 *
 * Collapsed by default to a small pill; expanded panel is dark-native (--paper
 * text, --grey labels, near-black chip, hairline border, 2px corners).
 */

// UTCI domain the bar spans (matches the ramp anchors in tokens.ts).
const T_LO = 9;
const T_HI = 46;
// Band breakpoints to tick under the bar. 32° is special (drawn as the danger line).
const BAND_TICKS = [
  { c: 26, label: "26°", name: "caution" },
  { c: 32, label: "32°", name: "danger", danger: true },
  { c: 38, label: "38°", name: "severe" },
];

// Near-opaque so the legend stays a crisp reading key on dark — and never gets
// washed out where the bright heat field bleeds toward the bottom-left corner.
const PANEL_BG = "color-mix(in srgb, var(--black) 90%, transparent)";

const pct = (c: number) => ((c - T_LO) / (T_HI - T_LO)) * 100;

export function HeatCrowdLegend() {
  const [open, setOpen] = useState(false);

  // Continuous UTCI gradient — sampled off the real ramp at 1 °C steps so the bar
  // matches the field exactly (never a rainbow, never a flat 4-block wash).
  const heatGradient = useMemo(() => {
    const stops: string[] = [];
    for (let c = T_LO; c <= T_HI; c += 1) {
      const [r, g, b] = utciColor(c);
      stops.push(`rgb(${r},${g},${b}) ${pct(c).toFixed(1)}%`);
    }
    return `linear-gradient(to right, ${stops.join(",")})`;
  }, []);

  // Crowd ramp — cool teal → indigo, distinct family from heat.
  const crowdGradient = useMemo(() => {
    const stops = [0, 0.5, 1].map((t) => `rgb(${crowdColor(t).join(",")})`);
    return `linear-gradient(to right, ${stops.join(",")})`;
  }, []);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="pointer-events-auto absolute bottom-4 left-4 z-30 flex items-center gap-1.5 font-mono text-[11px] backdrop-blur-md transition-opacity hover:opacity-80"
        style={{
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          background: PANEL_BG,
          color: "var(--grey)",
          padding: "7px 11px",
          boxShadow: "0 2px 10px rgba(0,0,0,0.45)",
        }}
      >
        <InfoCircle className="size-3.5" strokeWidth={1.6} />
        What do the colours mean?
      </button>
    );
  }

  return (
    <div
      className="pointer-events-auto absolute bottom-4 left-4 z-30 w-[256px] backdrop-blur-md animate-fade-in"
      style={{
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        background: PANEL_BG,
        boxShadow: "0 8px 28px rgba(0,0,0,0.55)",
        padding: "11px 12px 12px",
      }}
    >
      {/* header — instrument masthead */}
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="flex w-full items-center justify-between transition-opacity hover:opacity-80"
      >
        <span
          className="font-mono uppercase"
          style={{ fontSize: 9, letterSpacing: "0.16em", color: "var(--grey)" }}
        >
          Scientific urban · reading the map
        </span>
        <NavArrowDown className="size-3.5" style={{ color: "var(--grey)" }} strokeWidth={2} />
      </button>

      {/* HEAT — continuous UTCI loading bar */}
      <div className="mt-3">
        <div
          className="font-mono uppercase"
          style={{ fontSize: 8.5, letterSpacing: "0.14em", color: "var(--paper)" }}
        >
          UTCI loading <span style={{ color: "var(--grey)" }}>· feels-like °C</span>
        </div>

        {/* the bar + the 32° danger contour drawn over it */}
        <div className="relative mt-2 h-3.5" style={{ borderRadius: "var(--radius-sm)" }}>
          <div
            className="absolute inset-0"
            style={{
              background: heatGradient,
              borderRadius: "var(--radius-sm)",
              boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--white) 8%, transparent)",
            }}
          />
          {/* breakpoint ticks — hairlines that bite the top edge of the bar */}
          {BAND_TICKS.map((t) => (
            <span
              key={t.c}
              aria-hidden
              className="absolute"
              style={{
                left: `${pct(t.c)}%`,
                top: t.danger ? -3 : 0,
                bottom: t.danger ? -3 : "55%",
                width: 0,
                borderLeft: t.danger
                  ? "1.5px dashed var(--paper)"
                  : "1px solid color-mix(in srgb, var(--white) 45%, transparent)",
              }}
            />
          ))}
        </div>

        {/* ticks row — comfortable … emergency anchors + numeric breakpoints */}
        <div className="relative mt-1.5 h-7">
          {/* end anchors */}
          <span
            className="absolute left-0 font-mono"
            style={{ top: 0, fontSize: 7.5, color: "var(--grey)" }}
          >
            {T_LO}°
          </span>
          <span
            className="absolute right-0 text-right font-mono"
            style={{ top: 0, fontSize: 7.5, color: "var(--grey)" }}
          >
            {T_HI}°
          </span>
          {/* breakpoint labels, centred on each tick */}
          {BAND_TICKS.map((t) => (
            <span
              key={t.c}
              className="absolute font-mono"
              style={{
                left: `${pct(t.c)}%`,
                transform: "translateX(-50%)",
                top: 0,
                fontSize: 7.5,
                color: t.danger ? "var(--paper)" : "var(--grey)",
              }}
            >
              {t.label}
            </span>
          ))}
          {/* band names sitting under the gradient as a quiet scale legend */}
          <div
            className="absolute inset-x-0 flex justify-between font-mono uppercase"
            style={{ top: 13, fontSize: 7, letterSpacing: "0.08em", color: "var(--grey)" }}
          >
            <span>comfortable</span>
            <span>caution</span>
            <span style={{ color: "var(--paper)" }}>dangerous</span>
            <span>severe</span>
          </div>
        </div>

        {/* the 32° danger line, called out as a contour key */}
        <div
          className="mt-1 flex items-center gap-1.5 font-mono"
          style={{ fontSize: 8, color: "var(--paper)" }}
        >
          <span
            aria-hidden
            style={{ borderTop: "1.5px dashed var(--paper)", width: 14, display: "inline-block" }}
          />
          32° dangerous line · shade eligible above 26°
        </div>
      </div>

      {/* CROWD — distinct cool ramp */}
      <div className="mt-3.5">
        <div
          className="font-mono uppercase"
          style={{ fontSize: 8.5, letterSpacing: "0.14em", color: "var(--paper)" }}
        >
          Crowd density <span style={{ color: "var(--grey)" }}>· permanent max</span>
        </div>
        <div
          className="mt-2 h-2.5"
          style={{
            background: crowdGradient,
            borderRadius: "var(--radius-sm)",
            boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--white) 8%, transparent)",
          }}
        />
        <div
          className="mt-1 flex justify-between font-mono uppercase"
          style={{ fontSize: 7.5, letterSpacing: "0.08em", color: "var(--grey)" }}
        >
          <span>sparse</span>
          <span>packed</span>
        </div>
      </div>

      {/* the hero teaching: hot × busy = shade — stated quietly */}
      <div
        className="mt-3.5 flex items-center gap-1.5 pt-2.5"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <span
          aria-hidden
          style={{
            width: 15,
            height: 10,
            borderRadius: 2,
            background: `rgb(${utciColor(35).join(",")})`,
            flexShrink: 0,
          }}
        />
        <span className="font-mono" style={{ fontSize: 9, color: "var(--grey)" }}>×</span>
        <span
          aria-hidden
          style={{
            width: 15,
            height: 10,
            borderRadius: 2,
            background: `rgb(${crowdColor(0.7).join(",")})`,
            flexShrink: 0,
          }}
        />
        <span className="font-mono" style={{ fontSize: 9, color: "var(--grey)" }}>=</span>
        <span
          aria-hidden
          style={{
            width: 15,
            height: 10,
            borderRadius: 2,
            background: "transparent",
            border: "1.5px solid var(--heat)",
            boxShadow: "0 0 0 2px color-mix(in srgb, var(--heat) 32%, transparent)",
            flexShrink: 0,
          }}
        />
        <span
          className="ml-0.5 font-mono uppercase leading-tight"
          style={{ fontSize: 8, letterSpacing: "0.08em", color: "var(--paper)" }}
        >
          where shade goes
        </span>
      </div>
      <p
        className="mt-1.5 font-mono leading-relaxed"
        style={{ fontSize: 9, color: "var(--grey)" }}
      >
        Hot <span style={{ color: "var(--paper)" }}>AND</span> busy cells flag and pulse — that's the
        shade-priority signal.
      </p>
    </div>
  );
}
