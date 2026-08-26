import { AIStatusGauge } from "@/components/market/AIStatusGauge";
import { AlertPreview } from "@/components/market/AlertPreview";
import { MarketStatusPreview } from "@/components/market/MarketStatusPreview";
import { PortfolioPreview } from "@/components/market/PortfolioPreview";
import { RiskPreview } from "@/components/market/RiskPreview";
import { SignalPreview } from "@/components/market/SignalPreview";
import { WatchlistPreview } from "@/components/market/WatchlistPreview";

/**
 * MarketPilot Command Center — see docs/ui-screen-map.md (/dashboard).
 * All data below is clearly-labeled mock data (Step 4): this proves the
 * visual language, not a finished dashboard — full data wiring lands
 * with the packages that own it in Phase 3+.
 */
export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-5">
      <MarketStatusPreview />

      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        <AIStatusGauge />
        <PortfolioPreview />
        <RiskPreview />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-[2fr_1fr]">
        <WatchlistPreview />
        <SignalPreview />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        <AlertPreview />
      </div>
    </div>
  );
}
