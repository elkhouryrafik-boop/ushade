import type { ReactNode } from "react";
import { ArrowRight } from "iconoir-react";
import { cn } from "@/lib/utils";

/**
 * StageScaffold — IAAC anatomy for the 400px aside panel.
 * Header: index + headline + optional editorial lede, ruled bottom.
 * Content: scrollable flex-1 slot.
 * Footer: full-width CTA + optional error text.
 */
export function StageScaffold({
  index,
  title,
  lede,
  children,
  cta,
  className,
}: {
  index?: string;
  title: string;
  lede?: string;
  children: ReactNode;
  cta?: {
    label: string;
    onClick: () => void;
    disabled?: boolean;
    disabledReason?: string;
  };
  className?: string;
}) {
  return (
    <div className={cn("flex h-full flex-col", className)}>
      <header
        className="shrink-0 px-6 pb-5 pt-6"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        {index && (
          <p className="text-label mb-1.5" style={{ color: "var(--grey)" }}>
            {index}
          </p>
        )}
        <h1 className="text-headline text-text-primary">{title}</h1>
        {lede && (
          <p className="text-editorial mt-2" style={{ color: "var(--grey)" }}>
            {lede}
          </p>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>

      {cta && (
        <div
          className="shrink-0 px-6 pb-5 pt-4"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <button
            type="button"
            disabled={cta.disabled}
            onClick={cta.onClick}
            title={cta.disabled ? cta.disabledReason : undefined}
            className={cn(
              "flex h-11 w-full items-center justify-center gap-2 font-sans font-bold tracking-wide transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              cta.disabled
                ? "cursor-not-allowed opacity-40"
                : "hover:opacity-90 active:scale-[0.99]",
            )}
            style={{
              background: cta.disabled ? "var(--grey)" : "var(--green)",
              color: "var(--white)",
              borderRadius: "var(--radius-sm)",
              letterSpacing: "0.04em",
              fontSize: "0.875rem",
            }}
          >
            {cta.label}
            <ArrowRight className="size-4" strokeWidth={2} />
          </button>
          {cta.disabled && cta.disabledReason && (
            <p className="mt-2 text-center text-label" style={{ color: "var(--grey)" }}>
              {cta.disabledReason}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** IAAC empty / honest-state block. */
export function EmptyState({
  title,
  body,
  icon,
}: {
  title: string;
  body: string;
  icon?: ReactNode;
}) {
  return (
    <div
      className="flex flex-col items-center px-5 py-10 text-center"
      style={{ border: "1px dashed var(--border)", borderRadius: "var(--radius-md)" }}
    >
      {icon && <div className="mb-3" style={{ color: "var(--grey)" }}>{icon}</div>}
      <p className="text-subhead text-text-primary">{title}</p>
      <p className="mt-2 text-sm leading-relaxed text-text-muted">{body}</p>
    </div>
  );
}
