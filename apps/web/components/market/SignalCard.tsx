import { StatusTag, type MarketState } from "@/components/ui/StatusTag";
import type { SignalResponse, SignalStrength, SignalType } from "@/lib/signals";

const SIGNAL_COLOR: Record<SignalType, string> = {
  BUY: "var(--color-positive)",
  SELL: "var(--color-negative)",
  HOLD: "var(--color-neutral-signal)",
};

const STRENGTH_COLOR: Record<SignalStrength, string> = {
  STRONG: "var(--color-accent-teal)",
  MODERATE: "var(--color-text-secondary)",
  WEAK: "var(--color-text-tertiary)",
};

/**
 * The professional Signal Center card (Step 13) — precise and discplined,
 * never celebratory. No color-flashing, no emoji, no "you're about to
 * win" framing: STRONG uses the same restrained teal accent as any other
 * emphasized value elsewhere in the design system, not gold or flashing
 * green. This is a deterministic strategy's *suggestion*, presented with
 * its full reasoning — not a bet.
 */
export function SignalCard({ signal }: { signal: SignalResponse }) {
  return (
    <section className="flex flex-col gap-4 rounded-md border border-border-subtle bg-bg-1 p-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xl font-bold text-text-primary">{signal.symbol}</div>
          <div className="text-[11px] text-text-tertiary">
            {signal.strategy_label} &middot; {signal.interval}
          </div>
        </div>
        <StatusTag state={signal.market_regime as MarketState} />
      </div>

      <div className="flex items-center gap-3">
        <span
          className="text-2xl font-bold tracking-wide"
          style={{ color: SIGNAL_COLOR[signal.signal] }}
        >
          {signal.signal}
        </span>
        {signal.strength && (
          <span
            className="rounded-sm border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider"
            style={{
              color: STRENGTH_COLOR[signal.strength],
              borderColor: STRENGTH_COLOR[signal.strength],
            }}
          >
            {signal.strength}
          </span>
        )}
      </div>

      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
          Why this signal exists
        </div>
        <ul className="flex flex-col gap-1.5">
          {signal.reasons.map((reason) => (
            <li key={reason} className="flex gap-2 text-xs text-text-secondary">
              <svg width="12" height="12" viewBox="0 0 20 20" className="mt-0.5 shrink-0 text-positive" aria-hidden="true">
                <path d="M4 10 L8 14 L16 5" fill="none" stroke="currentColor" strokeWidth="2" />
              </svg>
              {reason}
            </li>
          ))}
        </ul>
      </div>

      {signal.invalidating_conditions.length > 0 && (
        <div>
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
            Invalidated if
          </div>
          <ul className="flex flex-col gap-1.5">
            {signal.invalidating_conditions.map((condition) => (
              <li key={condition} className="flex gap-2 text-xs text-text-secondary">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-text-tertiary" aria-hidden="true" />
                {condition}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center justify-between border-t border-border-subtle pt-3">
        <span className="text-[11px] uppercase tracking-wider text-text-tertiary">Status</span>
        <span className="font-mono text-xs text-text-primary">{signal.status}</span>
      </div>
    </section>
  );
}
