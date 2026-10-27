/**
 * Thin CLI for the Phase-1 parser (Plan 01-03 Task 2) — the manual/scripted trigger
 * surface. No HTTP server (deferred to Phase 7 / FE-04, karpathy: no speculative
 * server). No commander/yargs — `node:util` `parseArgs` plus a positional brief.
 *
 *   node src/parser/cli.ts "<brief text>" [--project <id>]
 *   echo "<brief text>" | node src/parser/cli.ts [--project <id>]
 *
 * Reads the brief from argv (positional) or stdin, parses it via `parseBrief`
 * (sonnet→haiku, stop_reason-gated, validated), writes the artifact via
 * `writeParsedBrief` (validate-then-write), and prints the artifact path. On a
 * terminal `ParserError` it prints `code: message` and exits non-zero. It never
 * prints or logs the API key (threat T-01-10) — the key is read from the env by the
 * SDK and never surfaced here.
 */

import { parseArgs } from "node:util";

import { parseBrief } from "./parser.ts";
import { writeParsedBrief } from "./artifact.ts";
import { ParserError } from "./errors.ts";

/** Read all of stdin to a string (used when no positional brief is given). */
async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString("utf-8");
}

async function main(): Promise<void> {
  const { values, positionals } = parseArgs({
    args: process.argv.slice(2),
    options: {
      project: { type: "string", default: "dev" },
    },
    allowPositionals: true,
  });

  const projectId = values.project as string;

  // Brief text: positional arg first; fall back to stdin.
  let text = positionals[0];
  if (text === undefined || text.trim() === "") {
    text = (await readStdin()).trim();
  }
  if (!text) {
    // Usage error (not a parse failure) — distinct, non-zero exit.
    process.stderr.write(
      'usage: cli.ts "<brief text>" [--project <id>]  (or pipe the brief on stdin)\n',
    );
    process.exit(2);
  }

  const brief = await parseBrief(text);
  const path = writeParsedBrief(projectId, brief, { inputText: text });
  console.log(path);
}

main().catch((err: unknown) => {
  if (err instanceof ParserError) {
    // Terminal parse failure → surface the 500 code + message. NEVER the API key.
    process.stderr.write(`${err.code}: ${err.message}\n`);
    process.exit(1);
  }
  // Any other unexpected error: print the message (no secret is referenced anywhere
  // in this CLI path) and fail non-zero.
  process.stderr.write(`error: ${(err as Error).message}\n`);
  process.exit(1);
});
