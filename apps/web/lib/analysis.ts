import { apiFetch } from "@/lib/api";
import type { SupportedInterval } from "@/lib/marketData";

// Mirrors apps/api/app/schemas/analysis.py — kept in sync by hand until
// the generated-client tooling from docs/api.md §4 lands.

export interface TrendIndicators {
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  ema9: number | null;
  ema21: number | null;
  ema50: number | null;
  ema200: number | null;
}

export interface MomentumIndicators {
  rsi14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  stochastic_k: number | null;
  stochastic_d: number | null;
}

export interface VolatilityIndicators {
  atr14: number | null;
  bollinger_upper: number | null;
  bollinger_middle: number | null;
  bollinger_lower: number | null;
  bollinger_width: number | null;
}

export interface VolumeIndicators {
  volume: number | null;
  volume_sma: number | null;
  relative_volume: number | null;
}

export interface Indicators {
  trend: TrendIndicators;
  momentum: MomentumIndicators;
  volatility: VolatilityIndicators;
  volume: VolumeIndicators;
}

export type RegimeLabel =
  | "BULLISH"
  | "BEARISH"
  | "SIDEWAYS"
  | "HIGH_VOLATILITY"
  | "LOW_VOLATILITY"
  | "INSUFFICIENT_DATA";

export interface MarketFeatures {
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
}

export interface Regime {
  regime: RegimeLabel;
  reasons: string[];
}

export interface AnalysisResponse {
  symbol: string;
  asset_id: string;
  interval: string;
  source: string;
  is_mock: boolean;
  calculated_at: string;
  candle_count: number;
  price: { timestamp: string; close: number };
  indicators: Indicators;
  features: MarketFeatures;
  regime: Regime;
}

export interface IndicatorPoint {
  timestamp: string;
  close: number | null;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  ema9: number | null;
  ema21: number | null;
  ema50: number | null;
  ema200: number | null;
  rsi14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  stochastic_k: number | null;
  stochastic_d: number | null;
  atr14: number | null;
  bollinger_upper: number | null;
  bollinger_middle: number | null;
  bollinger_lower: number | null;
  bollinger_width: number | null;
  volume: number | null;
  volume_sma: number | null;
  relative_volume: number | null;
}

export interface IndicatorSeriesResponse {
  symbol: string;
  asset_id: string;
  interval: string;
  source: string;
  is_mock: boolean;
  start: string;
  end: string;
  count: number;
  points: IndicatorPoint[];
}

export interface RegimeResponse {
  symbol: string;
  asset_id: string;
  interval: string;
  calculated_at: string;
  candle_count: number;
  regime: RegimeLabel;
  reasons: string[];
}

export function getAnalysis(
  symbol: string,
  interval: SupportedInterval = "1d",
): Promise<AnalysisResponse> {
  return apiFetch<AnalysisResponse>(
    `/api/v1/analysis/${encodeURIComponent(symbol)}?interval=${interval}`,
  );
}

export function getIndicatorSeries(
  symbol: string,
  options?: { interval?: SupportedInterval; start?: string; end?: string },
): Promise<IndicatorSeriesResponse> {
  const params = new URLSearchParams();
  if (options?.interval) params.set("interval", options.interval);
  if (options?.start) params.set("start", options.start);
  if (options?.end) params.set("end", options.end);
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<IndicatorSeriesResponse>(
    `/api/v1/analysis/${encodeURIComponent(symbol)}/indicators${query}`,
  );
}

export function getRegime(
  symbol: string,
  interval: SupportedInterval = "1d",
): Promise<RegimeResponse> {
  return apiFetch<RegimeResponse>(
    `/api/v1/analysis/${encodeURIComponent(symbol)}/regime?interval=${interval}`,
  );
}
