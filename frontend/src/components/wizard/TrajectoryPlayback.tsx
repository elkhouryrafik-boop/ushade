import { useEffect, useMemo, useRef, useState } from "react";
import { useControl } from "react-map-gl/mapbox";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { TripsLayer } from "@deck.gl/geo-layers";
import { useQuery } from "@tanstack/react-query";
import { getTrajectories } from "@/lib/heatguard-api";
import { useHeatGuard } from "@/lib/heatguard-store";
import { PALETTE } from "@/lib/tokens";
import { Play, Pause } from "iconoir-react";

/**
 * Live crowd-sim playback (the wow — UI-SPEC HANDOFF decision #3): replays the REAL
 * per-agent rollout (trajectories.json, 650 agents) as animated trails flowing toward
 * the stages. This is WHY the crowd density concentrates where it does — the user
 * watches the actual algorithm produce the busy-zones the placement reasons over.
 *
 * Perf: runs on its OWN dedicated deck overlay (a second MapboxOverlay) so the rAF
 * currentTime tick only re-renders the trail layer — the heavy heat/crowd field
 * layers (on the primary overlay) never rebuild during animation.
 */

// Bright cyan core — with ADDITIVE blending the overlapping trails accumulate into
// glowing nodes exactly where the crowd converges (the stages), the way the best
// flow maps read. Cyan is the cool crowd family, distinct from green/amber heat.
const CYAN: [number, number, number] = [86, 222, 238];

// Additive blending (luma.gl v9 params) — overlapping trails sum their light, so
// dense convergence points glow brighter. The signature "futuristic flow" look.
const ADDITIVE = {
  blend: true,
  blendColorOperation: "add",
  blendColorSrcFactor: "src-alpha",
  blendColorDstFactor: "one",
  blendAlphaOperation: "add",
  blendAlphaSrcFactor: "one",
  blendAlphaDstFactor: "one",
  depthCompare: "always",
} as const;

type Agent = { path: [number, number][]; timestamps: number[] };

export function TrajectoryPlayback() {
  const { state } = useHeatGuard();
  const { simRunId } = state;
  // Respect prefers-reduced-motion (WCAG 2.3.3 / spec §7): start paused so the
  // continuous animation never auto-plays for motion-sensitive users.
  const [playing, setPlaying] = useState(
    () =>
      typeof window === "undefined" ||
      !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );

  const { data } = useQuery({
    queryKey: ["trajectories", simRunId],
    queryFn: () => getTrajectories(simRunId!),
    enabled: simRunId !== null,
    staleTime: Infinity,
    retry: false,
  });

  // Pivot frames[t][agent] = [lon,lat,speed] → per-agent {path, timestamps}. Once.
  const agents = useMemo<Agent[]>(() => {
    const v = data?.runs.v2;
    if (!v) return [];
    const { frames, n_agents } = v;
    const out: Agent[] = [];
    // Subsample every 2nd agent (~325) — the full 650 render as an unreadable mass
    // (review P0); halving keeps the flow legible while still dense near stages.
    for (let a = 0; a < n_agents; a += 2) {
      const path: [number, number][] = [];
      const timestamps: number[] = [];
      for (let t = 0; t < frames.length; t++) {
        const p = frames[t][a];
        if (!p) continue;
        path.push([p[0], p[1]]);
        timestamps.push(t);
      }
      if (path.length > 1) out.push({ path, timestamps });
    }
    return out;
  }, [data]);

  const maxT = data?.runs.v2.n_steps_recorded ?? 0;

  // Dedicated overlay for the animated layer only.
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay({ interleaved: false, layers: [] }));
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;

  // Render the trips layer at the current time (own overlay → cheap re-render).
  const timeRef = useRef(0);
  const render = (t: number) =>
    overlayRef.current.setProps({
      layers: [
        // Soft wide under-trail — the glow halo (additive). Wide + low alpha so the
        // bloom builds where many agents overlap (the stages light up like nodes).
        new TripsLayer<Agent>({
          id: "agent-glow",
          data: agents,
          getPath: (d) => d.path,
          getTimestamps: (d) => d.timestamps,
          getColor: CYAN,
          opacity: 0.18,
          widthUnits: "pixels",
          getWidth: 7,
          widthMinPixels: 4,
          trailLength: Math.max(16, maxT * 0.16),
          currentTime: t,
          fadeTrail: true,
          jointRounded: true,
          capRounded: true,
          parameters: ADDITIVE,
        }),
        // Crisp bright core trail on top.
        new TripsLayer<Agent>({
          id: "agent-trails",
          data: agents,
          getPath: (d) => d.path,
          getTimestamps: (d) => d.timestamps,
          getColor: [170, 244, 255],
          opacity: 0.6,
          widthUnits: "pixels",
          getWidth: 1.6,
          widthMinPixels: 1,
          trailLength: Math.max(14, maxT * 0.13),
          currentTime: t,
          fadeTrail: true,
          jointRounded: true,
          capRounded: true,
          parameters: ADDITIVE,
        }),
      ],
    });

  useEffect(() => {
    if (!agents.length || !maxT) return;
    // Paused: draw ONE static frame and stop (no rAF — otherwise the page never
    // goes idle, which also blocks screenshots and wastes the GPU).
    if (!playing) {
      render(timeRef.current);
      return;
    }
    let raf = 0;
    const tick = () => {
      // ~16s for the full rollout @ 60fps — a calm, readable pace (was ~5s = too
      // fast). The PATHS are the real sim; only this playback clock is our choice.
      timeRef.current = (timeRef.current + maxT / 1000) % maxT;
      render(timeRef.current);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents, maxT, playing]);

  // Clear the layer when the component unmounts (leaving Placement).
  useEffect(() => () => overlayRef.current.setProps({ layers: [] }), []);

  if (!agents.length) return null;

  return (
    <button
      type="button"
      onClick={() => setPlaying((p) => !p)}
      className="pointer-events-auto absolute bottom-[232px] left-4 z-20 flex items-center gap-2 rounded-md border border-border bg-surface/95 px-3 py-2 font-mono text-[11px] text-text-primary backdrop-blur e2 hover:bg-muted"
      title={playing ? "Pause crowd-flow playback" : "Play crowd-flow playback"}
    >
      {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
      <span style={{ color: PALETTE.indigo }}>●</span>
      <span>{playing ? "Crowd flow — playing" : "Replay crowd flow"}</span>
      <span className="text-text-muted">· {data?.runs.v2.n_agents} agents</span>
    </button>
  );
}
