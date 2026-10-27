/**
 * Node-side manifest write for the `parsed_brief` stage (Plan 01-03 Task 1).
 *
 * Phase 0 shipped the CANONICAL resume manifest in Python (`src/manifest/manifest.py`)
 * and recorded a deliberate TIER NOTE: the Node orchestrator owns the RUNTIME
 * `projects/<id>/manifest.json` writes from Phase 1 on, implemented against the SAME
 * contract/algorithm (manifest.py docstring lines 16-23). This file is the Node half
 * of that deferred tier-ownership decision — and ONLY that.
 *
 * karpathy / scope guard: this is NOT a generic DAG engine. There is no
 * resume/invalidate/is_reusable logic here — those stay in the Python canonical
 * implementation until a Node consumer needs them. This module does exactly two
 * things: (1) hash an object with byte-parity against `manifest.py.content_hash`,
 * and (2) record the `parsed_brief` stage as done in a load-or-created manifest.
 *
 * The load-bearing correctness property (threat T-01-09): `contentHash` MUST produce
 * the identical hex to Python's `sha256(json.dumps(obj, sort_keys=True,
 * separators=(",",":")))`. A divergent recipe would silently break resume — so the
 * canonical recipe is replicated exactly below and proven live in
 * `tests/manifest_parity.test.ts`.
 */

import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";

/**
 * The pipeline DAG in execution order — mirrors `manifest.py` STAGE_ORDER exactly
 * (a fresh manifest has every stage pending). `parsed_brief` is the FIRST stage.
 */
const STAGE_ORDER = [
  "parsed_brief",
  "utci_grid",
  "crowd_grid",
  "structure_zones",
  "gh_response",
  "material_selection",
  "acceptance_verdict",
  "render",
] as const;

/**
 * Serialize `value` to a CANONICAL JSON string byte-identical to Python's
 * `json.dumps(value, sort_keys=True, separators=(",",":"))`:
 *   - object keys sorted ascending by code unit, RECURSIVELY (Python `sort_keys=True`),
 *   - compact separators `","` (items) and `":"` (key/value) — no spaces,
 *   - the same primitive encodings Python's json uses for the values this manifest
 *     ever hashes (strings, integers, the JSON literals).
 *
 * Scope note: the values hashed here are JSON artifacts (ParsedBrief objects and the
 * raw brief text) — strings, integers, nested objects/arrays. Python and JSON.stringify
 * agree on these. We do NOT attempt to reproduce Python's float `repr` (e.g. `1.0`),
 * since no float is ever hashed in this pipeline's parsed_brief stage; if a non-integer
 * number is passed, that is out of contract.
 */
function canonicalize(value: unknown): string {
  if (value === null) return "null";

  const t = typeof value;
  if (t === "string") return JSON.stringify(value);
  if (t === "boolean") return value ? "true" : "false";
  if (t === "number") {
    if (!Number.isFinite(value as number)) {
      // Python json emits NaN/Infinity tokens, but those never appear in a
      // contract-valid artifact — reject rather than silently diverge.
      throw new Error(`cannot canonicalize non-finite number: ${String(value)}`);
    }
    // Integers serialize identically in Python and JS. (The pipeline hashes only
    // integer/string fields — see scope note above.)
    return String(value);
  }

  if (Array.isArray(value)) {
    return "[" + value.map((v) => canonicalize(v)).join(",") + "]";
  }

  if (t === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort(); // Python sort_keys=True (code-unit order)
    const parts = keys.map(
      (k) => JSON.stringify(k) + ":" + canonicalize(obj[k]),
    );
    return "{" + parts.join(",") + "}";
  }

  // undefined / function / symbol — not representable; Python would never see these.
  throw new Error(`cannot canonicalize value of type ${t}`);
}

/**
 * SHA-256 over the CANONICAL JSON serialization of `obj` — byte-parity with
 * `manifest.py.content_hash` (sort_keys + compact separators). Returns the lowercase
 * hex digest. This is the manifest cache key (content-based, never mtime/exists).
 */
export function contentHash(obj: unknown): string {
  const canonical = canonicalize(obj);
  return createHash("sha256").update(canonical, "utf-8").digest("hex");
}

/** UTC ISO-8601 timestamp (mirrors manifest.py `_now_iso`). */
function nowIso(): string {
  return new Date().toISOString();
}

/** A single stage record — the exact shape manifest.py persists per stage. */
interface StageRecord {
  name: string;
  status: "pending" | "running" | "done" | "failed";
  artifact: string | null;
  input_hash: string | null;
  output_hash: string | null;
  completed_at: string | null;
}

interface ManifestDoc {
  project_id: string;
  created_at: string;
  stages: StageRecord[];
}

/** A fresh manifest: every stage pending, no hashes (mirrors manifest.py `__init__`). */
function freshManifest(projectId: string): ManifestDoc {
  return {
    project_id: projectId,
    created_at: nowIso(),
    stages: STAGE_ORDER.map((name) => ({
      name,
      status: "pending",
      artifact: null,
      input_hash: null,
      output_hash: null,
      completed_at: null,
    })),
  };
}

/**
 * Record the `parsed_brief` stage as done in `projects/<id>/manifest.json`,
 * load-or-creating the manifest. Sets the stage to
 * `{status:"done", artifact:"parsed_brief.json", input_hash, output_hash,
 * completed_at}` and writes the document with `indent=2` (manifest.py `write`).
 *
 * @param projectId  The project id; resolves under `projectRoot` (default "projects").
 * @param opts.inputHash  contentHash of the stage input (the raw brief text).
 * @param opts.outputHash contentHash of the stage output (the ParsedBrief object).
 * @param opts.projectRoot Override the projects root (tests write to a tmp dir).
 * @returns The absolute path to the written `manifest.json`.
 */
export function markParsedBriefDone(
  projectId: string,
  opts: { inputHash: string; outputHash: string; projectRoot?: string },
): string {
  return markStageDone(projectId, "parsed_brief", {
    inputHash: opts.inputHash,
    outputHash: opts.outputHash,
    artifact: "parsed_brief.json",
    projectRoot: opts.projectRoot,
  });
}

/**
 * The FROZEN gh_request / gh_response shapes (contracts/gh_request|gh_response.schema.json),
 * shared so a Node consumer of the geom stage (the live-EC2 RHINO_LIVE path in
 * src/geom/client.ts) can type the request it POSTs and the response it decodes. The offline
 * spine is the Python geom.geom.run_gh_stage; these types are the Node-seam half of GEOM-01.
 */
export interface GhRequest {
  schema_version: "1.0.0";
  IN_Footprint: Array<Array<{ x_m: number; y_m: number }>>;
  IN_FlowVectors: Array<{
    origin: { x_m: number; y_m: number };
    destination: { x_m: number; y_m: number };
  }>;
  IN_SunVector: [number, number, number];
}

export interface GhResponse {
  schema_version: "1.0.0";
  OUT_Mesh: { b64: string };
  OUT_BOM: { pillars: number; membrane_m2: number };
}

/** Load-or-create the manifest doc under `projectRoot/projectId`, returning the doc + its path. */
function loadOrCreateManifest(
  projectId: string,
  projectRoot: string | undefined,
): { doc: ManifestDoc; manifestPath: string; projectDir: string } {
  const root = projectRoot ?? "projects";
  const projectDir = resolve(root, projectId);
  const manifestPath = join(projectDir, "manifest.json");
  const doc: ManifestDoc = existsSync(manifestPath)
    ? (JSON.parse(readFileSync(manifestPath, "utf-8")) as ManifestDoc)
    : freshManifest(projectId);
  return { doc, manifestPath, projectDir };
}

function requireStage(doc: ManifestDoc, stageName: string): StageRecord {
  const stage = doc.stages.find((s) => s.name === stageName);
  if (!stage) {
    throw new Error(`manifest missing ${stageName} stage`);
  }
  return stage;
}

function writeManifest(
  doc: ManifestDoc,
  manifestPath: string,
  projectDir: string,
): string {
  mkdirSync(projectDir, { recursive: true });
  writeFileSync(manifestPath, JSON.stringify(doc, null, 2), "utf-8");
  return manifestPath;
}

/**
 * Mark any pipeline stage `running` (clears the prior hashes). Generalization of the
 * parsed_brief writer for the geom stage's mark_running -> solve -> mark_done/failed lifecycle
 * (clone core.py run lifecycle, Node half of the deferred tier-ownership decision).
 */
export function markStageRunning(
  projectId: string,
  stageName: string,
  opts: { inputHash?: string; projectRoot?: string } = {},
): string {
  const { doc, manifestPath, projectDir } = loadOrCreateManifest(
    projectId,
    opts.projectRoot,
  );
  const stage = requireStage(doc, stageName);
  stage.status = "running";
  stage.input_hash = opts.inputHash ?? null;
  return writeManifest(doc, manifestPath, projectDir);
}

/** Mark any pipeline stage `failed` (resume re-runs it; no partial artifact survives). */
export function markStageFailed(
  projectId: string,
  stageName: string,
  opts: { projectRoot?: string } = {},
): string {
  const { doc, manifestPath, projectDir } = loadOrCreateManifest(
    projectId,
    opts.projectRoot,
  );
  requireStage(doc, stageName).status = "failed";
  return writeManifest(doc, manifestPath, projectDir);
}

/** Mark any pipeline stage `done` with its artifact + input/output hashes + completed_at. */
export function markStageDone(
  projectId: string,
  stageName: string,
  opts: {
    inputHash: string;
    outputHash: string;
    artifact: string;
    projectRoot?: string;
  },
): string {
  const { doc, manifestPath, projectDir } = loadOrCreateManifest(
    projectId,
    opts.projectRoot,
  );
  const stage = requireStage(doc, stageName);
  stage.status = "done";
  stage.artifact = opts.artifact;
  stage.input_hash = opts.inputHash;
  stage.output_hash = opts.outputHash;
  stage.completed_at = nowIso();
  return writeManifest(doc, manifestPath, projectDir);
}

/**
 * Record the `gh_response` (Structural Geometry) stage as done (GEOM-01/05). Thin clone of
 * markParsedBriefDone for the geom artifact — the Node-seam half; the offline run lifecycle
 * lives in the Python geom.geom.run_gh_stage spine.
 */
export function markGhResponseDone(
  projectId: string,
  opts: { inputHash: string; outputHash: string; projectRoot?: string },
): string {
  return markStageDone(projectId, "gh_response", {
    inputHash: opts.inputHash,
    outputHash: opts.outputHash,
    artifact: "gh_response.json",
    projectRoot: opts.projectRoot,
  });
}
