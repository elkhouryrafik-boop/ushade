import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { ArrowRight, Check, WarningTriangle, Group, Coins, Calendar, SineWave, Microphone, Clock, Plus, Xmark, Pin, MapPin } from "iconoir-react";
import { useHeatGuard, type LineupSlot } from "@/lib/heatguard-store";
import { useForumSite } from "@/lib/forum-site";
import { StageScaffold } from "../StageScaffold";
import { EASE } from "@/lib/motion";

/**
 * S4 — Tell us about your festival.
 * Mode A: Paste a brief (textarea, Clarendon font).
 * Mode B: Guided 4-field form.
 * Parse result streams in one field at a time as an editorial datum readout.
 * LLM parse via /api/run/parse — never auto-runs shade.
 */

type Mode = "paste" | "form";

// Monotonic id source for new lineup rows (stable across re-renders).
let _slotSeq = 0;
const nextSlotId = () => ++_slotSeq;

const DRAWS: LineupSlot["draw"][] = ["support", "main", "headliner"];

interface ParsedFields {
  capacity?: number;
  budget?: number;
  date?: string;
  theme?: string;
}

const FIELD_ICON = {
  capacity: Group,
  budget: Coins,
  date: Calendar,
  theme: SineWave,
} as const;

export function BriefScreen() {
  const { state, dispatch } = useHeatGuard();
  const [mode, setMode] = useState<Mode>("paste");
  const [brief, setBrief] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState<ParsedFields>({});
  const [parseError, setParseError] = useState<string | null>(null);
  const reduce = useReducedMotion();
  const forum = useForumSite();

  // Load the real Parc del Fòrum site (boundary + read-only POIs) + prefill the demo
  // brief, then jump to the Site stage so the architect sees the geometry land.
  async function loadForum() {
    const ok = await forum.load({ withBriefFacts: true });
    if (ok) dispatch({ type: "setStage", stage: "site" });
  }

  // Direct form values (Mode B)
  const [capacity, setCapacity] = useState(String(state.project.capacity || ""));
  const [budget, setBudget] = useState(String(state.project.budget || ""));
  const [date, setDate] = useState(state.project.date || "");
  const [theme, setTheme] = useState(state.project.theme || "");

  // The bill — who plays, where, when. Drives the daytime crowd migration.
  const [lineup, setLineup] = useState<LineupSlot[]>(state.project.lineup ?? []);

  // Persist the lineup to the store independently of the four-facts gate, so
  // editing the bill is never lost even when the user hasn't completed the facts
  // (confirm() is gated; this is not). Mutators set local state AND mirror the
  // cleaned lineup into the store via the same setProject action.
  const persistLineup = (next: LineupSlot[]) => {
    setLineup(next);
    const cleanLineup = next.filter((s) => s.act.trim() || s.stage.trim());
    dispatch({ type: "setProject", patch: { lineup: cleanLineup } });
  };
  const addSlot = () =>
    persistLineup([
      ...lineup,
      { id: `ln-${nextSlotId()}`, act: "", stage: "", start: "", end: "", draw: "main" },
    ]);
  const updateSlot = (id: string, patch: Partial<LineupSlot>) =>
    persistLineup(lineup.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  const removeSlot = (id: string) => persistLineup(lineup.filter((s) => s.id !== id));

  const allFilled = mode === "paste"
    ? (parsed.capacity != null && parsed.budget != null && parsed.date && parsed.theme)
    : (capacity && budget && date && theme);

  async function parseBrief() {
    if (!brief.trim()) return;
    setParsing(true);
    setParseError(null);
    setParsed({});
    // True only for the expected "endpoint not yet live" case (network reject or
    // 404/501) — anything else is a real failure we must surface, not swallow.
    let endpointNotLive = false;
    try {
      let res: Response;
      try {
        res = await fetch("/api/run/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ brief }),
        });
      } catch {
        // fetch rejected → no server listening / network down → treat as not live.
        endpointNotLive = true;
        throw new Error("Parse endpoint not reachable");
      }
      if (res.status === 404 || res.status === 501) {
        // Route not mounted yet → expected during early dev.
        endpointNotLive = true;
        throw new Error(`Parse API ${res.status}`);
      }
      if (!res.ok) throw new Error(`Parse failed — server returned ${res.status}`);
      const data: ParsedFields = await res.json();
      // Stream in one field at a time (staggered reveal)
      const keys = Object.keys(data) as (keyof ParsedFields)[];
      for (let i = 0; i < keys.length; i++) {
        await new Promise<void>((r) => setTimeout(r, 150 * i));
        setParsed((prev) => ({ ...prev, [keys[i]]: data[keys[i]] }));
      }
    } catch (err) {
      if (!endpointNotLive) {
        // Real outage / 5xx / malformed response — surface it, don't hide it.
        setParseError(
          err instanceof Error ? err.message : "Couldn't parse the brief — please try again."
        );
        return; // finally still resets parsing; skip the client-side fallback.
      }
      // Parse endpoint not yet live — use client-side extraction
      const cap = brief.match(/(\d[\d,]+)\s*(?:people|capacity|attendees)/i);
      // Capture the trailing k/K so "€15k" → 15000, not 15.
      const bud = brief.match(/€?\$?\s*(\d[\d,.]*)\s*([kK])?/);
      const yr = brief.match(/20\d\d/);
      let budget: number | undefined;
      if (bud) {
        const n = parseFloat(bud[1].replace(/[, ]/g, ""));
        if (!Number.isNaN(n)) budget = bud[2] ? n * 1000 : n;
      }
      setParsed({
        capacity: cap ? parseInt(cap[1].replace(/,/g, "")) : undefined,
        budget,
        date: yr ? `${yr[0]}-06-01` : undefined,
        theme: brief.length > 30 ? brief.slice(0, 80) + "…" : undefined,
      });
    } finally {
      setParsing(false);
    }
  }

  function confirm() {
    const proj = mode === "form"
      ? {
          capacity: parseInt(capacity) || state.project.capacity,
          budget: parseInt(budget) || state.project.budget,
          date: date || state.project.date,
          theme: theme || state.project.theme,
        }
      : {
          capacity: parsed.capacity ?? state.project.capacity,
          budget: parsed.budget ?? state.project.budget,
          date: parsed.date ?? state.project.date,
          theme: parsed.theme ?? state.project.theme,
        };
    // The lineup is shared by both modes — it always rides along.
    const cleanLineup = lineup.filter((s) => s.act.trim() || s.stage.trim());
    dispatch({ type: "setProject", patch: { ...proj, lineup: cleanLineup } });
    dispatch({ type: "setStage", stage: "site" });
  }

  const FIELDS = [
    { key: "capacity" as const, label: "Capacity", unit: "people", val: mode === "paste" ? parsed.capacity : parseInt(capacity) || undefined },
    { key: "budget" as const, label: "Budget", unit: "€", val: mode === "paste" ? parsed.budget : parseInt(budget) || undefined },
    { key: "date" as const, label: "Date", unit: "", val: mode === "paste" ? parsed.date : date || undefined },
    { key: "theme" as const, label: "Theme", unit: "", val: mode === "paste" ? parsed.theme : theme || undefined },
  ];

  return (
    <StageScaffold
      index="01 / BRIEF"
      title="Tell us about your festival"
      lede="The facts plus your lineup — who plays where and when is what migrates the crowd across the day, so the engine can rank shade where it'll actually be."
      cta={
        allFilled
          ? { label: "Confirm these details →", onClick: confirm }
          : undefined
      }
    >
      {/* One-click demo-site shortcut — load the real Parc del Fòrum (boundary + POIs)
          and prefill the Primavera brief, skipping straight to the site geometry. */}
      <div
        className="mb-6 flex items-center gap-3 px-4 py-3"
        style={{
          background: "color-mix(in srgb, var(--green) 6%, transparent)",
          border: "1px solid color-mix(in srgb, var(--green) 35%, var(--border))",
          borderRadius: "var(--radius-sm)",
        }}
      >
        <MapPin className="size-4 shrink-0" strokeWidth={1.5} style={{ color: "var(--green)" }} />
        <div className="min-w-0 flex-1">
          <p className="font-sans text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            Try Parc del Fòrum
          </p>
          <p className="font-mono text-[10.5px] leading-snug" style={{ color: "var(--grey)" }}>
            Loads the real boundary, stages &amp; amenities — skip ahead to the geometry.
          </p>
        </div>
        <button
          type="button"
          onClick={loadForum}
          disabled={forum.loading}
          className="flex h-9 shrink-0 items-center gap-1.5 px-3.5 font-sans font-bold transition-opacity hover:opacity-90 disabled:opacity-60"
          style={{
            background: "var(--green)",
            color: "var(--paper)",
            borderRadius: "var(--radius-sm)",
            letterSpacing: "0.02em",
            fontSize: "0.8rem",
          }}
        >
          {forum.loading ? "Loading…" : "Load site"}
          {!forum.loading && <ArrowRight className="size-3.5" strokeWidth={2} />}
        </button>
      </div>
      {forum.error && (
        <p className="-mt-3 mb-5 flex items-center gap-1.5 font-mono text-[11px]" style={{ color: "var(--red)" }}>
          <WarningTriangle className="size-3.5" strokeWidth={1.5} />
          {forum.error}
        </p>
      )}

      {/* Mode tabs — editorial mono toggle, ruled baseline */}
      <div className="mb-6 flex" style={{ borderBottom: "1px solid var(--border)" }}>
        {(["paste", "form"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className="relative flex-1 pb-2.5 pt-1 text-label transition-colors"
            style={{
              color: mode === m ? "var(--text-primary)" : "var(--grey)",
              background: "transparent",
            }}
          >
            {m === "paste" ? "Paste a brief" : "Answer questions"}
            {mode === m && (
              <motion.span
                layoutId="brief-tab-underline"
                className="absolute -bottom-px left-0 right-0"
                style={{ height: "2px", background: "var(--text-primary)" }}
                transition={reduce ? { duration: 0 } : { duration: 0.25, ease: EASE.out }}
              />
            )}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {mode === "paste" ? (
          <motion.div
            key="paste"
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            <p className="text-label mb-2" style={{ color: "var(--grey)" }}>
              Describe it in a sentence
            </p>
            <textarea
              className="w-full resize-none p-4 leading-relaxed focus:outline-none focus:ring-1 focus:ring-ring placeholder:text-[var(--grey)]"
              style={{
                minHeight: "150px",
                fontFamily: "var(--font-editorial)",
                fontSize: "clamp(1.05rem, 1.8vw, 1.35rem)",
                color: "var(--text-primary)",
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
              }}
              placeholder="A 12,000-capacity electronic festival on the Barcelona waterfront, late June, natural-canopy aesthetic…"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
            />
            <button
              type="button"
              onClick={parseBrief}
              disabled={!brief.trim() || parsing}
              className="mt-3 flex items-center gap-2 px-4 py-2.5 font-sans font-semibold transition-colors"
              style={{
                background: !brief.trim() || parsing ? "var(--grey)" : "var(--text-primary)",
                color: "var(--surface)",
                borderRadius: "var(--radius-sm)",
                opacity: !brief.trim() || parsing ? 0.6 : 1,
                fontSize: "0.875rem",
                letterSpacing: "0.02em",
              }}
            >
              {parsing ? "Reading…" : "Extract the four facts"}
              {!parsing && <ArrowRight className="size-4" strokeWidth={2} />}
            </button>

            {/* Streamed parse results — editorial datum readout */}
            {Object.keys(parsed).length > 0 && (
              <div className="mt-7">
                <p className="text-label" style={{ color: "var(--grey)" }}>
                  Parsed fields · confirmation
                </p>
                <dl className="mt-3">
                  {FIELDS.map((f, i) => (
                    <DatumRow
                      key={f.key}
                      fieldKey={f.key}
                      label={f.label}
                      unit={f.unit}
                      val={f.val}
                      index={i}
                      first={i === 0}
                      reduce={!!reduce}
                    />
                  ))}
                </dl>
              </div>
            )}
          </motion.div>
        ) : (
          <motion.div
            key="form"
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            <p className="text-label mb-3" style={{ color: "var(--grey)" }}>
              Four facts
            </p>
            <div>
              {[
                { label: "Capacity", iconKey: "capacity" as const, unit: "people", value: capacity, onChange: setCapacity, type: "number", placeholder: "12000" },
                { label: "Budget", iconKey: "budget" as const, unit: "€", value: budget, onChange: setBudget, type: "number", placeholder: "15000" },
                { label: "Date", iconKey: "date" as const, unit: "", value: date, onChange: setDate, type: "date", placeholder: "" },
                { label: "Theme / aesthetic", iconKey: "theme" as const, unit: "", value: theme, onChange: setTheme, type: "text", placeholder: "Natural canopy, reclaimed timber…" },
              ].map((field, i) => {
                const Icon = FIELD_ICON[field.iconKey];
                const filled = !!field.value;
                return (
                  <div
                    key={field.label}
                    className="py-3.5"
                    style={{ borderTop: i === 0 ? "1px solid var(--text-primary)" : "1px solid var(--border)" }}
                  >
                    <label className="mb-2 flex items-center gap-2 text-label" style={{ color: "var(--grey)" }}>
                      <Icon className="size-3.5" strokeWidth={1.5} style={{ color: filled ? "var(--green)" : "var(--grey)" }} />
                      {field.label.toUpperCase()}
                    </label>
                    <div className="relative">
                      {field.unit && (
                        <span
                          className="absolute left-3 top-1/2 -translate-y-1/2 font-mono text-sm"
                          style={{ color: "var(--grey)" }}
                        >
                          {field.unit}
                        </span>
                      )}
                      <input
                        type={field.type}
                        value={field.value}
                        onChange={(e) => field.onChange(e.target.value)}
                        placeholder={field.placeholder}
                        className="w-full py-3 pr-9 font-mono tabular-nums focus:outline-none focus:ring-1 focus:ring-ring placeholder:text-[var(--grey)]"
                        style={{
                          paddingLeft: field.unit ? "2rem" : "0.75rem",
                          background: "var(--surface)",
                          border: "1px solid var(--border)",
                          borderRadius: "var(--radius-sm)",
                          color: "var(--text-primary)",
                          fontSize: "0.875rem",
                        }}
                      />
                      {filled && (
                        <span className="absolute right-3 top-1/2 -translate-y-1/2">
                          <Check className="size-4" strokeWidth={2} style={{ color: "var(--green)" }} />
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── LINEUP & SCHEDULE — the bill that powers the crowd simulator ──────── */}
      <section className="mt-9">
        <div className="flex items-baseline justify-between">
          <p className="flex items-center gap-2 text-label" style={{ color: "var(--grey)" }}>
            <Microphone className="size-3.5" strokeWidth={1.5} />
            Lineup &amp; schedule
          </p>
          <span className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--grey)" }}>
            {lineup.length} act{lineup.length === 1 ? "" : "s"}
          </span>
        </div>
        <p className="mt-1 font-mono text-[11px] leading-relaxed" style={{ color: "var(--grey)", maxWidth: "52ch" }}>
          Who's on, where, and when. The crowd migrates to whichever stage is playing —
          headliners pull hardest — so shade lands where the crowd actually is, hour by hour.
        </p>

        <div className="mt-4" style={{ borderTop: "1px solid var(--text-primary)" }}>
          {lineup.length === 0 && (
            <p className="py-4 font-mono text-[11px]" style={{ color: "var(--grey)" }}>
              No acts yet — add the bill so the sim knows where the crowd goes.
            </p>
          )}
          {lineup.map((slot) => (
            <div
              key={slot.id}
              className="grid items-center gap-2 py-2.5"
              style={{ gridTemplateColumns: "1.5fr 1.4fr auto auto auto auto", borderBottom: "1px solid var(--border)" }}
            >
              <SlotInput icon={<Microphone className="size-3" strokeWidth={1.5} />} placeholder="Act / artist" value={slot.act} onChange={(v) => updateSlot(slot.id, { act: v })} />
              <SlotInput icon={<Pin className="size-3" strokeWidth={1.5} />} placeholder="Stage" value={slot.stage} onChange={(v) => updateSlot(slot.id, { stage: v })} />
              <SlotInput type="time" icon={<Clock className="size-3" strokeWidth={1.5} />} value={slot.start} onChange={(v) => updateSlot(slot.id, { start: v })} compact />
              <SlotInput type="time" value={slot.end} onChange={(v) => updateSlot(slot.id, { end: v })} compact />
              <select
                value={slot.draw}
                onChange={(e) => updateSlot(slot.id, { draw: e.target.value as LineupSlot["draw"] })}
                className="font-mono text-[10px] uppercase tracking-wider focus:outline-none focus:ring-1 focus:ring-ring"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", color: "var(--text-primary)", padding: "0.4rem 0.3rem" }}
                aria-label="Crowd draw"
              >
                {DRAWS.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => removeSlot(slot.id)}
                className="flex size-7 items-center justify-center transition-opacity hover:opacity-70"
                style={{ color: "var(--grey)" }}
                aria-label="Remove act"
              >
                <Xmark className="size-3.5" strokeWidth={2} />
              </button>
            </div>
          ))}
        </div>

        <button
          type="button"
          onClick={addSlot}
          className="mt-3 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider transition-opacity hover:opacity-70"
          style={{ color: "var(--text-primary)" }}
        >
          <Plus className="size-3.5" strokeWidth={2} />
          Add act
        </button>
      </section>

      {parseError && (
        <p className="mt-3 text-label" style={{ color: "var(--red)" }}>{parseError}</p>
      )}
    </StageScaffold>
  );
}

/* ── One lineup-row input (act / stage / time) ─────────────────────────────── */
function SlotInput({
  icon,
  placeholder,
  value,
  onChange,
  type = "text",
  compact,
}: {
  icon?: React.ReactNode;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  compact?: boolean;
}) {
  return (
    <div className="relative flex items-center">
      {icon && (
        <span className="pointer-events-none absolute left-2" style={{ color: "var(--grey)" }}>
          {icon}
        </span>
      )}
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full font-mono text-[12px] focus:outline-none focus:ring-1 focus:ring-ring placeholder:text-[var(--grey)]"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          color: "var(--text-primary)",
          padding: compact ? "0.4rem 0.4rem" : "0.4rem 0.5rem",
          paddingLeft: icon ? "1.5rem" : undefined,
        }}
      />
    </div>
  );
}

/* ── A single parsed datum — found (value + check) or missing (amber flag) ──── */
function DatumRow({
  fieldKey,
  label,
  unit,
  val,
  index,
  first,
  reduce,
}: {
  fieldKey: keyof ParsedFields;
  label: string;
  unit: string;
  val: string | number | undefined;
  index: number;
  first: boolean;
  reduce: boolean;
}) {
  const Icon = FIELD_ICON[fieldKey];
  const found = val != null;
  const display = found
    ? `${unit === "€" ? "€" : ""}${typeof val === "number" ? val.toLocaleString() : val}${unit && unit !== "€" ? ` ${unit}` : ""}`
    : null;

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: reduce ? 0 : index * 0.06, duration: 0.3, ease: EASE.out }}
      className="flex items-center justify-between gap-3 py-3"
      style={{ borderTop: first ? "1px solid var(--text-primary)" : "1px solid var(--border)" }}
    >
      <dt className="flex items-center gap-2 text-label" style={{ color: "var(--grey)" }}>
        <Icon className="size-3.5" strokeWidth={1.5} style={{ color: found ? "var(--green)" : "var(--amber)" }} />
        {label}
      </dt>
      {found ? (
        <dd className="flex items-center gap-2">
          <span className="max-w-[12rem] truncate font-mono text-sm tabular-nums" style={{ color: "var(--text-primary)" }}>
            {display}
          </span>
          <Check className="size-4 shrink-0" strokeWidth={2} style={{ color: "var(--green)" }} />
        </dd>
      ) : (
        <dd className="flex items-center gap-1.5">
          <WarningTriangle className="size-3.5" strokeWidth={1.5} style={{ color: "var(--amber)" }} />
          <span className="font-mono text-[11px]" style={{ color: "var(--amber)" }}>
            Needs attention
          </span>
        </dd>
      )}
    </motion.div>
  );
}
