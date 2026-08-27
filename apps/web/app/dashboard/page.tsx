import { AlertPreview } from "@/components/market/AlertPreview";
import { MarketStateVisualization } from "@/components/market/MarketStateVisualization";
import { MarketStatusPreview } from "@/components/market/MarketStatusPreview";
import { PortfolioPreview } from "@/components/market/PortfolioPreview";
import { RiskPreview } from "@/components/market/RiskPreview";
import { SignalPreview } from "@/components/market/SignalPreview";
import { WatchlistPreview } from "@/components/market/WatchlistPreview";

/**
 * MarketPilot Command Center — see docs/ui-screen-map.md (/dashboard).
 * Market State (Phase 4), Signals (Phase 5), and Risk (Phase 6) are real,
 * backend-calculated data; portfolio/alerts remain clearly-labeled mock
 * placeholders until their owning phases land.
 */
export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-5">
      <MarketStatusPreview />

      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        <MarketStateVisualization />
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
