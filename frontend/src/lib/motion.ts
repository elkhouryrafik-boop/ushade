// Framer-motion easings — bezier ARRAYS, not CSS strings (framer rejects "cubic-bezier(...)").
export const EASE = {
  out:     [0.16, 1, 0.3, 1] as [number, number, number, number],
  outFast: [0.25, 1, 0.5, 1] as [number, number, number, number],
  inOut:   [0.65, 0, 0.35, 1] as [number, number, number, number],
  spring:  { stiffness: 200, damping: 24, mass: 0.8 },
} as const;

// CSS `transition-timing-function` strings (for style={{ transition }} / CSS, not framer).
export const EASE_CSS = {
  out:     'cubic-bezier(0.16, 1, 0.3, 1)',
  outFast: 'cubic-bezier(0.25, 1, 0.5, 1)',
  inOut:   'cubic-bezier(0.65, 0, 0.35, 1)',
} as const;

export const DUR = {
  tooltip:   150,
  hover:     200,
  inspector: 200,
  card:      400,
  stage:     500,
  countUp:   900,
  fly:       1000,
  bloom:     600,
} as const;
