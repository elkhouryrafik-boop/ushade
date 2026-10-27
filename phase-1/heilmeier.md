# Heilmeier Catechism

**1. What are you trying to do (no jargon)?**
Replace the made-up numbers describing each reclaimed material (how much shade it gives, how heavy it is, what it costs, how far it travels) with real numbers from actual product spec sheets, and clearly mark which numbers are real vs still estimated.

**2. How is it done today, what are the limits?**
Today `data/materials.json` carries estimates I invented for the 6 newest materials — shade factor, mass, thickness, span, cost. The limit: the app's cooling/carbon/cost ranking is built on guesses, so an organiser can't defend it to a city or sponsor, and it violates the project's honesty rules.

**3. What is new, why will it succeed?**
A disciplined data hunt (CRISP-DM Phase 2) that pulls each spec from a real manufacturer datasheet/EPD and attaches a provenance tier to every field. It succeeds because these material classes (technical membranes, sailcloth, HDPE sheet, steel sections, shade-cloth) all have public datasheets with the exact quantities we need.

**4. Who cares — what difference?**
The festival organiser and the architect: the shade plan's cooling/carbon/cost claims become auditable instead of fabricated. The professor reviewing it (Naboni) cares: defensible data is the difference between a demo and a credible tool.

**5. Risks?**
Some reclaimed items have no product-specific datasheet (use virgin equivalent, label DERIVED); ranges instead of points; an atlas-inferred archetype turning out not to be a real reusable shade product (then we drop it). Cancellation if ≥3 of 6 can't be grounded.

**6. Cost?**
€0 — web research + existing tooling. Time: this milestone.

**7. How long?**
Phase 2 data hunt + Phase 3 write-in + Phase 4/5 validation within this session/milestone.

**8. Mid-term and final exams?**
Mid-term: ≥90% of spec fields GROUNDED/DERIVED with citations (≤10% DECLARED). Final: the material ranking reproduces from cited sources, distances are to Parc del Fòrum, transport factor is a cited DEFRA value, and every UI/PDF number carries a tier.
