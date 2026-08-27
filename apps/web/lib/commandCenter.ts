import { apiFetch } from "@/lib/api";
import type { AIAnalysis, AIStatus } from "@/lib/aiAnalyst";
import type { RegimeLabel } from "@/lib/analysis";
import type { PaperFill, PaperPortfolio, PaperPosition } from "@/lib/paperTrading";
import type { RiskPolicy } from "@/lib/risk";
import type { SignalResponse } from "@/lib/signals";

// Mirrors apps/api/app/schemas/command_center.py — kept in sync by hand
// until the generated-client tooling from docs/api.md §4 lands.
//
// One aggregated read replacing what used to be ~8-10 separate dashboard
// requests (docs/command-center.md §2) — every field below is either a
// direct reuse of an existing endpoint's own response shape (signals,
// ai_analyses, portfolio, risk's PaperPortfolio/RiskPolicy types) or a
// small aggregation-only shape (SystemHealth, MarketSnapshot,
// WatchlistQuote, ActivityEvent) defined here.

export interface SystemHealth {
  api: string;
  database: string;
  redis: string;
  market_data: string;
  ai: AIStatus;
}

export interface MarketSnapshot {
  symbol: string;
  asset_id: string;
  interval: string;
  source: string;
  is_mock: boolean;
  calculated_at: string;
  candle_count: number;
  price: { timestamp: string; close: number };
  features: {
    price_above_ema21: boolean | null;
    ema9_above_ema21: boolean | null;
    ema21_above_ema50: boolean | null;
    ema50_above_ema200: boolean | null;
    trend_alignment_score: number | null;
    trend_alignment_label: string | null;
    trend_direction: "bullish" | "bearish" | "mixed" | null;
    rsi_state: "oversold" | "neutral" | "overbought" | null;
    macd_state: "bullish" | "bearish" | "neutral" | null;
    volume_state: "low" | "normal" | "elevated" | null;
    volatility_state: "low" | "normal" | "elevated" | null;
  };
  regime: { regime: RegimeLabel; reasons: string[] };
}

export interface WatchlistQuote {
  symbol: string;
  close: string;
  change_pct: string | null;
  timestamp: string;
  source: string;
  is_mock: boolean;
}

export type ActivityEventType =
  | "SIGNAL_GENERATED"
  | "RISK_APPROVED"
  | "RISK_REJECTED"
  | "AI_ANALYSIS_COMPLETED"
  | "PAPER_ORDER_FILLED"
  | "POSITION_CLOSED";

export interface ActivityEvent {
  type: ActivityEventType;
  timestamp: string;
  symbol: string;
  summary: string;
  signal_id: string | null;
}

export interface RiskSummary {
  portfolio: {
    equity: string;
    cash: string;
    high_water_mark: string;
    drawdown_pct: string;
    open_position_count: number;
    open_position_value: string;
    available_exposure_value: string;
    realized_pl_today: string;
    as_of: string;
  };
  policy: RiskPolicy;
}

export interface CommandCenterSnapshot {
  generated_at: string;
  system_health: SystemHealth;
  market: MarketSnapshot;
  watchlist: WatchlistQuote[];
  signals: SignalResponse[];
  ai_analyses: AIAnalysis[];
  risk: RiskSummary;
  portfolio: PaperPortfolio;
  positions: PaperPosition[];
  recent_fills: PaperFill[];
  recent_activity: ActivityEvent[];
}

export function getCommandCenterSnapshot(options?: {
  symbol?: string;
  interval?: string;
  watchlist?: string[];
  activityLimit?: number;
}): Promise<CommandCenterSnapshot> {
  const params = new URLSearchParams();
  if (options?.symbol) params.set("symbol", options.symbol);
  if (options?.interval) params.set("interval", options.interval);
  if (options?.watchlist?.length) params.set("watchlist", options.watchlist.join(","));
  if (options?.activityLimit) params.set("activity_limit", String(options.activityLimit));
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<CommandCenterSnapshot>(`/api/v1/command-center${query}`);
}
