import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { ArrowRight, Plus, OpenBook, Globe } from "iconoir-react";
import { EASE, DUR } from "@/lib/motion";
import { PixelMark } from "../PixelMark";

/**
 * S1 — Welcome & Project Hub.
 * Full-viewport editorial overlay, IAAC Barcelona house style: giant FK Grotesk
 * hero, tiny mono labels, ruled dividers, the scattered pixel-block motif, and a
 * dithered orange/green data-image on the right. Two doors (Create / Try Parc del
 * Fòrum demo) read as editorial ruled rows, not SaaS cards. Choosing a door eases
 * into the map with a directional threshold wipe — never a hard cut. Everything
 * settles; nothing loops.
 */

interface SavedProject {
  name: string;
  site: string;
  status: string;
  lastEdited: string;
}

interface WelcomeScreenProps {
  onNew: () => void;
  onResume: (project?: SavedProject) => void;
  onBeyond?: () => void;
  savedProjects?: SavedProject[];
}

export function WelcomeScreen({ onNew, onResume, onBeyond, savedProjects = [] }: WelcomeScreenProps) {
  const reduce = useReducedMotion();
  const [leaving, setLeaving] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  // Re-entry guard (synchronous — `leaving` state lags within a tick) + timeout
  // handle so the deferred navigation is cancelled if we unmount first.
  const chosenRef = useRef(false);
  const leaveTimer = useRef<ReturnType<typeof setTimeout>>();

  // Restrained parallax for the dithered image. Skipped under reduced-motion;
  // bounded + spring-eased so it always settles and never runs a CPU loop.
  useEffect(() => {
    if (reduce) return;
    let raf = 0;
    function onMove(e: MouseEvent) {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const x = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
        const y = ((e.clientY - rect.top) / rect.height - 0.5) * 2;
        setMousePos({ x, y });
      });
    }
    window.addEventListener("mousemove", onMove);
    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf);
    };
  }, [reduce]);

  // Cancel a pending leave-navigation if the component unmounts mid-transition.
  useEffect(() => () => clearTimeout(leaveTimer.current), []);

  function choose(door: "new" | "demo", project?: SavedProject) {
    if (chosenRef.current) return; // ignore double-invoke (door + saved-project rows)
    chosenRef.current = true;
    setLeaving(true);
    leaveTimer.current = setTimeout(() => {
      if (door === "new") onNew();
      else onResume(project);
    }, reduce ? 0 : DUR.stage);
  }

  // Staggered entrance helper.
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
          ref={containerRef}
          className="fixed inset-0 z-50 flex overflow-hidden"
          style={{ background: "var(--white)" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduce ? { opacity: 0 } : { clipPath: "inset(0 0 100% 0)", opacity: 0.4 }}
          transition={{ duration: DUR.stage / 1000, ease: EASE.inOut }}
        >
          {/* ─── LEFT — the editorial page ─────────────────────────────────── */}
          <div className="relative flex w-[56%] flex-col px-16 py-10">
            {/* Masthead — ruled bar, pixel-block mark, mono metadata */}
            <motion.header {...rise(0.04)} className="shrink-0">
              <div className="flex items-end justify-between">
                <div className="flex items-center gap-3">
                  <PixelMark cell={5} gap={2} />
                  <span className="text-label" style={{ color: "var(--ink)" }}>
                    U-SHADE
                  </span>
                </div>
                <span className="text-label" style={{ color: "var(--grey)" }}>
                  IAAC BARCELONA · SERVICE AS SOFTWARE
                </span>
              </div>
              <div className="mt-3 h-px w-full" style={{ background: "var(--ink)" }} />
              <div className="mt-2 flex items-center justify-between">
                <span className="font-mono text-[10px] tracking-widest" style={{ color: "var(--grey)" }}>
                  CLIMATE-AWARE FESTIVAL SHADE
                </span>
                <span className="font-mono text-[10px] tracking-widest" style={{ color: "var(--grey)" }}>
                  EST. BARCELONA
                </span>
              </div>
            </motion.header>

            {/* Hero — dramatic scale: giant display wordmark + Clarendon lede */}
            <div className="flex flex-1 flex-col justify-center py-8">
              <motion.div {...rise(0.10)} className="mb-5 flex items-center gap-3">
                <span className="text-label" style={{ color: "var(--green)" }}>
                  ↳ DECISION-SUPPORT INSTRUMENT
                </span>
              </motion.div>

              <motion.h1
                {...rise(0.14)}
                style={{
                  fontFamily: "var(--font-display)",
                  fontWeight: 700,
                  fontSize: "clamp(3.5rem, 9vw, 7rem)",
                  lineHeight: 0.92,
                  letterSpacing: "-0.04em",
                  color: "var(--ink)",
                }}
              >
                U-Shade
              </motion.h1>

              <motion.p
                {...rise(0.20)}
                className="text-editorial mt-6"
                style={{ color: "var(--ink)", maxWidth: "30ch" }}
              >
                Cross a real heat grid with a real crowd field — then place shade
                exactly where it protects the most people.
              </motion.p>

              {/* Ruled divider with pixel accent */}
              <motion.div {...rise(0.26)} className="mt-8 flex items-center gap-4">
                <div className="h-px flex-1" style={{ background: "var(--border)" }} />
                <PixelMark cell={4} gap={2} />
                <span className="text-label" style={{ color: "var(--grey)" }}>
                  WAYS IN
                </span>
              </motion.div>
            </div>

            {/* Doors — editorial ruled rows, indexed, not cards */}
            <div className="shrink-0">
              <DoorRow
                index="01"
                rise={rise(0.30)}
                title="Create your festival"
                sub="Describe it, or draw any site boundary"
                accent="var(--green)"
                primary
                icon={<Plus className="size-6" strokeWidth={1.5} style={{ color: "var(--green)" }} />}
                onClick={() => choose("new")}
                reduce={!!reduce}
              />
              <DoorRow
                index="02"
                rise={rise(0.36)}
                title="Try Parc del Fòrum"
                sub="Live Primavera Sound data — the whole product in 60 seconds"
                accent="var(--ink)"
                badge="DEMO"
                icon={<ArrowRight className="size-6" strokeWidth={1.5} style={{ color: "var(--ink)" }} />}
                onClick={() => choose("demo")}
                reduce={!!reduce}
              />
              {onBeyond && (
                <DoorRow
                  index="03"
                  rise={rise(0.42)}
                  title="Beyond Festivals"
                  sub="Parks · playgrounds · plazas · beaches — the same engine, any site"
                  accent="var(--teal)"
                  badge="CONCEPT"
                  icon={<Globe className="size-6" strokeWidth={1.5} style={{ color: "var(--teal)" }} />}
                  onClick={onBeyond}
                  reduce={!!reduce}
                />
              )}

              {/* Saved projects — list-item rows per s1-projectcard ref */}
              {savedProjects.length > 0 && (
                <motion.div {...rise(0.42)} className="mt-5">
                  <div className="mb-2 flex items-center gap-2">
                    <OpenBook className="size-3.5" strokeWidth={1.5} style={{ color: "var(--grey)" }} />
                    <span className="text-label" style={{ color: "var(--grey)" }}>
                      CONTINUE · {savedProjects.length}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    {savedProjects.map((p, i) => (
                      <motion.button
                        key={i}
                        type="button"
                        onClick={() => choose("demo", p)}
                        whileHover={reduce ? undefined : { x: 4 }}
                        transition={{ duration: DUR.hover / 1000, ease: EASE.out }}
                        className="group flex items-center gap-4 py-2.5 text-left"
                        style={{ borderTop: "1px solid var(--border)" }}
                      >
                        <span
                          className="flex size-9 shrink-0 items-center justify-center"
                          style={{ background: "var(--ink)" }}
                        >
                          <PixelMark cell={3} gap={1} tone="paper" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-sans text-sm font-semibold" style={{ color: "var(--ink)" }}>
                            {p.name}
                          </p>
                          <p className="font-mono text-[10px] tracking-wide" style={{ color: "var(--grey)" }}>
                            {p.site} · {p.lastEdited}
                          </p>
                        </div>
                        <span
                          className="font-mono text-[10px] uppercase tracking-wider"
                          style={{ color: p.status === "complete" ? "var(--green)" : "var(--amber)" }}
                        >
                          {p.status}
                        </span>
                        <ArrowRight
                          className="size-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                          strokeWidth={1.5}
                          style={{ color: "var(--grey)" }}
                        />
                      </motion.button>
                    ))}
                  </div>
                </motion.div>
              )}

              {/* Footer disclaimer */}
              <motion.div
                {...rise(0.48)}
                className="mt-6 flex items-center justify-between border-t pt-3"
                style={{ borderColor: "var(--ink)" }}
              >
                <p className="font-mono text-[10px] leading-relaxed" style={{ color: "var(--grey)" }}>
                  Decision-support tool — not engineering authority.
                  <br />
                  Built structures require licensed sign-off.
                </p>
                <span className="font-mono text-[10px] tracking-widest" style={{ color: "var(--grey)" }}>
                  S1 / WELCOME
                </span>
              </motion.div>
            </div>
          </div>

          {/* ─── RIGHT — dithered data-image plate ─────────────────────────── */}
          <div className="relative flex-1 overflow-hidden" style={{ background: "var(--ink)" }}>
            {/* The dithered image, clip-revealed then held; bounded parallax */}
            <motion.div
              className="absolute inset-0"
              initial={reduce ? { opacity: 0 } : { clipPath: "inset(0 0 0 100%)" }}
              animate={reduce ? { opacity: 1 } : { clipPath: "inset(0 0 0 0%)" }}
              transition={{ delay: 0.2, duration: 0.9, ease: EASE.out }}
            >
              <motion.div
                className="absolute inset-0"
                style={{
                  backgroundImage: "url('/assets/refs/welcome-canopy.webp')",
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                  filter: "contrast(1.05) brightness(0.96) saturate(1.05)",
                  scale: 1.1,
                }}
                animate={{ x: mousePos.x * -10, y: mousePos.y * -10 }}
                transition={{ duration: 0.9, ease: EASE.out }}
              />
            </motion.div>

            {/* Ink vignette so the type below always reads */}
            <div
              className="pointer-events-none absolute inset-0"
              style={{
                background:
                  "linear-gradient(180deg, color-mix(in srgb, var(--ink) 35%, transparent) 0%, transparent 28%, transparent 55%, var(--ink) 100%)",
              }}
            />

            {/* Corner crosshair (echoes s1-firstrun) */}
            <motion.div
              {...rise(0.5)}
              className="absolute right-6 top-6 font-mono text-[10px] tracking-widest"
              style={{ color: "color-mix(in srgb, var(--paper) 70%, transparent)" }}
            >
              <span style={{ color: "var(--green2)" }}>+</span> 41.4106° N · 2.2270° E
            </motion.div>

            {/* Caption plate — mono index only */}
            <div className="absolute inset-x-9 bottom-10">
              <motion.div {...rise(0.4)} className="flex items-center gap-3">
                <PixelMark cell={5} gap={2} tone="paper" />
                <span
                  className="font-mono text-[10px] tracking-widest"
                  style={{ color: "color-mix(in srgb, var(--paper) 60%, transparent)" }}
                >
                  FIG. 01 · REFUGI CLIMÀTIC · PRIMAVERA SOUND
                </span>
              </motion.div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ── Door row — an editorial ruled list-row with a large index numeral ─────── */
function DoorRow({
  index,
  title,
  sub,
  accent,
  icon,
  onClick,
  rise,
  reduce,
  primary,
  badge,
}: {
  index: string;
  title: string;
  sub: string;
  accent: string;
  icon: React.ReactNode;
  onClick: () => void;
  rise: Record<string, unknown>;
  reduce: boolean;
  primary?: boolean;
  badge?: string;
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
      {/* Sliding accent fill on hover — a deliberate, settling reveal */}
      <motion.span
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0"
        style={{ background: primary ? accent : "var(--paper)" }}
        initial={false}
        animate={{ width: hover && !reduce ? "100%" : "0%" }}
        transition={{ duration: DUR.card / 1000, ease: EASE.out }}
      />
      {/* Content sits above the fill */}
      <span
        className="relative font-mono text-sm tabular-nums"
        style={{ color: hover && primary ? "var(--paper)" : "var(--grey)" }}
      >
        {index}
      </span>
      <span className="relative min-w-0 flex-1">
        <span className="flex items-center gap-2">
          {badge && (
            <span
              className="font-mono text-[9px] uppercase tracking-widest"
              style={{ color: hover ? "var(--ink)" : "var(--grey)" }}
            >
              {badge}
            </span>
          )}
        </span>
        <span
          className="block font-sans font-bold"
          style={{
            fontSize: "1.35rem",
            letterSpacing: "-0.02em",
            color: hover ? (primary ? "var(--paper)" : "var(--ink)") : "var(--ink)",
          }}
        >
          {title}
        </span>
        <span
          className="mt-0.5 block text-sm"
          style={{ color: hover ? (primary ? "color-mix(in srgb, var(--paper) 80%, transparent)" : "var(--ink)") : "var(--grey)" }}
        >
          {sub}
        </span>
      </span>
      <motion.span
        className="relative shrink-0"
        animate={{ x: hover && !reduce ? 4 : 0 }}
        transition={{ duration: DUR.hover / 1000, ease: EASE.out }}
        style={{ filter: hover && primary ? "brightness(0) invert(1)" : "none" }}
      >
        {icon}
      </motion.span>
    </motion.button>
  );
}
