/**
 * MaterialsProvider (UI-SPEC §0) — the materials data adapter.
 *
 * Two implementations behind one interface:
 *   - `mockMaterialsProvider` — the labelled `stale_snapshot` demo set (offline-safe).
 *   - `realMaterialsProvider` — hits the REAL backend `GET /api/marketplace/materials`
 *     (archetype-grouped: scrape → classify → dedupe → carbon → bindable pools).
 *
 * `getMaterialsProvider()` picks via `VITE_USE_REAL_MATERIALS` (default OFF = mock, so
 * the demo never breaks when the backend is down). Flip the env var to go live — the UI
 * needs ZERO other change (the swap the spec always promised).
 *
 * Real data is HONESTLY thinner than the mock: most scraped feeds expose no photo, no
 * condition grade, and no stock count. We fill those with explicit "not stated" rather
 * than fabricate — quantity/distance/carbon may legitimately be null.
 */

export type ProvenanceTier = "GROUNDED" | "DERIVED" | "ASSUMED" | "DECLARED";

export interface MaterialItem {
  id: string;
  name: string;
  type: "struct" | "membr";
  /** Structured quantity — the focal datum. Null when the feed doesn't expose stock. */
  quantity: number | null;
  unit: string;
  /** Distance from site (km) — DERIVED road routing. Null if unrouted. */
  distanceKm: number | null;
  /** Transport carbon (kgCO2e) — ASSUMED, transport-only. Null when quantity unknown. */
  transportCarbonKg: number | null;
  /** Per-unit transport carbon (kgCO2e per unit) — shows even when total qty unknown. */
  transportCarbonPerUnitKg?: number | null;
  origin: string;
  supplier: string;
  /** WGS84 [lon, lat] pin. */
  lonLat: [number, number];
  quantityTier: ProvenanceTier;
  /** Passport fields. Real feeds often lack these → honest fallbacks, never faked. */
  condition: string;
  availableUntil: string;
  installMethod: string;
  verifiedSupplier: boolean;
  /** REAL supplier/stock photo URL, or null → no real photo for this listing. Never an
   * AI render — a real photo always wins over the illustration and carries no AI badge. */
  photoUrl: string | null;
  /** Optional AI-generated archetype illustration URL. Defaults (in the card) to the
   * deterministic `/materials/<id>.webp`. Shown ONLY when there is no real photoUrl, and
   * ALWAYS labelled "AI illustration" — never presented as real reclaimed stock. */
  illustrationUrl?: string | null;
  doubleBooked?: boolean;
  /** Real backend only: the specific listing a hold binds (archetype card → one listing). */
  bindListingId?: string;
  supplierId?: string;
  listingCount?: number;
  supplierCount?: number;
  // Datasheet-sourced engineering specs (CRISP-DM Phase 2, 2026-06-22). Each has a
  // matching provenance tier in `provenance`. Present on the catalogue feed.
  solarTransmissivity?: number | null;
  shadePct?: number | null;
  unitMassKg?: number | null;
  thicknessMm?: number | null;
  maxSpanMeters?: number | null;
  costPerUnit?: number | null;
  waterproof?: boolean | null;
  /** Per-spec provenance tier (field name → tier). */
  provenance?: Record<string, ProvenanceTier>;
  provenanceSources?: Record<string, string>;
  /** True if a live listing backs this archetype (hold can reserve it); else REFERENCE. */
  bindable?: boolean;
  /** Where the bindable stock comes from: live scrape, supplier onboarding, or none. */
  bindSource?: "scrape" | "onboarded" | "reference";
}

/** Deterministic AI-illustration path for an archetype id: `/materials/<id>.webp` (served
 * from `public/materials/`). The card uses this as the fallback when a card carries no
 * explicit `illustrationUrl`; a missing file degrades to an honest placeholder via onError. */
export function materialIllustrationUrl(id: string): string {
  return `/materials/${id}.webp`;
}

export interface CatalogueResult {
  status: "live" | "stale_snapshot" | "unavailable";
  asOf?: string;
  items: MaterialItem[];
  bindableCount: number;
}

export interface MaterialsResult {
  status: "live" | "stale_snapshot" | "unavailable";
  asOf?: string;
  items: MaterialItem[];
  /** Real backend transparency: listings before dedup vs cards served. */
  rawCount?: number;
  listingCount?: number;
}

export interface MaterialsProvider {
  queryMaterials(opts: { center: [number, number]; radiusKm: number }): Promise<MaterialsResult>;
  /** The full datasheet-sourced catalogue (every archetype + provenance + bindability). */
  queryCatalogue(): Promise<CatalogueResult>;
  /** Every DISTINCT live-scraped listing, region-wide (radius uncapped) — the raw haul the
   *  scraper actually found, NOT collapsed to archetypes. Far stock is included on purpose. */
  queryLiveListings(opts: { center: [number, number] }): Promise<MaterialsResult>;
}

// --------------------------------------------------------------------------- //
// Mock (offline demo) — labelled stale, never live.
// --------------------------------------------------------------------------- //
const MOCK_ITEMS: MaterialItem[] = [
  {
    id: "timber-01", name: "Reclaimed pine truss timber", type: "struct",
    quantity: 12.4, unit: "m³", distanceKm: 9.1, transportCarbonKg: 78,
    origin: "Sant Adrià strip-out", supplier: "Synthetic reclaim timber yard, demo district",
    lonLat: [2.236, 41.425], quantityTier: "GROUNDED",
    condition: "Reusable · grade B", availableUntil: "30 Jun",
    installMethod: "Bolt-fit truss · demountable, no cutting",
    verifiedSupplier: true,
    photoUrl: "https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=600&q=70",
  },
  {
    id: "scaffold-01", name: "Reclaimed steel scaffold", type: "struct",
    quantity: 1840, unit: "kg", distanceKm: 3.2, transportCarbonKg: 41,
    origin: "Poblenou demolition, BCN", supplier: "Synthetic demolition-reuse supplier, demo district",
    lonLat: [2.214, 41.41], quantityTier: "ASSUMED",
    condition: "Reusable · grade A", availableUntil: "12 Jul",
    installMethod: "Clamp-coupler frame · fully demountable",
    verifiedSupplier: true,
    photoUrl: "https://images.unsplash.com/photo-1581094794329-c8112a89af12?w=600&q=70",
  },
  {
    id: "membrane-01", name: "Recovered PVC membrane", type: "membr",
    quantity: 620, unit: "m²", distanceKm: 5.8, transportCarbonKg: 33,
    origin: "Fira BCN event teardown", supplier: "Synthetic membrane recovery supplier, demo district",
    // On the Sant Adrià waterfront (land) just E of the Fòrum — the old [2.241, 41.398]
    // sat ~900 m offshore in open sea.
    lonLat: [2.2365, 41.4085], quantityTier: "ASSUMED",
    condition: "Reusable · minor patching", availableUntil: "5 Jul",
    installMethod: "Tensioned panels · eyelet-fixed",
    verifiedSupplier: false, photoUrl: null,
    doubleBooked: true,
  },
  {
    id: "membrane-02", name: "Woven jute shade cloth", type: "membr",
    quantity: 410, unit: "m²", distanceKm: 6.4, transportCarbonKg: 19,
    origin: "Textile co-op surplus", supplier: "Synthetic textile-reuse co-op, demo district",
    lonLat: [2.219, 41.402], quantityTier: "ASSUMED",
    condition: "Good · UV-stable", availableUntil: "20 Jul",
    installMethod: "Lashed to frame · no fixings",
    verifiedSupplier: false,
    photoUrl: "https://images.unsplash.com/photo-1528283648649-33347faa5d9e?w=600&q=70",
  },
];

export const mockMaterialsProvider: MaterialsProvider = {
  async queryMaterials({ radiusKm }) {
    const items = MOCK_ITEMS.filter((m) => (m.distanceKm ?? 0) <= radiusKm);
    return { status: "stale_snapshot", asOf: "2026-06-19 09:00 CET", items };
  },
  async queryCatalogue() {
    return {
      status: "stale_snapshot",
      asOf: "2026-06-19 09:00 CET",
      items: MOCK_ITEMS.map((m) => ({ ...m, bindable: true, bindSource: "onboarded" as const })),
      bindableCount: MOCK_ITEMS.length,
    };
  },
  // Offline mock has no live scrape — honest empty result.
  async queryLiveListings() {
    return { status: "unavailable", items: [], rawCount: 0, listingCount: 0 };
  },
};

// --------------------------------------------------------------------------- //
// Real backend adapter — GET /api/marketplace/materials (archetype-grouped).
// --------------------------------------------------------------------------- //
interface ApiCard {
  id: string;
  materialId: string;
  name: string;
  type: "struct" | "membr";
  quantity: number | null;
  unit: string;
  quantityTier: ProvenanceTier;
  distanceKm: number | null;
  transportCarbonKg: number | null;
  transportCarbonPerUnitKg: number | null;
  origin: string;
  supplier: string;
  supplierId: string;
  lonLat: [number, number];
  availability: string;
  listingCount: number;
  supplierCount: number;
  listings: { id: string; supplier: string; supplierId: string; distanceKm: number | null }[];
}

/** Map a backend archetype card → the UI MaterialItem (honest "not stated" for gaps). */
function mapCard(c: ApiCard): MaterialItem {
  const nearest = c.listings[0]; // sorted nearest-first by the backend
  return {
    id: c.id,
    name: c.name,
    type: c.type,
    quantity: c.quantity,
    unit: c.unit,
    distanceKm: c.distanceKm,
    transportCarbonKg: c.transportCarbonKg,
    transportCarbonPerUnitKg: c.transportCarbonPerUnitKg,
    origin: c.origin,
    supplier: c.supplierCount > 1 ? `${c.supplierCount} suppliers` : c.supplier,
    lonLat: c.lonLat,
    quantityTier: c.quantityTier,
    condition: "Condition not stated", // scraped feeds carry no grade — honest, not faked
    availableUntil: "Not stated",
    installMethod: "Not stated — set on supplier confirm",
    verifiedSupplier: false, // trust is an admin gate, never self-asserted
    photoUrl: null,
    bindListingId: nearest?.id,
    supplierId: c.supplierId,
    listingCount: c.listingCount,
    supplierCount: c.supplierCount,
  };
}

/** A single live-scraped listing (group=listing) — one supplier's stock of an archetype. */
interface ApiListing {
  id: string;
  materialId: string;
  name: string;
  type: "struct" | "membr";
  quantity: number | null;
  unit: string;
  quantityTier: ProvenanceTier;
  distanceKm: number | null;
  transportCarbonKg: number | null;
  transportCarbonPerUnitKg: number | null;
  origin: string;
  supplier: string;
  supplierId: string;
  lonLat: [number, number];
  availability: string;
  sourceUrl: string | null;
  solarTransmissivity: number | null;
  /** How many raw scrape variants rolled up into this one listing (transparency). */
  listingsRolledUp?: number;
}

/** Map a live listing → MaterialItem. No scraped photo exists, so we reuse the archetype's
 *  illustration (we HAVE that image) rather than fabricate one — badged "Reference photo". */
function mapListing(c: ApiListing): MaterialItem {
  return {
    id: c.id,
    name: c.name,
    type: c.type,
    quantity: c.quantity,
    unit: c.unit,
    distanceKm: c.distanceKm,
    transportCarbonKg: c.transportCarbonKg,
    transportCarbonPerUnitKg: c.transportCarbonPerUnitKg,
    origin: c.origin,
    supplier: c.supplier,
    lonLat: c.lonLat,
    quantityTier: c.quantityTier,
    condition: "Live scraped stock — supplier-confirmable",
    availableUntil: "Live",
    installMethod: "Not stated — set on supplier confirm",
    verifiedSupplier: false,
    photoUrl: null,
    // Reuse the archetype illustration for the listing's material type (no AI gen per listing).
    illustrationUrl: materialIllustrationUrl(c.materialId),
    bindListingId: c.id,
    supplierId: c.supplierId,
    solarTransmissivity: c.solarTransmissivity,
    bindable: true,
    bindSource: "scrape",
  };
}

interface ApiCatalogueCard {
  id: string; materialId: string; name: string; type: "struct" | "membr"; unit: string;
  solarTransmissivity: number | null; shadePct: number | null;
  unitMassKg: number | null; thicknessMm: number | null; maxSpanMeters: number | null;
  waterproof: boolean | null; costPerUnit: number | null;
  distanceKm: number | null; transportCarbonPerUnitKg: number | null;
  origin: string; supplier: string; lonLat: [number, number];
  provenance: Record<string, ProvenanceTier>; provenanceSources: Record<string, string>;
  bindable: boolean; bindListingId: string | null; bindSource: "scrape" | "onboarded" | "reference";
  availability: string;
  quantity: number | null; listingCount: number; supplierCount: number;
}

/** Map a backend catalogue card → MaterialItem (carries the sourced specs + provenance). */
function mapCatalogueCard(c: ApiCatalogueCard): MaterialItem {
  return {
    id: c.id, name: c.name, type: c.type, quantity: c.quantity, unit: c.unit,
    distanceKm: c.distanceKm, transportCarbonKg: null,
    transportCarbonPerUnitKg: c.transportCarbonPerUnitKg,
    origin: c.origin, supplier: c.supplierCount > 1 ? `${c.supplierCount} suppliers` : c.supplier,
    lonLat: c.lonLat,
    quantityTier: (c.provenance?.distanceKm ?? "DERIVED"),
    condition:
      c.bindSource === "scrape"
        ? "Live scraped stock — supplier-confirmable"
        : c.bindSource === "onboarded"
          ? "Supplier-listed stock — unverified until checked"
          : "Reference — sourced specs, no live stock",
    availableUntil: c.bindable ? "Live" : "On supplier onboard",
    installMethod: "Not stated — set on supplier confirm",
    verifiedSupplier: false, photoUrl: null,
    bindListingId: c.bindListingId ?? undefined,
    listingCount: c.listingCount, supplierCount: c.supplierCount,
    solarTransmissivity: c.solarTransmissivity, shadePct: c.shadePct,
    unitMassKg: c.unitMassKg, thicknessMm: c.thicknessMm, maxSpanMeters: c.maxSpanMeters,
    costPerUnit: c.costPerUnit, waterproof: c.waterproof,
    provenance: c.provenance, provenanceSources: c.provenanceSources,
    bindable: c.bindable, bindSource: c.bindSource,
  };
}

export const realMaterialsProvider: MaterialsProvider = {
  async queryMaterials({ center, radiusKm }) {
    const [lon, lat] = center;
    const qs = new URLSearchParams({
      project_id: import.meta.env.VITE_PROJECT_ID || "primavera-demo",
      lon: String(lon), lat: String(lat), radius_km: String(radiusKm), group: "archetype",
    });
    const res = await fetch(`/api/marketplace/materials?${qs}`);
    if (!res.ok) throw new Error(`materials query failed: ${res.status}`);
    const body = await res.json();
    return {
      status: body.status,
      asOf: body.asOf ?? undefined,
      items: (body.items as ApiCard[]).map(mapCard),
      rawCount: body.rawCount,
      listingCount: body.listingCount,
    };
  },
  async queryCatalogue() {
    const qs = new URLSearchParams({
      project_id: import.meta.env.VITE_PROJECT_ID || "primavera-demo",
    });
    const res = await fetch(`/api/marketplace/catalogue?${qs}`);
    if (!res.ok) throw new Error(`catalogue query failed: ${res.status}`);
    const body = await res.json();
    return {
      status: body.status,
      asOf: body.asOf ?? undefined,
      items: (body.items as ApiCatalogueCard[]).map(mapCatalogueCard),
      bindableCount: body.bindableCount ?? 0,
    };
  },
  async queryLiveListings({ center }) {
    const [lon, lat] = center;
    // group=listing → one row per scraped listing; radius_km=500 (the API max) so far stock
    // is included — we want the WHOLE haul, not the metro-local slice.
    const qs = new URLSearchParams({
      project_id: import.meta.env.VITE_PROJECT_ID || "primavera-demo",
      lon: String(lon), lat: String(lat), radius_km: "500", group: "listing",
    });
    const res = await fetch(`/api/marketplace/materials?${qs}`);
    if (!res.ok) throw new Error(`live listings query failed: ${res.status}`);
    const body = await res.json();
    const raw = body.items as ApiListing[];

    // Collapse same-material-from-same-supplier repeats into ONE card — the feed exposes no
    // quantity, so it returns the same stock as many near-identical rows (61× the same ULMA
    // scaffold tube). We group by material+supplier and surface the rolled-up COUNT as the
    // volume signal ("how much is around"), which is what those repeats actually encode.
    const groups = new Map<string, ApiListing[]>();
    for (const it of raw) {
      const k = `${it.materialId}::${it.supplierId}`;
      const arr = groups.get(k);
      if (arr) arr.push(it);
      else groups.set(k, [it]);
    }
    const items: MaterialItem[] = [...groups.values()].map((g) => {
      const rep = g.reduce((a, b) => ((a.distanceKm ?? Infinity) <= (b.distanceKm ?? Infinity) ? a : b));
      const qtys = g.map((x) => x.quantity).filter((q): q is number => q != null);
      const carbons = g.map((x) => x.transportCarbonKg).filter((q): q is number => q != null);
      return {
        ...mapListing(rep),
        quantity: qtys.length ? qtys.reduce((a, b) => a + b, 0) : null,
        transportCarbonKg: carbons.length ? carbons.reduce((a, b) => a + b, 0) : null,
        listingCount: g.length, // how many raw listings rolled up — the availability proxy
        supplierCount: 1, // grouped per single supplier
      };
    });
    items.sort((a, b) => (a.distanceKm ?? Infinity) - (b.distanceKm ?? Infinity));

    return {
      status: body.status,
      asOf: body.asOf ?? undefined,
      items,
      rawCount: body.rawCount,
      listingCount: body.listingCount,
    };
  },
};

export function getMaterialsProvider(): MaterialsProvider {
  return import.meta.env.VITE_USE_REAL_MATERIALS === "1"
    ? realMaterialsProvider
    : mockMaterialsProvider;
}

// --------------------------------------------------------------------------- //
// Holds client — the binding reserve (POST /api/marketplace/holds, /cancel).
// --------------------------------------------------------------------------- //
export interface PlacedHold {
  id: string;
  state: string;
  expiresAt: number; // epoch ms (parsed from the backend's UTC ISO expires_at)
  remainingSeconds: number;
}

export class DoubleBookedError extends Error {
  constructor(public available: number) {
    super("insufficient stock");
  }
}

function uuid(): string {
  // idempotency key — client-generated (a retry must reuse it, per the backend recipe).
  return (crypto as Crypto).randomUUID();
}

export const holdsApi = {
  /** Place a binding hold against a specific listing. Throws DoubleBookedError on 409. */
  async placeHold(opts: {
    listingId: string;
    organiserId: string;
    qty: number;
    idempotencyKey?: string;
  }): Promise<PlacedHold> {
    const res = await fetch("/api/marketplace/holds", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        listing_id: opts.listingId,
        organiser_id: opts.organiserId,
        qty: opts.qty,
        idempotency_key: opts.idempotencyKey ?? uuid(),
      }),
    });
    if (res.status === 409) {
      const d = await res.json().catch(() => ({}));
      throw new DoubleBookedError(d?.detail?.available ?? 0);
    }
    if (!res.ok && res.status !== 201) throw new Error(`place hold failed: ${res.status}`);
    const h = await res.json();
    return {
      id: h.id,
      state: h.state,
      expiresAt: Date.parse(h.expires_at),
      remainingSeconds: h.remaining_seconds ?? 0,
    };
  },

  async cancelHold(holdId: string, organiserId: string): Promise<void> {
    await fetch(`/api/marketplace/holds/${holdId}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ organiser_id: organiserId }),
    });
  },
};
