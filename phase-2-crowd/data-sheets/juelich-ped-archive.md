# Data sheet — Jülich Pedestrian Dynamics Data Archive

1. **Motivation.** Forschungszentrum Jülich's open archive of controlled pedestrian experiments — the field's reference for fundamental diagrams (speed↔density). ped.fz-juelich.de.
2. **Composition.** 50+ experiments: corridor, bottleneck, T-junction, stairs, stadium ingress/egress (HERMES), concert-hall entrance (BaSiGo corridor6, 926 participants). Per-person (x,y) trajectories (PeTrack), HDF5/text/JSON.
3. **Collection.** Instrumented lab/controlled experiments, overhead cameras, sub-metre tracking, 25 fps.
4. **Pre-processing (we must do).** Compute Voronoi density + speed via PedPy (native to this data + to JuPedSim output) → build the empirical FD to compare against.
5. **Uses.** ✅ **the physics gate** — validate the JuPedSim CFSM emergent speed–density curve against the empirical/ Weidmann FD at ±20% (RiMEA core test); promotes the LOCAL-PHYSICS sub-claim to DERIVED. ✗ NOT venue-scale, NO stage/attractor structure — cannot validate spatial allocation or magnitude.
6. **Distribution.** CC-BY 4.0, per-experiment DOIs (e.g. corridor6 = 10.34735/ped.2013.5). Verified reachable.
7. **Maintenance.** Actively maintained archive; versioned DOIs.
8. **Limitations.** Lab geometry, recruited participants (not festival demographics), bounded experiments — proves the physics is right, says nothing about where a festival crowd chooses to stand.
