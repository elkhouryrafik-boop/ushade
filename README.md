# U-Shade

**Climate-aware shade placement for mass outdoor events.**

Festivals put tens of thousands of people on unshaded, low-albedo ground during the hottest
hours of summer, and the decision of *where* the shade goes is still made by intuition. U-Shade
places shade on the cells that are simultaneously the hottest and the busiest — and refuses to
report a number it cannot defend.

Built on Barcelona's Parc del Fòrum festival circuit, generalisable to any site with an EPW file
and a boundary.

Not affiliated with Primavera Sound, Parc del Fòrum or any venue named in the demo data; the
festival schedule is used as a published case study.

## What it does

A deterministic, sequential pipeline — no step guesses what the next one needs:

1. **Parse the brief.** A language model turns free-text into four typed operational fields and
   a theme label, using schema-constrained structured output. It is structurally barred from
   making any design decision; it translates, nothing more.
2. **Get the heat.** A real urban-microclimate service (infrared.city) returns a UTCI field,
   resampled onto a **6 m** master lattice.
3. **Simulate the crowd.** JuPedSim's Collision-Free Speed Model moves a persistent crowd across
   the site over a continuous daytime timeline, driven by the real festival schedule and by
   stage popularity grounded in Spotify monthly-listener counts.
4. **Build the demand field.** Crowd density × thermal excess above a **26 °C** comfort
   threshold.
5. **Solve placement.** Maximal covering location over that demand field, by a deterministic
   greedy heuristic **and** an exact integer program that emits a verifiable optimality
   certificate.
6. **Choose material.** The lowest-transport-carbon locally available reclaimed archetype, with
   cooling effectiveness scaled by one minus the membrane's solar transmissivity.
7. **Gate the result.** A cooling-acceptance gate with hash-locked thresholds that fails at run
   time if they are edited.

## What it can claim

From the paper, with the caveats attached:

- the acceptance gate passes at **full coverage** with a **4.8 °C** mean UTCI reduction against
  pre-locked thresholds of **4 °C minimum reduction and 70 % minimum coverage**;
- the 4.8 °C is not tuned after the fact — it is the **8 °C** declared ideal opaque-canopy
  benefit × (1 − **0.40** solar transmissivity) = 4.8 °C, through the real optical path;
- placement is **proven optimal at zero gap** against the greedy lower bound;
- materials: **22 sources across a 30 km span**, from a **16-archetype** catalogue merged with
  live-scraped reclaimed stock.

## What it does not claim

The project's distinguishing feature is this section, not the one above.

- **Crowd-density magnitude is `assumed`, not validated.** It fails its Lyon/MADRAS comparison
  against the Fruin crush ceiling. The demand field therefore ranks correctly but its absolute
  magnitude is not certified.
- **The crowd→heat metabolic feedback exists only in the visualisation layer.** The placement
  engine does not model people heating each other.
- **The pipeline deliberately stops at ranked shade zones.** Form-making — the actual structure —
  is handed to a human architect. This is a decision-support tool, not a generator.

Every quantity the system reports carries an explicit provenance tier: `grounded`, `derived`,
`assumed`, or `declared`. `UShade-Academic-Paper.md` documents each subsystem, defends the design
decisions against their alternatives, and records the specifications-versus-implementation
divergences.

## Repository map

```
src/                 Python pipeline — brief parsing, climate, crowd, placement,
                     materials, acceptance gate
frontend/            Vite + React + deck.gl organiser app (bun)
contracts/           JSON Schemas for every artifact that crosses a subsystem boundary
data/                Materials atlas, provenance table and synthetic seed data
viz/                 Standalone HTML build scripts for the site and layout maps
acceptance/          Hash-locked cooling-acceptance thresholds
tests/               pytest suite
UShade-Academic-Paper.md   Full system paper: architecture, methods, limits
docs/                Method notes and the archived legacy README
app/                 LEGACY — collaborator's "Material Harvesting" Streamlit mock.
                     Kept for reference only; it is NOT the product. See
                     docs/LEGACY-material-harvesting-mock.md
```

## Running it

The pipeline, offline:

```bash
pip install -e ".[dev]"
pytest -m "not crowd and not crowdsim and not geom and not red"
```

The organiser app:

```bash
cd frontend
bun install
bun run dev          # http://localhost:5173
```

Frontend unit tests: `bun run test` (vitest). End-to-end: `bunx playwright test` — needs the dev
server and a backend on `:8000`.

The crowd, crowdsim and geom tiers pull torch / jupedsim / rhino3dm and install per-extra; see
the marker list in `pyproject.toml`. The pipeline in `src/` needs Python and an infrared.city
key for live UTCI runs — the recorded demo artifacts replay without one.

## Data

This repository ships **synthetic operator data**. Venue, supplier and stakeholder records in
`data/` and in the frontend demo fixtures are generated placeholders (reserved `@example.org`
addresses, invented organisation names) with the same schema and field types as the originals,
so the pipeline runs identically without carrying a real contact list. Site names, material
specifications and numeric parameters are unchanged.



`app/` is a Streamlit prototype proposing "the Uber for Materials" — an idea an adversarial
review recommended blocking on the grounds that it was fabricated data dressed as an engine.
It is retained only so the review that rejected it remains auditable. Nothing in the shipped
pipeline imports it.

## Licence

MIT — see `LICENSE`.

