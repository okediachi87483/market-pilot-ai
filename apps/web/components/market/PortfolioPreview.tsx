import { Card } from "@/components/ui/Card";

/** Placeholder — see docs/component-architecture.md (PortfolioSummary). */
export function PortfolioPreview() {
  return (
    <Card eyebrow="Portfolio Performance" mock>
      <div className="font-mono text-3xl font-semibold text-text-primary">$128,402.19</div>
      <div className="mt-1 flex gap-3 font-mono text-xs">
        <span className="text-positive">+$1,842.60 today</span>
        <span className="text-text-tertiary">+18.4% total return</span>
      </div>
    </Card>
  );
}
