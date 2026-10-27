import { useState } from "react";
import { NavArrowDown, NavArrowUp, Eye, EyeClosed } from "iconoir-react";
import { cn } from "@/lib/utils";
import { ProvenanceBadge, type Tier } from "./ProvenanceBadge";

/**
 * LayerToggle (UI-SPEC §3.3 / §4.2) — collapsible panel pinned top-right of the
 * map well. Each row carries its layer's ProvenanceBadge and an honest per-layer
 * status (live / stale / unavailable). Single field at a time keeps each pure; this
 * is the always-available fallback for the bivariate Cross.
 *
 * Reworked as a dark-native instrument: near-black panel, mono uppercase header, an
 * eye glyph per row instead of a default-kit checkbox so on/off reads at a glance.
 * Public props (`layers`, `onToggle`) and the `cn` re-export are unchanged.
 */

export type LayerRow = {
  id: string;
  label: string;
  tier: Tier;
  on: boolean;
  /** Honest per-layer state: live data, a stale snapshot, or unavailable. */
  status?: "live" | "stale" | "unavailable";
};

const PANEL_BG = "color-mix(in srgb, var(--black) 78%, transparent)";

export function LayerToggle({
  layers,
  onToggle,
}: {
  layers: LayerRow[];
  onToggle: (id: string) => void;
}) {
  const [open, setOpen] = useState(true);
  if (layers.length === 0) return null;

  return (
    <div
      className="pointer-events-auto absolute right-4 top-4 z-20 w-56 overflow-hidden backdrop-blur-md"
      style={{
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        background: PANEL_BG,
        boxShadow: "0 8px 28px rgba(0,0,0,0.55)",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-3 py-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="text-label" style={{ color: "var(--paper)" }}>
          Map layers
        </span>
        {open ? (
          <NavArrowUp className="size-3.5" style={{ color: "var(--grey)" }} strokeWidth={2} />
        ) : (
          <NavArrowDown className="size-3.5" style={{ color: "var(--grey)" }} strokeWidth={2} />
        )}
      </button>

      {open && (
        <ul style={{ borderTop: "1px solid var(--border)", padding: "4px" }}>
          {layers.map((l) => {
            const dim = l.status === "unavailable";
            return (
              <li key={l.id}>
                {/* a <label> wrapping a visually-hidden checkbox keeps native toggle
                    semantics (and avoids nesting the ProvenanceBadge <button> inside
                    another <button>). The eye glyph is the visible on/off cue. */}
                <label
                  className={cn(
                    "flex items-center gap-2.5 rounded-[2px] px-2 py-1.5 transition-colors",
                    !dim && "cursor-pointer hover:bg-[color-mix(in_srgb,var(--paper)_8%,transparent)]",
                    dim && "cursor-not-allowed opacity-45",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={l.on}
                    disabled={dim}
                    onChange={() => onToggle(l.id)}
                    className="sr-only"
                  />
                  {/* eye glyph = the on/off cue (replaces the default checkbox) */}
                  {l.on ? (
                    <Eye
                      className="size-4 shrink-0"
                      style={{ color: "var(--green2)" }}
                      strokeWidth={1.8}
                    />
                  ) : (
                    <EyeClosed
                      className="size-4 shrink-0"
                      style={{ color: "var(--grey)" }}
                      strokeWidth={1.8}
                    />
                  )}
                  <span
                    className="flex-1 font-sans text-[13px]"
                    style={{ color: l.on ? "var(--paper)" : "var(--grey)" }}
                  >
                    {l.label}
                  </span>
                  {l.status === "stale" && (
                    <span
                      className="font-mono text-[9px] uppercase tracking-wider"
                      style={{ color: "var(--amber)" }}
                    >
                      stale
                    </span>
                  )}
                  {l.status === "unavailable" && (
                    <span
                      className="font-mono text-[9px] uppercase tracking-wider"
                      style={{ color: "var(--grey)" }}
                    >
                      n/a
                    </span>
                  )}
                  <ProvenanceBadge tier={l.tier} compact />
                </label>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export { cn };
