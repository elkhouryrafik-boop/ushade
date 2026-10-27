import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MusicNote,
  LogIn,
  Cutlery,
  HealthShield,
  Droplet,
  Tools,
  NavArrowDown,
  Trash,
  Check,
} from "iconoir-react";
import { useHeatGuard, type ShapeKind } from "@/lib/heatguard-store";
import { useRunPipeline } from "@/lib/useRunPipeline";
import { StageScaffold } from "../StageScaffold";
import { ProvenanceBadge } from "../ProvenanceBadge";
import { EASE } from "@/lib/motion";

/**
 * S5 — Place your stages & amenities.
 * Pick a tool from the two-tier palette, then click the map to drop a pin.
 * Spec S5: arranging a real site, not filling a form — palette → place-tool →
 * live count → pin inspector. Big-number live count is the hero datum (P2).
 * Stages/gates/hours are GROUNDED — this layout is exactly what the crowd sim runs on.
 *
 * Store contract (unchanged): addShape / removeShape / updateShape / setStage,
 * ShapeKind unchanged, StageScaffold reused.
 */

interface PaletteItem {
  kind: ShapeKind;
  label: string;
  short: string;
  icon: React.ElementType;
  group: "essentials" | "more";
}

const PALETTE: PaletteItem[] = [
  { kind: "stage",    label: "Stage",        short: "stages",    icon: MusicNote,    group: "essentials" },
  { kind: "entrance", label: "Gate",         short: "gates",     icon: LogIn,        group: "essentials" },
  { kind: "food",     label: "Food & bar",   short: "F&B",       icon: Cutlery,      group: "essentials" },
  { kind: "medical",  label: "Medical",      short: "medical",   icon: HealthShield, group: "essentials" },
  { kind: "restroom", label: "Water point",  short: "water",     icon: Droplet,      group: "more" },
  { kind: "service",  label: "Services",     short: "services",  icon: Tools,        group: "more" },
];

const KIND_LABELS: Record<ShapeKind, string> = {
  boundary: "Boundary",
  stage:    "Stage",
  entrance: "Gate",
  restroom: "Water point",
  food:     "Food & bar",
  medical:  "Medical",
  service:  "Services",
};

/** Which kinds carry the safety case (clearance matters, GROUNDED for the sim). */
const SAFETY_KINDS = new Set<ShapeKind>(["medical", "entrance"]);

export function LayoutScreen() {
  const { state, dispatch } = useHeatGuard();
  // Shared with the map's draw control (store) so picking a tool here arms the map:
  // click the map → DrawControl drops a point of this kind → addShape.
  const activeTool = state.layoutTool;
  const setActiveTool = (t: ShapeKind | null) => dispatch({ type: "setLayoutTool", tool: t });
  const { runCustomSite } = useRunPipeline();
  const [showMore, setShowMore] = useState(false);
  const [inspecting, setInspecting] = useState<string | null>(null);

  const placed = state.project.shapes.filter((s) => s.kind !== "boundary");
  const counts = PALETTE.reduce<Record<string, number>>((acc, p) => {
    acc[p.kind] = placed.filter((s) => s.kind === p.kind).length;
    return acc;
  }, {});

  const inspectedShape = placed.find((s) => s.id === inspecting);

  const essentials = PALETTE.filter((p) => p.group === "essentials");
  const extras = PALETTE.filter((p) => p.group === "more");

  // Hero datum — the headline figure read across a room (P2). Stages lead;
  // everything else is quiet support.
  const stageCount = counts["stage"] ?? 0;
  const summaryParts = PALETTE.filter((p) => p.kind !== "stage" && counts[p.kind] > 0).map(
    (p) => `${counts[p.kind]} ${p.short}`,
  );

  return (
    <StageScaffold
      index="03 / LAYOUT"
      title="Place your stages & amenities"
      lede="The layout is the crowd sim's skeleton. Stages pull people; gates feed them in; water, medical and exits are the safety case the plan defends."
      cta={{
        label: placed.length > 0 ? "Run heat × crowd →" : "Place at least one element",
        onClick: () => runCustomSite(),
        disabled: placed.length === 0,
        disabledReason: placed.length === 0 ? "Drop a stage or gate to begin." : undefined,
      }}
    >
      <div className="space-y-6">
        {/* ── Hero live count ─────────────────────────────────────────── */}
        <section>
          <div className="flex items-baseline justify-between">
            <p className="text-label" style={{ color: "var(--grey)" }}>
              ON THE SITE
            </p>
            <AnimatePresence>
              {placed.length > 0 && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2, ease: EASE.outFast }}
                  className="flex items-center gap-1 font-mono text-[11px]"
                  style={{ color: "var(--green)" }}
                >
                  <Check className="size-3" strokeWidth={2.5} />
                  Saved on continue
                </motion.span>
              )}
            </AnimatePresence>
          </div>

          <div className="mt-1 flex items-end gap-3">
            <motion.span
              key={stageCount}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: EASE.out }}
              className="text-display tabular-nums"
              style={{ color: "var(--text-primary)", lineHeight: 0.9 }}
            >
              {stageCount}
            </motion.span>
            <span
              className="pb-1 font-sans text-lg font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              {stageCount === 1 ? "stage" : "stages"}
            </span>
          </div>

          {/* Live count strip — an instrument readout, one figure per category (s5-save). */}
          <div
            className="mt-3 flex flex-wrap items-baseline gap-x-5 gap-y-1.5"
            style={{ minHeight: "1.4rem" }}
          >
            {summaryParts.length > 0 ? (
              PALETTE.filter((p) => p.kind !== "stage" && counts[p.kind] > 0).map((p) => (
                <span key={p.kind} className="flex items-baseline gap-1.5">
                  <span
                    className="font-mono text-sm tabular-nums"
                    style={{ color: "var(--green)" }}
                  >
                    {String(counts[p.kind]).padStart(2, "0")}
                  </span>
                  <span
                    className="font-mono text-[11px] uppercase tracking-wider"
                    style={{ color: "var(--grey)" }}
                  >
                    {p.short}
                  </span>
                </span>
              ))
            ) : (
              <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                no amenities yet
              </span>
            )}
          </div>

          <div
            className="mt-3 flex items-center gap-2 pt-2"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            <ProvenanceBadge tier="GROUNDED" source="Your placed layout — exactly what the crowd sim runs on" />
            <span
              className="font-mono text-[11px] uppercase tracking-wider"
              style={{ color: "var(--grey)" }}
            >
              The skeleton the crowd sim runs on
            </span>
          </div>
        </section>

        {/* ── Palette dock ────────────────────────────────────────────── */}
        <section>
          <p className="text-label mb-2 font-mono" style={{ color: "var(--grey)" }}>
            PALETTE · PICK A TOOL, CLICK THE MAP
          </p>

          <div
            style={{
              borderTop: "1px solid var(--border)",
              borderRight: "1px solid var(--border)",
              borderBottom: "1px solid var(--border)",
              borderLeft: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <div className="divide-y" style={{ borderColor: "var(--border)" }}>
              {essentials.map((item) => (
                <PaletteRow
                  key={item.kind}
                  item={item}
                  active={activeTool === item.kind}
                  count={counts[item.kind] ?? 0}
                  onClick={() => setActiveTool(activeTool === item.kind ? null : item.kind)}
                />
              ))}
            </div>

            {/* More tray */}
            {extras.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={() => setShowMore((v) => !v)}
                  className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-muted/40"
                  style={{ borderTop: "1px solid var(--border)" }}
                >
                  <span className="text-label" style={{ color: "var(--grey)" }}>
                    {showMore ? "Fewer amenities" : "More amenities"}
                  </span>
                  <NavArrowDown
                    className="size-3 transition-transform"
                    style={{
                      color: "var(--grey)",
                      transform: showMore ? "rotate(180deg)" : "none",
                    }}
                    strokeWidth={2}
                  />
                </button>
                <AnimatePresence initial={false}>
                  {showMore && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.25, ease: EASE.inOut }}
                      className="divide-y overflow-hidden"
                      style={{ borderColor: "var(--border)", borderTop: "1px solid var(--border)" }}
                    >
                      {extras.map((item) => (
                        <PaletteRow
                          key={item.kind}
                          item={item}
                          active={activeTool === item.kind}
                          count={counts[item.kind] ?? 0}
                          onClick={() =>
                            setActiveTool(activeTool === item.kind ? null : item.kind)
                          }
                        />
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </>
            )}
          </div>

          <AnimatePresence>
            {activeTool && (
              <motion.p
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.2, ease: EASE.outFast }}
                className="mt-2 font-mono text-[11px] uppercase tracking-wider"
                style={{ color: "var(--teal)" }}
              >
                {KIND_LABELS[activeTool]} tool active — click the map to place
              </motion.p>
            )}
          </AnimatePresence>
        </section>

        {/* ── Placed list ─────────────────────────────────────────────── */}
        {placed.length > 0 ? (
          <section className="space-y-2">
            <p className="text-label" style={{ color: "var(--grey)" }}>
              PLACED · {placed.length}
            </p>
            <div className="space-y-1">
              {placed.map((shape) => {
                const open = shape.id === inspecting;
                return (
                  <div key={shape.id}>
                    <button
                      type="button"
                      onClick={() => setInspecting(open ? null : shape.id)}
                      className="flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-muted/40"
                      style={{
                        borderTop: "1px solid var(--border)",
                        borderRight: "1px solid var(--border)",
                        borderBottom: "1px solid var(--border)",
                        borderLeft: open
                          ? "2px solid var(--teal)"
                          : "1px solid var(--border)",
                        borderRadius: "var(--radius-sm)",
                        background: open ? "var(--surface)" : "transparent",
                      }}
                    >
                      <span
                        className="size-2 shrink-0 rounded-full"
                        style={{
                          background: SAFETY_KINDS.has(shape.kind) ? "var(--red)" : "var(--teal)",
                        }}
                      />
                      <span
                        className="flex-1 truncate font-sans text-sm"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {shape.label ?? KIND_LABELS[shape.kind]}
                      </span>
                      <span className="font-mono text-[11px] uppercase" style={{ color: "var(--grey)" }}>
                        {KIND_LABELS[shape.kind]}
                      </span>
                    </button>

                    {/* Inspector springs from the object */}
                    <AnimatePresence>
                      {open && (
                        <motion.div
                          initial={{ opacity: 0, scale: 0.98 }}
                          animate={{ opacity: 1, scale: 1 }}
                          exit={{ opacity: 0, scale: 0.98 }}
                          transition={{ duration: 0.2, ease: EASE.outFast }}
                          className="mt-1 space-y-3 p-3"
                          style={{
                            borderTop: "1px solid var(--teal)",
                            borderRight: "1px solid var(--teal)",
                            borderBottom: "1px solid var(--teal)",
                            borderLeft: "2px solid var(--teal)",
                            borderRadius: "var(--radius-sm)",
                            background: "var(--surface)",
                          }}
                        >
                          <p className="text-label" style={{ color: "var(--teal)" }}>
                            INSPECTOR
                          </p>
                          <div>
                            <label
                              className="text-label mb-1 block"
                              style={{ color: "var(--grey)" }}
                            >
                              NAME
                            </label>
                            <input
                              type="text"
                              className="w-full px-3 py-2 font-sans text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                              style={{
                                border: "1px solid var(--border)",
                                borderRadius: "var(--radius-sm)",
                                background: "var(--surface)",
                                color: "var(--text-primary)",
                              }}
                              defaultValue={shape.label ?? KIND_LABELS[shape.kind]}
                              onBlur={(e) =>
                                dispatch({
                                  type: "updateShape",
                                  shape: { ...shape, label: e.target.value },
                                })
                              }
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              dispatch({ type: "removeShape", id: shape.id });
                              setInspecting(null);
                            }}
                            className="flex items-center gap-1.5 font-sans text-sm font-medium transition-opacity hover:opacity-80"
                            style={{ color: "var(--red)" }}
                          >
                            <Trash className="size-3.5" strokeWidth={1.5} />
                            Delete
                          </button>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })}
            </div>
          </section>
        ) : (
          <p className="font-sans text-sm" style={{ color: "var(--text-muted)" }}>
            Pick a tool above, then click the map to drop your first pin. Start from scratch,
            or load the Parc del F&ograve;rum ground-truth as a reference outline.
          </p>
        )}
      </div>
    </StageScaffold>
  );
}

/** One dock row — icon + label + live count, inverts to ink when active. */
function PaletteRow({
  item,
  active,
  count,
  onClick,
}: {
  item: PaletteItem;
  active: boolean;
  count: number;
  onClick: () => void;
}) {
  const Icon = item.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-3 py-3 pr-3 text-left transition-colors hover:bg-muted/30"
      style={{
        background: active ? "var(--ink)" : "transparent",
        color: active ? "var(--white)" : "var(--text-primary)",
        // Instrument accent bar — deliberate left edge when armed (no double-border).
        paddingLeft: active ? "10px" : "12px",
        borderLeft: active ? "2px solid var(--teal)" : "2px solid transparent",
      }}
    >
      <Icon
        className="size-5 shrink-0"
        strokeWidth={1.5}
        style={{ color: active ? "var(--paper)" : "var(--grey)" }}
      />
      <span className="font-sans text-sm font-medium">{item.label}</span>
      {active ? (
        <span
          className="ml-auto font-mono text-[10px] uppercase tracking-wider"
          style={{ color: "var(--paper)" }}
        >
          armed
        </span>
      ) : (
        count > 0 && (
          <span
            className="ml-auto font-mono text-xs tabular-nums"
            style={{ color: "var(--green)" }}
          >
            {String(count).padStart(2, "0")}
          </span>
        )
      )}
    </button>
  );
}
