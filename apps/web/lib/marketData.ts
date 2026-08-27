import { apiFetch } from "@/lib/api";

// Mirrors apps/api/app/schemas/{asset,market_data}.py — kept in sync by
// hand until the generated-client tooling from docs/api.md §4 lands.

export interface Asset {
  id: string;
  symbol: string;
  name: string;
  asset_type: string;
  exchange: string | null;
  currency: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OHLCVBar {
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export interface QuoteResponse {
  symbol: string;
  asset_id: string;
  interval: string;
  source: string;
  is_mock: boolean;
  bar: OHLCVBar;
}

export interface HistoryResponse {
  symbol: string;
  asset_id: string;
  interval: string;
  source: string;
  is_mock: boolean;
  start: string;
  end: string;
  count: number;
  bars: OHLCVBar[];
}

export type SupportedInterval = "1m" | "5m" | "15m" | "1h" | "1d";

export function getAssets(assetType?: string): Promise<Asset[]> {
  const query = assetType ? `?asset_type=${encodeURIComponent(assetType)}` : "";
  return apiFetch<Asset[]>(`/api/v1/assets${query}`);
}

export function getAsset(symbol: string): Promise<Asset> {
  return apiFetch<Asset>(`/api/v1/assets/${encodeURIComponent(symbol)}`);
}

export function getQuote(symbol: string): Promise<QuoteResponse> {
  return apiFetch<QuoteResponse>(`/api/v1/market/${encodeURIComponent(symbol)}`);
}

export function getHistory(
  symbol: string,
  options?: { interval?: SupportedInterval; start?: string; end?: string },
): Promise<HistoryResponse> {
  const params = new URLSearchParams();
  if (options?.interval) params.set("interval", options.interval);
  if (options?.start) params.set("start", options.start);
  if (options?.end) params.set("end", options.end);
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<HistoryResponse>(`/api/v1/market/${encodeURIComponent(symbol)}/history${query}`);
}
