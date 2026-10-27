import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Xmark } from "iconoir-react";
import { useHeatGuard } from "@/lib/heatguard-store";
import { EASE } from "@/lib/motion";

/**
 * S3 — Parc del Fòrum Primer banner.
 * Absolute top-right chip on the map column.
 * On click: loads Primavera demo project and steps through analysis.
 */

export function PrimerBanner() {
  const { dispatch } = useHeatGuard();
  const [dismissed, setDismissed] = useState(false);
  const [running, setRunning] = useState(false);

  function startPrimer() {
    setRunning(true);
    // Load the demo project and kick off the run
    dispatch({
      type: "setProject",
      patch: {
        capacity: 70000,
        budget: 80000,
        date: "2025-06-01",
        theme: "Sun-bleached natural canopy, reclaimed timber and woven jute, organic flowing forms inspired by Mediterranean dunes",
        siteAreaM2: 197000,
      },
    });
    dispatch({ type: "startRun", runId: "primavera-demo" });
    dispatch({ type: "setStage", stage: "placement" });
  }

  return (
    <AnimatePresence>
      {!dismissed && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.3, ease: EASE.outFast }}
          className="absolute right-4 top-4 z-30 flex items-center gap-0"
          style={{
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            background: "var(--surface)",
            height: "36px",
          }}
        >
          <button
            type="button"
            onClick={startPrimer}
            disabled={running}
            className="flex items-center gap-1.5 px-3 h-full font-mono text-[11px] font-semibold uppercase tracking-wider transition-colors hover:bg-muted/40"
            style={{ color: running ? "var(--grey)" : "var(--text-primary)" }}
          >
            {running ? "Loading…" : "Try Parc del Fòrum →"}
            {!running && <ArrowRight className="size-3.5" strokeWidth={2} />}
          </button>
          <div style={{ width: "1px", height: "20px", background: "var(--border)" }} />
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="flex items-center justify-center px-2 h-full transition-colors hover:bg-muted/40"
            aria-label="Dismiss"
          >
            <Xmark className="size-3.5" style={{ color: "var(--grey)" }} strokeWidth={2} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
