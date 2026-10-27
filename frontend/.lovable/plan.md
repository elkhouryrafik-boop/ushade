# HeatGuard SPA — Implementation Plan

A high-fidelity, fully client-side prototype. No backend, no auth provider — login is a UI gate that advances the flow. All "simulations" are scripted animations + mock data. State is shared across views via a single React context.

## Tech & Conventions

- TanStack Start (existing template), single route `/` with in-page step state (no route-per-view — flow is linear and shares heavy state; persistent top stepper drives transitions).
- Tailwind v4 dark theme defined in `src/styles.css` with semantic tokens + neon accents:
  - `--heat` (amber), `--eco` (emerald), `--flow` (cyan), `--danger` (magenta), `--bg` near-black, `--panel` elevated slate, `--grid` subtle lines.
- Shadcn components already in repo (button, card, input, select, slider, checkbox, progress, table, tooltip, dialog). Reuse, don't reinstall.
- Fonts: Inter (UI) + JetBrains Mono (technical labels/telemetry) loaded via `<link>` in `__root.tsx`.
- Icons: lucide-react.
- Animations: Tailwind transitions + small `motion`-style CSS keyframes (no new deps); SVG for map/3D mocks.

## State Model

`src/lib/heatguard-store.tsx` — React context + reducer:

```ts
type Step = 'login' | 'workspace' | 'simulation' | 'structural' | 'dashboard';
type Shape = { id; kind: 'boundary'|'stage'|'restroom'|'food'|'activation'|'dancefloor'; points: [x,y][] };
type Project = {
  capacity: number; budget: number; date: string;
  theme: 'Urban'|'Maritime'|'Natural'|'Industrial';
  shapes: Shape[];
  structural: { columnThickness: number; tension: number; optimization: 'eco'|'balanced'|'rigid' };
};
```

Derived dashboard metrics computed from inputs (budget spent ≈ 0.897 × budget, CO2 saved scales with capacity + theme, shade m² scales with boundary area).

## File Layout

```
src/routes/index.tsx                 → renders <HeatGuardApp/>
src/components/heatguard/
  HeatGuardApp.tsx                   → step router + TopNav
  TopNav.tsx                         → 5-step stepper, logo, active/done states
  views/LoginView.tsx
  views/WorkspaceView.tsx
  views/SimulationView.tsx
  views/StructuralView.tsx
  views/DashboardView.tsx
  map/MapCanvas.tsx                  → SVG satellite-style mock (dark tiles + roads + parcels)
  map/DrawingToolbar.tsx
  map/LayerChecklist.tsx
  map/HeatmapOverlay.tsx             → SVG radial gradients (amber/red)
  map/FlowOverlay.tsx                → animated cyan arrows + magenta dwell circles
  viewport3d/Viewport3D.tsx          → SVG isometric canopy + columns, parallax on mouse
  dashboard/HeroRender.tsx           → AI-generated hero image
  dashboard/KpiCards.tsx
  dashboard/BomTable.tsx
  shared/ProgressiveStepper.tsx      → multi-line loader with check-offs
  shared/TelemetryLog.tsx            → monospace streaming log
src/lib/heatguard-store.tsx
src/lib/heatguard-mock.ts            → BOM rows, telemetry lines, derived metrics
src/styles.css                       → token additions
```

## View Details

**View 1 — Login.** Centered card on grid-noise bg. Geometric logo (SVG hexagon). Inputs with focus ring glow. "Access Console" → sets step to `workspace` (no validation, any input accepted; empty is also fine for demo).

**View 2 — Workspace.** 30/70 split. Left: capacity, budget, native date input, theme select, scrolling layer checklist that fills as shapes are drawn, FAB "Run Thermal & Crowd Simulation" disabled until ≥1 boundary + ≥1 other shape exist. Right: `MapCanvas` (SVG: dark satellite tiles via layered rects + subtle road paths + parcel polygons). Floating top-right toolbar with 6 tool buttons (active state = neon ring). Click-to-add points: boundary/activation/dancefloor = polygon (click points, double-click to close); stage/food = drag-box; restroom = single point marker. Each shape color-coded per spec.

**View 3 — Simulation.** On entry, full-canvas `ProgressiveStepper` cycles through the two listed steps (plus 2 more for realism) with check animations and a streaming telemetry log on the right. After ~3s, canvas reveals the same drawn boundary with `HeatmapOverlay` (amber→red radial blooms anchored on stages/dance floors) and `FlowOverlay` (animated dashed cyan arrows between entrances↔stages↔restrooms, magenta pulsing circles at dwell points). Floating bottom-left toggles panel (3 checkboxes). Bottom-right CTA → structural view.

**View 4 — Structural.** Loader card overlays for ~2.5s with rotating Rhino/Karamba copy. Then split: left controls (3 sliders + optimization toggle group, all writing to store), right `Viewport3D` — an SVG/CSS isometric canopy made of dynamically-sized columns (thickness slider scales stroke), tensioned cable mesh (tension slider scales sag curve), and a tilted roof plane. Subtle mouse-parallax rotation. Bottom-right CTA → dashboard.

**View 5 — Dashboard.** 
- Hero: generated photoreal image (one `imagegen` call, premium tier, festival canopy render) saved to `src/assets/heatguard-hero.jpg`.
- 3 KPI cards: Financial (progress bar `spent/budget`), Environmental (large emerald number, CO2 tons), Cooling (m² shade with mini sparkline SVG).
- BOM table: 6–8 rows generated from theme + shapes (recycled scaffolding, upcycled sailcloth, etc.), columns: Material ID, Source, Qty, Unit Weight, Transport km.
- Footer: "Export Project Dossier" (secondary, triggers toast "Dossier prepared"), "Create New Project Workflow" (primary, resets store → login).

## Design Tokens (additions to styles.css)

```css
--heat: oklch(0.78 0.18 60);     /* amber */
--eco: oklch(0.78 0.17 160);     /* emerald */
--flow: oklch(0.82 0.13 220);    /* cyan */
--danger: oklch(0.7 0.25 340);   /* magenta */
--panel: oklch(0.19 0.015 250);
--panel-2: oklch(0.23 0.018 250);
--grid-line: oklch(1 0 0 / 6%);
```

Background gets a subtle 24px grid via `background-image` linear gradients for the console feel.

## Out of Scope (explicit)

- Real Mapbox/Three.js — mocked with SVG/CSS for fidelity without heavy deps.
- Real auth, real persistence (state resets on reload — acceptable for prototype).
- Real PDF/CSV export — toast confirmation only.

## Deliverable

One generated hero image + ~18 new files. No new npm deps. After build, all 5 views reachable end-to-end with inputs from View 2 flowing into View 5 metrics.
