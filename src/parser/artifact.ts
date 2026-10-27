/**
 * `writeParsedBrief` — validate-then-write the parsed_brief artifact (Plan 01-03 Task 2).
 *
 * The load-bearing guarantee (Pitfall 7 / threat T-01-08): an invalid or partial
 * brief NEVER hits disk. `validate(brief, "parsed_brief")` runs FIRST and throws on
 * failure; only a contract-valid brief is written, and only then is the manifest's
 * `parsed_brief` stage recorded. On a validation throw there is no artifact and no
 * manifest mutation.
 *
 * The artifact lands at `projects/<id>/parsed_brief.json` (gitignored). The manifest
 * stage is recorded via the byte-parity Node writer (`manifest.ts`), so resume in
 * later phases sees the same content-hash recipe as the Python canonical manifest.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

import type { ParsedBrief } from "./types.ts";
import { validate } from "../validate/validate.ts";
import { contentHash, markParsedBriefDone } from "./manifest.ts";

/**
 * Validate `brief` against the frozen `parsed_brief` contract, then write it to
 * `projects/<projectId>/parsed_brief.json` and record the `parsed_brief` manifest
 * stage as done.
 *
 * @param projectId  Project id; the artifact + manifest live under `projects/<id>/`
 *                   (root overridable via `opts.projectRoot`, default "projects").
 * @param brief      The ParsedBrief to persist. Validated BEFORE any write.
 * @param opts.projectRoot  Override the projects root (tests use a tmp dir).
 * @param opts.inputText    The raw brief text — the parsed_brief stage's INPUT, hashed
 *                          into `input_hash` so a changed brief invalidates resume.
 * @returns The absolute path to the written `parsed_brief.json`.
 * @throws  If `brief` fails contract validation — and in that case NOTHING is written.
 */
export function writeParsedBrief(
  projectId: string,
  brief: ParsedBrief,
  opts?: { projectRoot?: string; inputText?: string },
): string {
  // (1) validate FIRST — throws before any mkdir/write (Pitfall 7; never persist an
  // invalid/partial artifact). No filesystem side effect happens before this passes.
  validate(brief, "parsed_brief");

  // (2) resolve projects/<id>/parsed_brief.json (root default "projects").
  const root = opts?.projectRoot ?? "projects";
  const projectDir = resolve(root, projectId);
  const artifactPath = join(projectDir, "parsed_brief.json");

  // (3) write the validated brief.
  mkdirSync(projectDir, { recursive: true });
  writeFileSync(artifactPath, JSON.stringify(brief, null, 2), "utf-8");

  // (4) record the parsed_brief manifest stage with content-hash parity.
  // input_hash = hash of the raw brief text (the stage input); output_hash = hash of
  // the parsed brief object (the stage output).
  const inputHash = contentHash(opts?.inputText ?? "");
  const outputHash = contentHash(brief);
  markParsedBriefDone(projectId, {
    inputHash,
    outputHash,
    projectRoot: root,
  });

  // (5) return the artifact path.
  return artifactPath;
}
