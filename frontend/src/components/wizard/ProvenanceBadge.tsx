/**
 * ProvenanceBadge — intentionally renders NOTHING in the client app.
 *
 * The GROUNDED / DERIVED / ASSUMED provenance tiers are an INTERNAL data-quality
 * discipline (they govern how we model and what we trust) — they are not something
 * the organizer should see plastered on the UI (owner directive 2026-06-24). The
 * component is kept as a no-op so every existing call site stays valid and the
 * honesty discipline lives on in the data layer / tooltips can be reintroduced
 * deliberately later — but no tier pill is shown.
 */

export type Tier = "GROUNDED" | "DERIVED" | "ASSUMED" | "DECLARED" | "UNLABELLED";

export function ProvenanceBadge(_props: {
  tier: Tier;
  source?: string;
  method?: string;
  compact?: boolean;
  className?: string;
}) {
  return null;
}
