/**
 * Node contract validator over the neutral `contracts/` schemas (CONTRACT-02).
 *
 * The single source of truth for every inter-stage contract is the set of
 * `contracts/*.schema.json` files (JSON Schema draft 2020-12). This module is the
 * Node *consumer* of those files; the Python `validate.py` consumes the SAME files
 * with jsonschema 4.26, so the two runtimes cannot drift
 * (00-RESEARCH §Single-Source Schema Strategy, Pitfall A).
 *
 * 2020-12 REQUIRES the `Ajv2020` class imported from `ajv/dist/2020.js` — the
 * default `Ajv` import is draft-07 only and the two dialects cannot share an
 * instance (Pitfall F / T-00-10). `ajv-formats` restores the `date` (YYYY-MM-DD)
 * assertion that 2020-12 makes annotation-only by default.
 *
 * Cross-file `$ref` resolution: the shared crs/lattice defs self-key by their
 * embedded absolute `$id` (`https://heatguard/contracts/_defs/<name>.schema.json`),
 * which is exactly what the spatial schemas `$ref`. We `addSchema` each `_defs`
 * file (ajv keys it by its `$id`), so resolution matches the Python registry side
 * (see 00-02-SUMMARY deviation #1: absolute def `$id`, never a relative path).
 *
 * karpathy: thin and direct — one Ajv2020 instance, the _defs preloaded, a compile
 * cache, a raise-on-failure validate. ajv owns the validation math.
 */

import Ajv2020 from "ajv/dist/2020.js";
import type { ValidateFunction } from "ajv";
import addFormats from "ajv-formats";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Repo root = two levels up from src/validate/.
const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..");
const CONTRACTS_DIR = join(REPO_ROOT, "contracts");
const DEFS_DIR = join(CONTRACTS_DIR, "_defs");

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf-8"));
}

function schemaFilename(name: string): string {
  // Accept either a bare contract name ("utci_grid") or a full file name.
  return name.endsWith(".schema.json") ? name : `${name}.schema.json`;
}

// One shared Ajv2020 instance with the _defs preloaded. `strict: true` surfaces
// genuine schema authoring mistakes (the parity win); `allErrors` collects every
// violation for diagnostics.
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);

// The contracts carry `x-`-prefixed annotation keywords (`x-schema-version`,
// `x-units`) — readable provenance/unit metadata that validators must IGNORE.
// jsonschema (Python) already ignores unknown keywords; ajv `strict: true` would
// otherwise throw "unknown keyword". Register them as known no-op annotations so
// both runtimes treat the SAME files identically (cross-language parity) WITHOUT
// dropping strict mode for everything else.
ajv.addVocabulary(["x-schema-version", "x-units"]);

// Preload the shared defs so absolute `$ref`s (crs/lattice) resolve. ajv keys each
// added schema by its embedded `$id`.
for (const file of readdirSync(DEFS_DIR)) {
  if (file.endsWith(".json")) {
    ajv.addSchema(readJson(join(DEFS_DIR, file)));
  }
}

const _compiled = new Map<string, ValidateFunction>();

/**
 * Compile (and cache) the validate function for the named contract.
 * `name` may be "utci_grid" or "utci_grid.schema.json".
 *
 * Reuses an already-registered schema by its `$id` (via `getSchema`) so a contract
 * is compiled at most once even across module re-imports — `ajv.compile`
 * auto-registers the schema by `$id`, and a second compile of the same `$id` would
 * otherwise throw "schema already exists".
 */
export function compileSchema(name: string): ValidateFunction {
  const file = schemaFilename(name);
  const cached = _compiled.get(file);
  if (cached) return cached;
  const schema = readJson(join(CONTRACTS_DIR, file)) as { $id?: string };
  const existing = schema.$id ? ajv.getSchema(schema.$id) : undefined;
  const fn = (existing as ValidateFunction | undefined) ?? ajv.compile(schema);
  _compiled.set(file, fn);
  return fn;
}

/**
 * Validate `artifact` against the named contract; throw on failure.
 * Returns void on success (mirrors the Python `validate(...)` raise-on-failure API).
 */
export function validate(artifact: unknown, name: string): void {
  const fn = compileSchema(name);
  if (!fn(artifact)) {
    throw new Error(
      `Contract validation failed for "${name}": ${JSON.stringify(fn.errors)}`,
    );
  }
}

/** Non-throwing convenience: true iff `artifact` satisfies the contract. */
export function isValid(artifact: unknown, name: string): boolean {
  return compileSchema(name)(artifact) === true;
}
