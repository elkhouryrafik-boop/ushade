import { useEffect, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Check, WarningTriangle } from "iconoir-react";
import { useHeatGuard } from "@/lib/heatguard-store";
import { EASE } from "@/lib/motion";
import { ProvenanceBadge, type Tier } from "../ProvenanceBadge";

/**
 * S6 — Running the analysis (standalone). "Lights down, instruments up" (M2).
 *
 * The dark thermal surface is owned by the shell (data-theme="dark"). Here the
 * graticule ignites and each subsystem REPORTS as it actually lands — climate,
 * crowd, placement. Progress is the honest done-count; loop completion is gated
 * on real `allDone` status, never a fabricated timer (P3 / CCA-F P1).
 *
 * Motion discipline: every animation SETTLES. The only "live" cue is the single
 * running marker, which is a finite pulse-in (no repeat:Infinity — that pins the
 * CPU and blocks screenshots). Liveness is carried by the real progress bar
 * advancing as artifacts arrive. Respects useReducedMotion throughout.
 *
 * Contract FROZEN: props { steps, allDone, onContinue }. Restyle/re-time only.
 */

export type AnalysisStep = {
  key: string;
  label: string;
  detail: string;
  fact?: string;
  tier: Tier;
  state: "queued" | "running" | "done" | "failed";
};

interface AnalysisScreenProps {
  steps: AnalysisStep[];
  allDone: boolean;
  onContinue: () => void;
}

export function AnalysisScreen({ steps, allDone, onContinue }: AnalysisScreenProps) {
  const { dispatch } = useHeatGuard();
  const reduce = useReducedMotion();
  const [currentStepIdx, setCurrentStepIdx] = useState(0);

  const doneCount = steps.filter((s) => s.state === "done").length;
  const failed = steps.some((s) => s.state === "failed");
  const total = steps.length || 1;
  const runningStep = steps.find((s) => s.state === "running");
  // Honest percent: whole steps done + half-step credit while one runs.
  const pct = Math.round(((doneCount + (runningStep ? 0.5 : 0)) / total) * 100);

  useEffect(() => {
    const running = steps.findIndex((s) => s.state === "running");
    if (running >= 0) setCurrentStepIdx(running);
    else {
      const done = steps.filter((s) => s.state === "done").length;
      if (done > 0) setCurrentStepIdx(Math.min(done, steps.length - 1));
    }
  }, [steps]);

  // Advance only once real status says everything landed — status-driven, not a guess.
  useEffect(() => {
    if (allDone) {
      const t = setTimeout(onContinue, 700);
      return () => clearTimeout(t);
    }
  }, [allDone, onContinue]);

  const current = steps[currentStepIdx];

  return (
    <div className="relative flex h-full flex-col overflow-hidden px-6 py-6">
      {/* Graticule — the instrument grid igniting on the thermal black */}
      <Graticule reduce={!!reduce} />

      {/* ── Top bar: live tag + skip ─────────────────────────────────────── */}
      <div className="relative z-10 mb-6 flex items-center justify-between">
        <span
          className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.18em]"
          style={{ color: "var(--grey)" }}
        >
          <span
            className="size-1.5 rounded-full"
            style={{ background: failed ? "var(--red)" : "var(--green2)" }}
          />
          {failed ? "Run stopped" : "Thermal analysis · live"}
        </span>
        <button
          type="button"
          onClick={() => dispatch({ type: "setAnalyzing", analyzing: false })}
          className="font-mono text-[11px] uppercase tracking-wider transition-opacity hover:opacity-70"
          style={{ color: "var(--grey)" }}
        >
          Skip to result →
        </button>
      </div>

      {/* ── Hero: dramatic step readout ──────────────────────────────────── */}
      <div className="relative z-10 mb-7">
        <p
          className="text-label mb-2 font-mono"
          style={{ color: failed ? "var(--red)" : "var(--grey)" }}
        >
          {failed
            ? "SUBSYSTEM FAULT"
            : allDone
            ? "ALL SUBSYSTEMS REPORTED"
            : `STEP ${Math.min(currentStepIdx + 1, total)} / ${total}`}
        </p>
        {current && (
          <AnimatePresence mode="wait">
            <motion.div
              key={current.key}
              initial={reduce ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
              transition={reduce ? { duration: 0 } : { duration: 0.4, ease: EASE.out }}
            >
              <p className="text-display" style={{ color: "var(--paper)", lineHeight: 1.0 }}>
                {current.label}
              </p>
              <p
                className="text-editorial mt-2"
                style={{ color: "var(--grey)", fontSize: "1.02rem" }}
              >
                {failed
                  ? "A subsystem failed to land. Check the backend, then re-run."
                  : current.detail}
              </p>
            </motion.div>
          </AnimatePresence>
        )}

        {/* Honest progress — done-count only */}
        <div className="mt-5">
          <div className="flex items-baseline justify-between">
            <span
              className="font-mono text-[11px] uppercase tracking-wider"
              style={{ color: "var(--grey)" }}
            >
              {doneCount} of {total} complete
            </span>
            <span
              className="font-mono text-sm tabular-nums"
              style={{ color: "var(--paper)" }}
            >
              {pct}%
            </span>
          </div>
          <div
            className="mt-2 h-1 w-full overflow-hidden"
            style={{ background: "color-mix(in srgb, var(--grey) 22%, transparent)" }}
          >
            <motion.div
              className="h-full"
              style={{ background: failed ? "var(--red)" : "var(--green2)" }}
              initial={false}
              animate={{ width: `${pct}%` }}
              transition={reduce ? { duration: 0 } : { duration: 0.6, ease: EASE.out }}
            />
          </div>
        </div>
      </div>

      {/* ── Timeline: subsystems report as they land ─────────────────────── */}
      <div className="relative z-10 flex flex-col gap-0">
        {steps.map((step, i) => {
          const isDone = step.state === "done";
          const isRunning = step.state === "running";
          const isFailed = step.state === "failed";
          const last = i === steps.length - 1;
          const num = String(i + 1).padStart(2, "0");

          return (
            <motion.div
              key={step.key}
              className="flex items-start gap-4"
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={
                reduce ? { duration: 0 } : { duration: 0.5, delay: i * 0.18, ease: EASE.inOut }
              }
            >
              {/* Marker + connector */}
              <div className="flex flex-col items-center">
                <div
                  className="flex size-6 shrink-0 items-center justify-center rounded-full"
                  style={{
                    background: isDone ? "var(--green2)" : isFailed ? "var(--red)" : "transparent",
                    border:
                      isDone || isFailed
                        ? "none"
                        : isRunning
                        ? "1px solid var(--green2)"
                        : "1px solid color-mix(in srgb, var(--grey) 45%, transparent)",
                  }}
                >
                  {isDone && (
                    <Check className="size-3.5" style={{ color: "var(--ink)" }} strokeWidth={3} />
                  )}
                  {isFailed && (
                    <WarningTriangle
                      className="size-3.5"
                      style={{ color: "var(--white)" }}
                      strokeWidth={2}
                    />
                  )}
                  {isRunning && (
                    // Finite pulse-in — settles immediately (NO repeat loop).
                    <motion.span
                      className="size-2.5 rounded-full"
                      style={{ background: "var(--green2)" }}
                      initial={reduce ? false : { scale: 0.4, opacity: 0.5 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={reduce ? { duration: 0 } : { duration: 0.45, ease: EASE.out }}
                    />
                  )}
                  {step.state === "queued" && (
                    <span
                      className="font-mono text-[10px] font-semibold tabular-nums"
                      style={{ color: "color-mix(in srgb, var(--grey) 55%, transparent)" }}
                    >
                      {num}
                    </span>
                  )}
                </div>
                {!last && (
                  <div
                    className="w-px grow"
                    style={{
                      minHeight: "34px",
                      background: isDone
                        ? "var(--green2)"
                        : "color-mix(in srgb, var(--grey) 22%, transparent)",
                    }}
                  />
                )}
              </div>

              {/* Step text */}
              <div className="min-w-0 flex-1 pb-7">
                <div className="flex items-center gap-2">
                  <span
                    className="font-mono text-[11px] font-semibold uppercase tracking-wider"
                    style={{
                      color:
                        isDone || isRunning
                          ? "var(--paper)"
                          : isFailed
                          ? "var(--red)"
                          : "color-mix(in srgb, var(--grey) 50%, transparent)",
                    }}
                  >
                    {num} · {step.label}
                  </span>
                  <ProvenanceBadge tier={step.tier} compact />
                </div>
                <p
                  className="mt-1 font-mono text-[11px] uppercase tracking-wider"
                  style={{
                    color: isFailed
                      ? "var(--red)"
                      : isDone
                      ? "var(--green2)"
                      : isRunning
                      ? "var(--paper)"
                      : "color-mix(in srgb, var(--grey) 50%, transparent)",
                  }}
                >
                  {isFailed ? "Failed" : isDone ? "Complete" : isRunning ? "Running…" : "Queued"}
                </p>
                <AnimatePresence>
                  {isDone && step.fact && (
                    <motion.p
                      initial={reduce ? false : { opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={reduce ? { duration: 0 } : { duration: 0.3, ease: EASE.out }}
                      className="mt-1 overflow-hidden font-mono text-xs"
                      style={{ color: "var(--paper)" }}
                    >
                      {step.fact}
                    </motion.p>
                  )}
                </AnimatePresence>
                {isRunning && (
                  <p className="mt-1 font-mono text-[11px]" style={{ color: "var(--grey)" }}>
                    {step.detail}
                  </p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* ── Done / fail CTA ──────────────────────────────────────────────── */}
      <AnimatePresence>
        {(allDone || failed) && (
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reduce ? { duration: 0 } : { duration: 0.4, ease: EASE.out }}
            className="relative z-10 mt-auto pt-4"
          >
            {failed && (
              <p
                className="mb-2.5 font-mono text-[11px] leading-relaxed"
                style={{ color: "var(--red)" }}
              >
                A step failed — no fake spin. Check the backend at :8000, then re-run.
              </p>
            )}
            <button
              type="button"
              onClick={onContinue}
              className="flex h-11 w-full items-center justify-center gap-2 font-sans font-bold transition-opacity hover:opacity-90"
              style={{
                background: failed ? "var(--red)" : "var(--green2)",
                color: failed ? "var(--white)" : "var(--ink)",
                borderRadius: "var(--radius-sm)",
                letterSpacing: "0.04em",
                fontSize: "0.875rem",
              }}
            >
              {failed ? "Back to layout" : "View results →"}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * The graticule — a faint instrument grid that ignites once on entry, then holds.
 * IAAC pixel-block motif: a few scattered squares warm to the thermal accent.
 * Pure decoration of a REAL event (the run starting); settles, never loops.
 */
function Graticule({ reduce }: { reduce: boolean }) {
  // Static scatter (deterministic) so it reads as an instrument, not noise.
  const cells = [
    { x: "12%", y: "22%", d: 0.1 },
    { x: "82%", y: "14%", d: 0.25 },
    { x: "68%", y: "40%", d: 0.4 },
    { x: "22%", y: "68%", d: 0.55 },
    { x: "88%", y: "74%", d: 0.3 },
    { x: "44%", y: "86%", d: 0.5 },
  ];
  return (
    <div className="pointer-events-none absolute inset-0 z-0" aria-hidden="true">
      {/* Hairline grid */}
      <motion.div
        className="absolute inset-0"
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={reduce ? { duration: 0 } : { duration: 1.1, ease: EASE.out }}
        style={{
          backgroundImage:
            "linear-gradient(color-mix(in srgb, var(--grey) 14%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--grey) 14%, transparent) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse at 50% 40%, black 30%, transparent 78%)",
          WebkitMaskImage: "radial-gradient(ellipse at 50% 40%, black 30%, transparent 78%)",
        }}
      />
      {/* Scattered pixel blocks warming to the accent */}
      {cells.map((c, i) => (
        <motion.span
          key={i}
          className="absolute size-2"
          style={{ left: c.x, top: c.y, background: "var(--green2)" }}
          initial={reduce ? false : { opacity: 0, scale: 0.6 }}
          animate={{ opacity: 0.22, scale: 1 }}
          transition={
            reduce ? { duration: 0 } : { duration: 0.5, delay: 0.6 + c.d, ease: EASE.out }
          }
        />
      ))}
    </div>
  );
}
