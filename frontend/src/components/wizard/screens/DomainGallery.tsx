import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { ArrowRight, ArrowLeft } from "iconoir-react";
import { EASE, DUR } from "@/lib/motion";
import { PixelMark } from "../PixelMark";
import { SCENARIOS, type ScenarioId } from "@/lib/scenarios";

/**
 * Beyond Festivals — domain gallery.
 *
 * The picker reached from the welcome screen's third door. Same IAAC editorial house
 * style as WelcomeScreen: giant FK Grotesk title, mono labels, ruled rows. Each row is
 * a domain (park / playground / plaza / beach) with a one-line "what U-Shade does here".
 * Choosing one threshold-wipes into the scenario workspace.
 */

const ACCENT_VAR: Record<string, string> = {
  green: "var(--green)",
  teal: "var(--teal)",
  amber: "var(--amber)",
  indigo: "var(--indigo)",
};

export function DomainGallery({
  onPick,
  onBack,
}: {
  onPick: (id: ScenarioId) => void;
  onBack: () => void;
}) {
  const reduce = useReducedMotion();
  const [leaving, setLeaving] = useState(false);

  function choose(id: ScenarioId) {
    setLeaving(true);
    setTimeout(() => onPick(id), reduce ? 0 : DUR.stage);
  }

  const rise = (delay: number) =>
    reduce
      ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.2 } }
      : {
          initial: { opacity: 0, y: 14 },
          animate: { opacity: 1, y: 0 },
          transition: { delay, duration: 0.6, ease: EASE.out },
        };

  return (
    <AnimatePresence>
      {!leaving && (
        <motion.div
          className="fixed inset-0 z-50 flex flex-col overflow-y-auto px-16 py-10"
          style={{ background: "var(--white)" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduce ? { opacity: 0 } : { clipPath: "inset(0 0 100% 0)", opacity: 0.4 }}
          transition={{ duration: DUR.stage / 1000, ease: EASE.inOut }}
        >
          {/* Masthead */}
          <motion.header {...rise(0.04)} className="shrink-0">
            <div className="flex items-end justify-between">
              <button
                type="button"
                onClick={onBack}
                className="flex items-center gap-2 transition-opacity hover:opacity-70"
                style={{ color: "var(--ink)" }}
              >
                <ArrowLeft className="size-4" strokeWidth={1.6} />
                <span className="text-label">BACK</span>
              </button>
              <span className="text-label" style={{ color: "var(--grey)" }}>
                IAAC BARCELONA · ONE ENGINE, ANY SITE
              </span>
            </div>
            <div className="mt-3 h-px w-full" style={{ background: "var(--ink)" }} />
          </motion.header>

          {/* Hero */}
          <div className="shrink-0 py-8">
            <motion.div {...rise(0.10)} className="mb-5 flex items-center gap-3">
              <PixelMark cell={5} gap={2} />
              <span className="text-label" style={{ color: "var(--teal)" }}>
                ↳ BEYOND FESTIVALS
              </span>
            </motion.div>
            <motion.h1
              {...rise(0.14)}
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 700,
                fontSize: "clamp(2.75rem, 6.5vw, 5rem)",
                lineHeight: 0.94,
                letterSpacing: "-0.04em",
                color: "var(--ink)",
              }}
            >
              The same tool,
              <br />
              anywhere people gather.
            </motion.h1>
            <motion.p {...rise(0.20)} className="text-editorial mt-6" style={{ color: "var(--ink)", maxWidth: "44ch" }}>
              U-Shade is a timeline crossed with crowd attractors crossed with a heat grid.
              Festivals are just one site. Pick another and watch the identical engine rank
              shade where it protects the most people.
            </motion.p>
            <motion.p {...rise(0.24)} className="mt-3 font-mono text-[10px] tracking-widest" style={{ color: "var(--grey)" }}>
              CONCEPT MOCKS · SYNTHETIC DATA · NO LIVE SIMULATION
            </motion.p>
          </div>

          {/* Domain rows */}
          <div className="shrink-0">
            {SCENARIOS.map((s, i) => (
              <DomainRow
                key={s.id}
                index={String(i + 1).padStart(2, "0")}
                label={s.label}
                site={s.site}
                tagline={s.tagline}
                attractorsNote={s.attractorsNote}
                accent={ACCENT_VAR[s.accent]}
                rise={rise(0.3 + i * 0.06)}
                reduce={!!reduce}
                onClick={() => choose(s.id)}
              />
            ))}
          </div>

          {/* Footer */}
          <motion.div
            {...rise(0.6)}
            className="mt-6 flex shrink-0 items-center justify-between border-t pt-3"
            style={{ borderColor: "var(--ink)" }}
          >
            <p className="font-mono text-[10px] leading-relaxed" style={{ color: "var(--grey)" }}>
              These are illustrative scenarios on fabricated data — they do not affect any
              festival project.
            </p>
            <span className="font-mono text-[10px] tracking-widest" style={{ color: "var(--grey)" }}>
              BEYOND / GALLERY
            </span>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function DomainRow({
  index,
  label,
  site,
  tagline,
  attractorsNote,
  accent,
  rise,
  reduce,
  onClick,
}: {
  index: string;
  label: string;
  site: string;
  tagline: string;
  attractorsNote: string;
  accent: string;
  rise: Record<string, unknown>;
  reduce: boolean;
  onClick: () => void;
}) {
  const [hover, setHover] = useState(false);
  return (
    <motion.button
      type="button"
      onClick={onClick}
      onHoverStart={() => setHover(true)}
      onHoverEnd={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
      whileTap={reduce ? undefined : { scale: 0.995 }}
      className="group relative flex w-full items-center gap-5 py-5 text-left"
      style={{ borderTop: "1px solid var(--ink)" }}
      {...rise}
    >
      <motion.span
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0"
        style={{ background: accent }}
        initial={false}
        animate={{ width: hover && !reduce ? "100%" : "0%" }}
        transition={{ duration: DUR.card / 1000, ease: EASE.out }}
      />
      <span className="relative font-mono text-sm tabular-nums" style={{ color: hover ? "var(--paper)" : "var(--grey)" }}>
        {index}
      </span>
      <span className="relative min-w-0 flex-1">
        <span className="flex items-baseline gap-3">
          <span
            className="block font-sans font-bold"
            style={{ fontSize: "1.45rem", letterSpacing: "-0.02em", color: hover ? "var(--paper)" : "var(--ink)" }}
          >
            {label}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-wider" style={{ color: hover ? "color-mix(in srgb, var(--paper) 75%, transparent)" : "var(--grey)" }}>
            {site}
          </span>
        </span>
        <span className="mt-0.5 block text-sm" style={{ color: hover ? "color-mix(in srgb, var(--paper) 88%, transparent)" : "var(--ink)" }}>
          {tagline}
        </span>
        <span className="mt-0.5 block font-mono text-[10px] uppercase tracking-wider" style={{ color: hover ? "color-mix(in srgb, var(--paper) 65%, transparent)" : "var(--grey)" }}>
          {attractorsNote}
        </span>
      </span>
      <motion.span
        className="relative shrink-0"
        animate={{ x: hover && !reduce ? 4 : 0 }}
        transition={{ duration: DUR.hover / 1000, ease: EASE.out }}
      >
        <ArrowRight className="size-6" strokeWidth={1.5} style={{ color: hover ? "var(--paper)" : "var(--ink)" }} />
      </motion.span>
    </motion.button>
  );
}
