export type MarketState =
  | "BULLISH"
  | "BEARISH"
  | "NEUTRAL"
  | "HIGH_RISK"
  | "MARKET_CLOSED"
  | "VOLATILITY_EVENT";

const STATE_META: Record<MarketState, { label: string; colorVar: string }> = {
  BULLISH: { label: "BULLISH", colorVar: "var(--color-positive)" },
  BEARISH: { label: "BEARISH", colorVar: "var(--color-negative)" },
  NEUTRAL: { label: "NEUTRAL", colorVar: "var(--color-neutral-signal)" },
  HIGH_RISK: { label: "HIGH RISK", colorVar: "var(--color-accent-amber)" },
  MARKET_CLOSED: { label: "MARKET CLOSED", colorVar: "var(--color-text-tertiary)" },
  VOLATILITY_EVENT: { label: "VOLATILITY EVENT", colorVar: "var(--color-accent-amber)" },
};

function StateGlyph({ state }: { state: MarketState }) {
  switch (state) {
    case "BULLISH":
      return (
        <path d="M10 4 L17 15 L3 15 Z" fill="currentColor" />
      );
    case "BEARISH":
      return (
        <path d="M10 16 L3 5 L17 5 Z" fill="currentColor" />
      );
    case "NEUTRAL":
      return <rect x="4" y="9" width="12" height="2" rx="1" fill="currentColor" />;
    case "HIGH_RISK":
      return (
        <>
          <path d="M10 2 L18 10 L10 18 L2 10 Z" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <rect x="9" y="6" width="2" height="6" fill="currentColor" />
          <rect x="9" y="13.5" width="2" height="2" fill="currentColor" />
        </>
      );
    case "MARKET_CLOSED":
      return (
        <>
          <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M10 6 L10 10 L13 12" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </>
      );
    case "VOLATILITY_EVENT":
      return (
        <path
          d="M2 10 L6 10 L8 4 L11 16 L13 10 L18 10"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      );
  }
}

/**
 * Status is always glyph + color + text label together — never color
 * alone. See docs/ui-design-system.md §5. This is the one status
 * vocabulary shared by every screen.
 */
export function StatusTag({ state }: { state: MarketState }) {
  const meta = STATE_META[state];
  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs font-semibold"
      style={{ color: meta.colorVar }}
    >
      <svg width="12" height="12" viewBox="0 0 20 20" aria-hidden="true">
        <StateGlyph state={state} />
      </svg>
      {meta.label}
    </span>
  );
}
