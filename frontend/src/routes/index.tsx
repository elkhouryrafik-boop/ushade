import { createFileRoute } from "@tanstack/react-router";
import { WizardApp } from "@/components/wizard/WizardShell";

// Unified HeatGuard organiser app (UI-SPEC): Site → Materials → Placement → Handoff
// on one persistent Mapbox canvas. Replaces the old 5-view console (HeatGuardApp);
// the old views remain in the tree but are no longer routed.
export const Route = createFileRoute("/")({
  component: WizardApp,
});
