import { motion, useReducedMotion } from "framer-motion";
import { Check, WarningTriangle, ArrowRight } from "iconoir-react";
import { ProvenanceBadge, type Tier } from "./ProvenanceBadge";
import { EASE } from "@/lib/motion";

/**
 * AnalysisChecklist — S6 "lights down, instruments up".
 *
 * The wait IS the show: on the dark thermal surface (data-theme="dark" applied by
 * the shell), each subsystem reports as it REALLY lands. Steps flip
 * queued → running → done as real engine artifacts arrive — never a fake timer
 * (P3 / CCA-F P1). Progress is the honest done-count, nothing more.
 *
 * Contract is FROZEN: props are { steps, allDone, onContinue }. AnalysisStep shape
 * unchanged. This file only restyles + re-times — no data-flow changes.
 *
 * Motion: steps reveal once with a staggered ease-in-out enter (like the heat grid
 * developing cell-by-cell). NO infinite pulse/spin loops — the only live motion is
 * the single running marker, and it stops the moment the run is idle/done.
 */

export type StepState = "queued" | "running" | "done" | "failed";

export interface AnalysisStep {
  key: string;
  label: string;
  detail: string;
  waitingOn: string;
  fact?: string;
  tier: Tier;
  state: StepState;
}

export function AnalysisChecklist({
  steps,
  allDone,
  onContinue,
}: {
  steps: AnalysisStep[];
  allDone: boolean;
  onContinue: () => void;
}) {
  const reduce = useReducedMotion();
  const doneCount = steps.filter((s) => s.state === "done").length;
  const failed = steps.some((s) => s.state === "failed");
  const total = steps.length || 1;
  const runningStep = steps.find((s) => s.state === "running");
  const currentStep = runningStep ?? steps[Math.min(doneCount, steps.length - 1)];
  // Honest percent: whole steps done, plus a half-step credit while one runs.
  const pct = Math.round(((doneCount + (runningStep ? 0.5 : 0)) / total) * 100);
  const currentIndex = runningStep
    ? steps.indexOf(runningStep)
    : Math.min(doneCount, steps.length - 1);

  return (
    <div className="relative flex h-full flex-col overflow-hidden px-6 py-6">
      {/* Graticule — the instrument grid igniting on the thermal black (M2). */}
      <Graticule reduce={!!reduce} failed={failed} />

      {/* Skip — calm, top-right (skippable to result, per spec) */}
      <div className="relative z-10 mb-5 flex items-center justify-between">
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
          onClick={onContinue}
          className="flex items-center gap-1 font-mono text-[11px] uppercase tracking-wider transition-opacity hover:opacity-70"
          style={{ color: "var(--grey)" }}
        >
          Skip to result <ArrowRight className="size-3" strokeWidth={2} />
        </button>
      </div>

      {/* Hero — one big readout: which step of how many, plain language */}
      <div className="relative z-10 mb-5">
        <p
          className="text-label mb-2 font-mono"
          style={{ color: failed ? "var(--red)" : "var(--grey)" }}
        >
          {failed
            ? "SUBSYSTEM FAULT"
            : allDone
            ? "ALL SUBSYSTEMS REPORTED"
            : `STEP ${Math.min(currentIndex + 1, total)} / ${total}`}
        </p>
        {currentStep && (
          <>
            <p className="text-display" style={{ color: "var(--paper)", lineHeight: 1.02 }}>
              {currentStep.label}
            </p>
            <p
              className="text-editorial mt-2"
              style={{ color: "var(--grey)", fontSize: "1rem" }}
            >
              {failed
                ? "A subsystem failed to land. Check the backend, then re-run."
                : currentStep.detail}
            </p>
          </>
        )}

        {/* Honest progress bar — driven only by the real done-count */}
        <div className="mt-4">
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-[11px] uppercase tracking-wider" style={{ color: "var(--grey)" }}>
              {doneCount} of {total} complete
            </span>
            <span className="font-mono text-xs tabular-nums" style={{ color: "var(--paper)" }}>
              {pct}%
            </span>
          </div>
          <div
            className="mt-1.5 h-1 w-full overflow-hidden"
            style={{ background: "color-mix(in srgb, var(--grey) 24%, transparent)" }}
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

      {/* Timeline — numbered subsystems, each reveals once, reports as it lands */}
      <ol className="relative z-10 flex-1 space-y-0">
        {steps.map((s, i) => {
          const last = i === steps.length - 1;
          const isDone = s.state === "done";
          const isRunning = s.state === "running";
          const isFailed = s.state === "failed";
          const num = String(i + 1).padStart(2, "0");

          return (
            <motion.li
              key={s.key}
              className="flex gap-4"
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={reduce ? { duration: 0 } : { duration: 0.5, delay: i * 0.2, ease: EASE.inOut }}
            >
              {/* Marker + connecting line */}
              <div className="flex flex-col items-center">
                <div
                  className="flex size-6 shrink-0 items-center justify-center rounded-full"
                  style={{
                    background: isDone
                      ? "var(--green2)"
                      : isFailed
                      ? "var(--red)"
                      : "transparent",
                    border: isDone || isFailed
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
                    <WarningTriangle className="size-3.5" style={{ color: "var(--white)" }} strokeWidth={2} />
                  )}
                  {isRunning && (
                    // Running marker — finite pulse-in, settles at once. No infinite
                    // loop: liveness is carried by the real progress bar advancing as
                    // artifacts land (P3 / CCA-F P1).
                    <motion.span
                      className="size-2.5 rounded-full"
                      style={{ background: "var(--green2)" }}
                      initial={reduce ? false : { scale: 0.4, opacity: 0.5 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={reduce ? { duration: 0 } : { duration: 0.45, ease: EASE.out }}
                    />
                  )}
                  {s.state === "queued" && (
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
                    className="w-px"
                    style={{
                      flex: "1",
                      minHeight: "40px",
                      background: isDone
                        ? "var(--green2)"
                        : "color-mix(in srgb, var(--grey) 24%, transparent)",
                    }}
                  />
                )}
              </div>

              {/* Step text — mono status line + plain detail + provenance pill */}
              <div className={last ? "min-w-0 flex-1 pb-2" : "min-w-0 flex-1 pb-7"}>
                <div className="flex items-center gap-2">
                  <span
                    className="font-mono text-[11px] font-semibold uppercase tracking-wider"
                    style={{
                      color: isDone || isRunning
                        ? "var(--paper)"
                        : isFailed
                        ? "var(--red)"
                        : "color-mix(in srgb, var(--grey) 50%, transparent)",
                    }}
                  >
                    {num} · {s.label}
                  </span>
                  <ProvenanceBadge tier={s.tier} compact />
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
                  {isFailed
                    ? "Failed"
                    : isDone
                    ? "Complete"
                    : isRunning
                    ? "Running…"
                    : `Waiting on ${s.waitingOn}`}
                </p>

                {isDone && s.fact && (
                  <p className="mt-1 font-mono text-xs" style={{ color: "var(--paper)" }}>
                    {s.fact}
                  </p>
                )}
                {isRunning && (
                  <p className="mt-1 font-mono text-[11px]" style={{ color: "var(--grey)" }}>
                    {s.detail}
                  </p>
                )}
              </div>
            </motion.li>
          );
        })}
      </ol>

      {/* CTA — state-driven, no spinner that hides a result that never came */}
      <div className="relative z-10 mt-auto pt-4" style={{ borderTop: "1px solid var(--border)" }}>
        {!allDone && !failed && (
          <p className="mb-2.5 font-mono text-[11px] leading-relaxed" style={{ color: "var(--grey)" }}>
            Once all zones are ranked, you'll accept the shade spots you want.
          </p>
        )}
        {failed && (
          <p className="mb-2.5 font-mono text-[11px] leading-relaxed" style={{ color: "var(--red)" }}>
            A step failed — no fake spin. Check the backend at :8000, then re-run.
          </p>
        )}
        <button
          type="button"
          disabled={!allDone}
          onClick={onContinue}
          className="flex h-11 w-full items-center justify-center gap-2 font-sans font-bold tracking-wide transition-opacity hover:opacity-90 disabled:opacity-40"
          style={{
            background: failed ? "var(--red)" : "var(--green2)",
            color: failed ? "var(--white)" : "var(--ink)",
            borderRadius: "var(--radius-sm)",
            letterSpacing: "0.04em",
            fontSize: "0.875rem",
          }}
        >
          {allDone ? (
            <>
              Review shade placements
              <ArrowRight className="size-4" strokeWidth={2} />
            </>
          ) : (
            `Working — ${doneCount} of ${total} subsystems landed`
          )}
        </button>
      </div>
    </div>
  );
}

/**
 * The graticule — a faint instrument grid that ignites once on entry, then holds.
 * IAAC pixel-block motif: a few scattered squares warm to the accent (red on fault).
 * Pure decoration of a REAL event (the run starting); settles, never loops.
 */
function Graticule({ reduce, failed }: { reduce: boolean; failed: boolean }) {
  const accent = failed ? "var(--red)" : "var(--green2)";
  const cells = [
    { x: "14%", y: "20%", d: 0.1 },
    { x: "80%", y: "16%", d: 0.28 },
    { x: "70%", y: "44%", d: 0.42 },
    { x: "24%", y: "66%", d: 0.55 },
    { x: "86%", y: "72%", d: 0.34 },
    { x: "46%", y: "84%", d: 0.5 },
  ];
  return (
    <div className="pointer-events-none absolute inset-0 z-0" aria-hidden="true">
      <motion.div
        className="absolute inset-0"
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={reduce ? { duration: 0 } : { duration: 1.1, ease: EASE.out }}
        style={{
          backgroundImage:
            "linear-gradient(color-mix(in srgb, var(--grey) 13%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--grey) 13%, transparent) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage: "radial-gradient(ellipse at 50% 36%, black 28%, transparent 80%)",
          WebkitMaskImage: "radial-gradient(ellipse at 50% 36%, black 28%, transparent 80%)",
        }}
      />
      {cells.map((c, i) => (
        <motion.span
          key={i}
          className="absolute size-2"
          style={{ left: c.x, top: c.y, background: accent }}
          initial={reduce ? false : { opacity: 0, scale: 0.6 }}
          animate={{ opacity: 0.2, scale: 1 }}
          transition={reduce ? { duration: 0 } : { duration: 0.5, delay: 0.6 + c.d, ease: EASE.out }}
        />
      ))}
    </div>
  );
}
