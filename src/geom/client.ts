/**
 * GEOM-01 — the RhinoComputeClient seam (Fake | Reference | Live) + typed error.
 *
 * Clone of the Phase-2a infrared_client three-way client_factory seam crossed to TS, with
 * src/parser/errors.ts for the typed-error shape (instanceof-discriminated, carries `cause`).
 *
 * INVARIANT — importing this module is NETWORK-FREE and side-effect-free: axios is lazy-imported
 * inside LiveRhinoClient.solve ONLY, and node:child_process (+ fs/os/path/util) inside
 * ReferenceGeometryClient.solve ONLY. So a bare `import "./client.ts"` pulls neither the network
 * dep nor a subprocess dep (clone the infrared `_load_sdk` lazy discipline; RESEARCH Pitfall 2).
 *
 * SECRET DISCIPLINE: RHINO_COMPUTE_KEY is read from process.env and flowed ONLY into the request
 * header — never assigned to a logged variable (clone infrared _default_client_factory). No
 * RHINO_* value is ever hardcoded.
 *
 * Three implementations the Wave-3 orchestrator can inject:
 *   - FakeRhinoClient        → returns a recorded gh_response fixture (default offline / tests)
 *   - ReferenceGeometryClient→ DEMO DEFAULT: bridges to the Python PREVIEW generator subprocess
 *   - LiveRhinoClient        → opt-in axios POST to Rhino.Compute (gated by RHINO_LIVE upstream)
 */

import type { GhRequest, GhResponse } from "./request.ts";

// [CITED: PRD §Phase 4 endpoint :8081/grasshopper] mirrors src/geom/constants.py RHINO_PORT
// (the ONE source of truth) — never inline it elsewhere.
const RHINO_PORT = 8081;

/** The client seam every implementation satisfies. */
export interface RhinoComputeClient {
  solve(req: GhRequest): Promise<GhResponse>;
}

/**
 * Typed Rhino.Compute / reference-generator failure (clone src/parser/errors.ts shape:
 * instanceof-discriminated, carries `cause`). A thrown RhinoComputeError → the Wave-3
 * orchestrator marks the manifest stage NOT done. Never carries or logs a secret.
 */
export class RhinoComputeError extends Error {
  readonly name = "RhinoComputeError";
  constructor(
    message: string,
    readonly cause?: unknown,
  ) {
    super(message);
  }
}

/**
 * A minimal contract-valid recorded gh_response — the default fixture FakeRhinoClient returns
 * when constructed with no args (so tests can `new FakeRhinoClient()` and get a usable response).
 * `OUT_Mesh.b64` is a tiny valid base64 placeholder; the BOM is a non-negative stub.
 */
const DEFAULT_RECORDED_RESPONSE: GhResponse = {
  schema_version: "1.0.0",
  OUT_Mesh: { b64: "" }, // empty string is valid base64 (the recorded-fixture placeholder)
  OUT_BOM: { pillars: 0, membrane_m2: 0 },
};

/**
 * Offline fixture client (tests / default offline tier). Returns the recorded gh_response with
 * NO network. `raiseOnSolve` simulates a solve failure as a typed RhinoComputeError.
 */
export class FakeRhinoClient implements RhinoComputeClient {
  constructor(
    private readonly recorded: GhResponse = DEFAULT_RECORDED_RESPONSE,
    private readonly raiseOnSolve = false,
  ) {}

  async solve(_req: GhRequest): Promise<GhResponse> {
    if (this.raiseOnSolve) {
      throw new RhinoComputeError("fake solve failure (test)");
    }
    return this.recorded; // recorded fixture; no network
  }
}

/**
 * DEMO DEFAULT (no EC2): bridges to the Python PREVIEW generator
 * (`python -m geom.reference_generator`, Plan 03). node:child_process and friends are
 * lazy-imported inside solve so importing this module stays side-effect-free.
 *
 * Temp-file invocation (chosen over stdout so a large mesh JSON can't blow the pipe buffer):
 *   1. write the validated gh_request to a temp JSON file (mkdtemp under os.tmpdir())
 *   2. execFile("python", ["-m","geom.reference_generator","--input",req,"--output",resp], {timeout})
 *   3. exit 0 → read + JSON.parse the gh_response temp file, return it (caller ajv-validates, Wave 3)
 *   4. non-zero exit OR unreadable/unparseable output → RhinoComputeError(msg, stderr tail)
 *   5. always remove the temp dir (finally)
 */
export class ReferenceGeometryClient implements RhinoComputeClient {
  constructor(
    private readonly opts: { timeoutMs?: number; python?: string } = {},
  ) {}

  async solve(req: GhRequest): Promise<GhResponse> {
    const { execFile } = await import("node:child_process"); // LAZY — import stays side-effect-free
    const { promisify } = await import("node:util");
    const fs = await import("node:fs/promises");
    const os = await import("node:os");
    const path = await import("node:path");
    const run = promisify(execFile);
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), "ghreq-"));
    const inPath = path.join(dir, "gh_request.json");
    const outPath = path.join(dir, "gh_response.json");
    try {
      await fs.writeFile(inPath, JSON.stringify(req));
      await run(
        this.opts.python ?? "python",
        [
          "-m",
          "geom.reference_generator",
          "--input",
          inPath,
          "--output",
          outPath,
        ],
        { timeout: this.opts.timeoutMs ?? 120000 },
      );
      const raw = await fs.readFile(outPath, "utf8");
      return JSON.parse(raw) as GhResponse; // caller ajv-validates (Wave 3)
    } catch (e: unknown) {
      const tail =
        typeof (e as { stderr?: unknown })?.stderr === "string"
          ? ((e as { stderr: string }).stderr).slice(-2000)
          : String(e);
      throw new RhinoComputeError(
        "reference generator (python) solve failed",
        tail,
      );
    } finally {
      await fs.rm(dir, { recursive: true, force: true });
    }
  }
}

/**
 * Opt-in LIVE client — axios POST to Rhino.Compute. axios is lazy-imported here so the module
 * import stays network-free. RHINO_HOST/RHINO_TIMEOUT_MS/RHINO_COMPUTE_KEY come from ${ENV_VAR}
 * only; the key flows straight into the request header and is never assigned to a logged variable.
 */
export class LiveRhinoClient implements RhinoComputeClient {
  async solve(req: GhRequest): Promise<GhResponse> {
    const { default: axios } = await import("axios"); // LAZY (clone _load_sdk) — import stays network-free
    const host = process.env.RHINO_HOST; // ${ENV_VAR} only
    if (!host) {
      throw new RhinoComputeError("RHINO_HOST not set (RHINO_LIVE path)");
    }
    try {
      const { data } = await axios.post(
        `http://${host}:${RHINO_PORT}/grasshopper`, // PRD literal endpoint
        req,
        {
          timeout: Number(process.env.RHINO_TIMEOUT_MS ?? 600000), // > worst-case solve (ASSUMED; Pitfall 4)
          headers: {
            "Content-Type": "application/json",
            ...(process.env.RHINO_COMPUTE_KEY
              ? { RhinoComputeKey: process.env.RHINO_COMPUTE_KEY }
              : {}),
          },
        },
      );
      return data as GhResponse; // ajv-validated by the caller (Wave 3)
    } catch (e) {
      // SECRET DISCIPLINE (P7): an AxiosError carries `config.headers`, which includes the
      // `RhinoComputeKey` header built above. Never put the raw error into `cause` — any caller
      // that logs/serializes the cause would leak the key. Sanitize to message/code/status only.
      const ax = e as {
        message?: string;
        code?: string;
        response?: { status?: number };
      };
      throw new RhinoComputeError("rhino.compute solve failed", {
        message: ax.message,
        code: ax.code,
        status: ax.response?.status,
      });
    }
  }
}
