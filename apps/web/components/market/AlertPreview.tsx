import { Card } from "@/components/ui/Card";

/** Placeholder — see docs/component-architecture.md (AlertsTimeline), docs/profit-protection.md. */
export function AlertPreview() {
  return (
    <Card eyebrow="Recent Alerts" mock>
      <div className="flex flex-col gap-3 text-xs">
        <div>
          <p className="text-text-secondary">Daily profit target reached &middot; +2.1%</p>
          <p className="mt-0.5 font-mono text-text-tertiary">09:12:47 ET</p>
        </div>
        <div>
          <p className="text-text-secondary">Portfolio drawdown 3.2% &mdash; below threshold</p>
          <p className="mt-0.5 font-mono text-text-tertiary">08:50:03 ET</p>
        </div>
      </div>
    </Card>
  );
}
