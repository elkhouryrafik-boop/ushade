import { useHeatGuard, type WizardStage } from "@/lib/heatguard-store";
import { Button } from "@/components/ui/button";
import { MapPin, LayoutGrid, Boxes, CheckCircle2, Plus, ArrowRight } from "lucide-react";

/**
 * ProjectDashboard (UI-SPEC §3.2) — the returning-user hub. Shown on load when a
 * saved project exists; surfaces the saved site + its status and lets the organiser
 * resume where they left off or start a new site. Single-site (Fòrum) for now, so
 * it's one project card — the layout scales to a list when multi-site lands.
 */

const STAGE_LABEL: Record<WizardStage, string> = {
  brief: "Describing the festival",
  site: "Boundary drawn",
  layout: "Generating layout",
  placement: "Reviewing shade spots",
  materials: "Choosing materials",
  handoff: "Ready for architect handoff",
};

export function ProjectDashboard({
  onResume,
  onNew,
}: {
  onResume: () => void;
  onNew: () => void;
}) {
  const { state } = useHeatGuard();
  const { project, stage, acceptedRanks, materialHolds } = state;
  const holds = Object.keys(materialHolds).length;
  const ha = (project.siteAreaM2 / 10000).toFixed(2);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6 py-12">
      <div className="w-full max-w-lg">
        <div className="font-display text-3xl text-text-primary">U-Shade</div>
        <p className="mt-1 text-[15px] text-text-muted">Welcome back. Pick up where you left off.</p>

        {/* Saved project card */}
        <div className="mt-6 overflow-hidden rounded-xl border border-border bg-surface e2">
          <div className="flex items-center gap-2 border-b border-border px-5 py-4">
            <MapPin className="size-4 shrink-0 text-data-cool" />
            <span className="font-medium text-text-primary">Parc del Fòrum, Barcelona</span>
            <span className="ml-auto rounded-full bg-success/12 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-success">
              {STAGE_LABEL[stage]}
            </span>
          </div>

          <div className="grid grid-cols-3 divide-x divide-border">
            <Stat icon={MapPin} label="Site area" value={`${ha} ha`} />
            <Stat icon={Boxes} label="Holds" value={String(holds)} />
            <Stat icon={CheckCircle2} label="Accepted" value={String(acceptedRanks.length)} />
          </div>

          <div className="border-t border-border px-5 py-4">
            <Button
              className="h-11 w-full bg-primary text-primary-foreground hover:bg-primary-hover"
              onClick={onResume}
            >
              <LayoutGrid className="size-4" /> Resume this site
              <ArrowRight className="size-4" />
            </Button>
          </div>
        </div>

        <button
          type="button"
          onClick={onNew}
          className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-md border border-border bg-surface px-4 py-3 text-[13px] text-text-muted hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Plus className="size-4" /> Start a new site
        </button>

        <p className="mt-6 text-center font-mono text-[10px] leading-relaxed text-text-muted">
          Your work is saved on this device. Decision-support tool — not engineering authority.
        </p>
      </div>
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof MapPin;
  label: string;
  value: string;
}) {
  return (
    <div className="px-4 py-3 text-center">
      <Icon className="mx-auto size-4 text-text-muted" />
      <div className="mt-1 font-mono text-lg font-medium tabular-nums text-text-primary">{value}</div>
      <div className="font-mono text-[9px] uppercase tracking-wider text-text-muted">{label}</div>
    </div>
  );
}
