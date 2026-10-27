import { useHeatGuard, WIZARD_STAGES, type WizardStage } from "@/lib/heatguard-store";
import {
  EditPencil,
  LayoutLeft,
  MapPin,
  Packages,
  GridMinus,
  FrameSelect,
  Settings,
  Lock,
  Check,
} from "iconoir-react";
import { cn } from "@/lib/utils";
import { PixelMark } from "./PixelMark";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const STAGE_META: Record<WizardStage, { label: string; index: string; icon: React.ElementType }> = {
  brief:     { label: "Brief",     index: "01", icon: EditPencil },
  site:      { label: "Site",      index: "02", icon: MapPin },
  layout:    { label: "Layout",    index: "03", icon: LayoutLeft },
  placement: { label: "Shade",     index: "04", icon: GridMinus },
  materials: { label: "Materials", index: "05", icon: Packages },
  handoff:   { label: "The Plan",  index: "06", icon: FrameSelect },
};

function gateFor(
  stage: WizardStage,
  s: ReturnType<typeof useHeatGuard>["state"],
): { locked: false } | { locked: true; reason: string } {
  if (s.navMode === "hub") return { locked: false };
  const hasBoundary = s.project.siteAreaM2 > 0;
  const runStarted = s.simRunId !== null;
  switch (stage) {
    case "brief":
      return { locked: false };
    case "site":
      return { locked: false };
    case "layout":
      return hasBoundary
        ? { locked: false }
        : { locked: true, reason: "Draw a valid site boundary first." };
    case "placement":
      return runStarted
        ? { locked: false }
        : { locked: true, reason: "Place the layout, then run." };
    case "materials":
      return s.acceptedRanks.length > 0
        ? { locked: false }
        : { locked: true, reason: "Accept a shade zone first — we clad what you keep." };
    case "handoff":
      return s.acceptedRanks.length > 0
        ? { locked: false }
        : { locked: true, reason: "Accept at least one placement first." };
  }
}

const idx = (st: WizardStage) => WIZARD_STAGES.indexOf(st);

export function WizardRail() {
  const { state, dispatch } = useHeatGuard();
  const current = state.stage;

  return (
    <TooltipProvider delayDuration={150}>
      <nav
        aria-label="Workflow stages"
        className="flex h-full w-16 shrink-0 flex-col"
        style={{
          background: "var(--ink)",
          borderRight: "1px solid color-mix(in srgb, var(--paper) 15%, transparent)",
        }}
      >
        {/* U-Shade wordmark + IAAC pixel-block motif */}
        <div className="flex h-14 flex-col items-center justify-center gap-1.5 border-b"
          style={{ borderColor: "color-mix(in srgb, var(--paper) 12%, transparent)" }}>
          <span
            className="font-display text-[10px] font-bold tracking-widest uppercase"
            style={{ color: "var(--paper)", letterSpacing: "0.12em" }}
          >
            U-S
          </span>
          <PixelMark tone="paper" cell={3} gap={1.5} />
        </div>

        {/* Stage items */}
        <ol className="flex flex-1 flex-col items-center gap-1 py-2">
          {WIZARD_STAGES.map((stage, i) => {
            const meta = STAGE_META[stage];
            const Icon = meta.icon;
            const gate = gateFor(stage, state);
            const isActive = stage === current;
            const isComplete = idx(current) > i && !gate.locked;
            const locked = gate.locked;

            return (
              <li key={stage} className="w-full">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      disabled={locked}
                      aria-current={isActive ? "step" : undefined}
                      onClick={() => !locked && dispatch({ type: "setStage", stage })}
                      className={cn(
                        "relative flex w-full flex-col items-center gap-0.5 py-2.5 transition-colors",
                        "focus-visible:outline-none",
                        locked && "cursor-not-allowed opacity-40",
                        !locked && !isActive && "hover:bg-white/5",
                      )}
                      style={
                        isActive
                          ? { borderLeft: "2px solid var(--green)" }
                          : { borderLeft: "2px solid transparent" }
                      }
                    >
                      {isComplete ? (
                        <Check
                          className="size-5"
                          style={{ color: "var(--green)" }}
                          strokeWidth={1.5}
                        />
                      ) : locked ? (
                        <Lock
                          className="size-5"
                          style={{ color: "var(--grey)" }}
                          strokeWidth={1.5}
                        />
                      ) : (
                        <Icon
                          className="size-5"
                          style={{ color: isActive ? "var(--paper)" : "var(--grey)" }}
                          strokeWidth={1.5}
                        />
                      )}
                      <span
                        className="font-mono text-[9px] font-semibold"
                        style={{ color: isActive ? "var(--grey)" : "color-mix(in srgb, var(--grey) 50%, transparent)" }}
                      >
                        {meta.index}
                      </span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right" className="text-label">
                    {locked ? gate.reason : meta.label}
                  </TooltipContent>
                </Tooltip>
              </li>
            );
          })}
        </ol>

        {/* IAAC pixel motif — quiet bitmap accent above the footer divider. */}
        <div className="flex items-center justify-center pb-2 opacity-60">
          <PixelMark tone="paper" cell={2.5} gap={1.5} />
        </div>

        {/* Settings */}
        <div className="flex items-center justify-center border-t py-3"
          style={{ borderColor: "color-mix(in srgb, var(--paper) 12%, transparent)" }}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="rounded p-1.5 transition-colors hover:bg-white/8"
                aria-label="Settings"
              >
                <Settings
                  className="size-4"
                  style={{ color: "var(--grey)" }}
                  strokeWidth={1.5}
                />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right" className="text-label">Settings</TooltipContent>
          </Tooltip>
        </div>
      </nav>
    </TooltipProvider>
  );
}
