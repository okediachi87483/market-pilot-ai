import { CommandCenter } from "@/components/market/CommandCenter";

/**
 * MarketPilot Command Center — see docs/ui-screen-map.md (/dashboard)
 * and docs/command-center.md. One aggregated snapshot
 * (GET /api/v1/command-center) drives every section: market overview,
 * market state, active signals, AI Analyst, risk, paper portfolio,
 * recent activity, and system health — all real, backend-calculated
 * data (Phases 3-9); the underlying market data itself remains mock end
 * to end (docs/market-data.md), always labeled SOURCE: MOCK.
 */
export default function DashboardPage() {
  return <CommandCenter />;
}
