/**
 * PixelMark — the IAAC Barcelona pixel-block motif (the scattered squares that sit
 * around IAAC's brand marks). A deterministic cluster of small squares: mostly ink,
 * one green accent. Decorative only — drop it beside a wordmark or kicker for the
 * IAAC "bitmap" texture. Sharp 2px corners, rationed colour, no animation by default.
 */

// 1 = ink square, 2 = green accent, 0 = empty. A fixed, hand-tuned scatter (no random
// so it renders identically every time).
const PATTERN: number[][] = [
  [1, 0, 1, 0, 0],
  [0, 1, 0, 0, 2],
  [1, 0, 0, 1, 0],
  [0, 0, 1, 0, 1],
];

export function PixelMark({
  cell = 4,
  gap = 2,
  className,
  tone = "ink",
}: {
  /** Square edge in px. */
  cell?: number;
  /** Gap between squares in px. */
  gap?: number;
  className?: string;
  /** "ink" on light surfaces, "paper" on the dark rail/map. */
  tone?: "ink" | "paper";
}) {
  const cols = PATTERN[0].length;
  const rows = PATTERN.length;
  const w = cols * cell + (cols - 1) * gap;
  const h = rows * cell + (rows - 1) * gap;
  const base = tone === "paper" ? "var(--paper)" : "var(--ink)";

  return (
    <svg
      className={className}
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      aria-hidden="true"
      style={{ display: "block", flexShrink: 0 }}
    >
      {PATTERN.flatMap((row, r) =>
        row.map((v, c) =>
          v === 0 ? null : (
            <rect
              key={`${r}-${c}`}
              x={c * (cell + gap)}
              y={r * (cell + gap)}
              width={cell}
              height={cell}
              fill={v === 2 ? "var(--green)" : base}
            />
          ),
        ),
      )}
    </svg>
  );
}
