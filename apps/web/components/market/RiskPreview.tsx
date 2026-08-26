import { Card } from "@/components/ui/Card";

/** Placeholder — see docs/component-architecture.md (RiskPanel), docs/risk-engine.md. */
export function RiskPreview() {
  return (
    <Card eyebrow="Risk Exposure" mock>
      <div className="flex flex-col gap-3">
        <div>
          <div className="mb-1.5 flex justify-between text-xs">
            <span className="text-text-secondary">Portfolio exposure</span>
            <span className="font-mono text-text-primary">62% / 80%</span>
          </div>
          <div className="h-1.5 rounded-sm bg-bg-3">
            <div className="h-full w-[77%] rounded-sm bg-accent-teal" />
          </div>
        </div>
        <div>
          <div className="mb-1.5 flex justify-between text-xs">
            <span className="text-text-secondary">Drawdown</span>
            <span className="font-mono text-text-primary">3.2% / 8%</span>
          </div>
          <div className="h-1.5 rounded-sm bg-bg-3">
            <div className="h-full w-[40%] rounded-sm bg-accent-amber" />
          </div>
        </div>
      </div>
    </Card>
  );
}
