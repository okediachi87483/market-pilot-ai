import { Card } from "@/components/ui/Card";
import { StatusTag } from "@/components/ui/StatusTag";

/**
 * Placeholder for MarketPilot's signature Market State Visualization
 * (docs/ui-design-system.md §7). A static, simplified render for the
 * Phase 2 foundation — the full interactive instrument (animated needle,
 * volatility pulse, hover tooltip) is built once real signal/AI data
 * exists to drive it. Mock values only.
 */
export function AIStatusGauge() {
  // Fixed mock reading: score 58/100, drawn on a 180° semicircle gauge
  // centered at (120,130) r=100 — same geometry as the design canvas.
  return (
    <Card eyebrow="AI Market Assessment" mock className="flex flex-col items-center gap-3">
      <svg viewBox="0 0 240 160" className="w-[70%] max-w-[220px]" aria-hidden="true">
        <path
          d="M20,130 A100,100 0 0 1 70,43.4"
          fill="none"
          stroke="var(--color-negative)"
          strokeWidth="10"
          strokeLinecap="round"
          opacity="0.55"
        />
        <path
          d="M70,43.4 A100,100 0 0 1 170,43.4"
          fill="none"
          stroke="var(--color-neutral-signal)"
          strokeWidth="10"
          strokeLinecap="round"
          opacity="0.4"
        />
        <path
          d="M170,43.4 A100,100 0 0 1 220,130"
          fill="none"
          stroke="var(--color-positive)"
          strokeWidth="10"
          strokeLinecap="round"
          opacity="0.55"
        />
        <circle cx="120" cy="130" r="6" fill="var(--color-bg-1)" stroke="var(--color-border-default)" strokeWidth="1.5" />
        <line x1="120" y1="130" x2="175.8" y2="79.2" stroke="var(--color-positive)" strokeWidth="3" strokeLinecap="round" />
        <circle cx="120" cy="130" r="3" fill="var(--color-positive)" />
      </svg>

      <StatusTag state="BULLISH" />

      <p className="text-center text-xs leading-relaxed text-text-secondary">
        Conditions currently favor continuation of the recent uptrend. Not a guarantee — see{" "}
        <span className="font-mono text-text-tertiary">/ai-analyst</span>.
      </p>
    </Card>
  );
}
