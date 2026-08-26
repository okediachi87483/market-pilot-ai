import { Card } from "@/components/ui/Card";
import { StatusTag } from "@/components/ui/StatusTag";

/** Placeholder — see docs/component-architecture.md (SignalPanel). */
export function SignalPreview() {
  return (
    <Card eyebrow="Active Signals" mock>
      <div className="flex flex-col gap-2 rounded-md border border-border-subtle bg-bg-2 p-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-text-primary">NVDA</span>
          <StatusTag state="BULLISH" />
        </div>
        <div className="flex justify-between font-mono text-xs text-text-tertiary">
          <span>Confidence</span>
          <span className="text-text-primary">82%</span>
        </div>
      </div>
    </Card>
  );
}
