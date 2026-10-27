/**
 * Save / resume (UI-SPEC §3.1 "Save & resume" + §3.2 returning-user hub).
 * Persists the meaningful slice of the project to localStorage so a reload (or a
 * returning visit) re-enters where the organiser left off — drawn boundary,
 * accepted placements, material holds, current stage. Transient UI (hoveredZone,
 * analyzing) is NOT persisted. SSR-guarded (TanStack Start renders on the server).
 */
import type { WizardStage } from "./heatguard-store";

const KEY = "ushade.project.v1";

export interface PersistedProject {
  project: unknown; // the Project slice (shapes, siteAreaM2, capacity/budget/date/theme)
  stage: WizardStage;
  simRunId: string | null;
  acceptedRanks: number[];
  materialHolds: Record<string, { expiresAt: number; holdId: string }>;
  materialPlan: string[];
  savedAt: number;
}

export function loadPersisted(): PersistedProject | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as PersistedProject;
    // Drop expired material holds on load (a hold past its TTL is auto-released).
    const now = Date.now();
    p.materialHolds = Object.fromEntries(
      Object.entries(p.materialHolds ?? {}).filter(([, h]) => h.expiresAt > now),
    );
    return p;
  } catch {
    return null;
  }
}

export function savePersisted(p: Omit<PersistedProject, "savedAt">): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ ...p, savedAt: Date.now() }));
  } catch {
    /* quota / private mode — non-fatal, save is best-effort */
  }
}

export function clearPersisted(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* non-fatal */
  }
}

export function hasSavedProject(): boolean {
  const p = loadPersisted();
  // A meaningful save = a boundary was drawn (siteAreaM2 > 0).
  return !!p && !!(p.project as { siteAreaM2?: number })?.siteAreaM2;
}
