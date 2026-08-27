import { apiFetch } from "@/lib/api";
import type { SupportedInterval } from "@/lib/marketData";

// Mirrors apps/api/app/schemas/signal.py — kept in sync by hand until
// the generated-client tooling from docs/api.md §4 lands.

export type SignalType = "BUY" | "SELL" | "HOLD";
export type SignalStrength = "WEAK" | "MODERATE" | "STRONG";
export type SignalStatus = "CANDIDATE" | "RISK_APPROVED" | "RISK_REJECTED" | "EXPIRED" | "SUPERSEDED";

export interface SignalResponse {
  id: string;
  symbol: string;
  interval: string;
  signal: SignalType;
  strategy_id: string;
  strategy_version: string;
  strategy_label: string;
  strength: SignalStrength | null;
  market_regime: string;
  reasons: string[];
  supporting_features: Record<string, unknown>;
  invalidating_conditions: string[];
  status: SignalStatus;
  generated_at: string;
  created_at: string;
}

export interface EvaluateSignalResponse extends SignalResponse {
  was_newly_created: boolean;
}

export function evaluateSignal(
  symbol: string,
  interval: SupportedInterval = "1h",
): Promise<EvaluateSignalResponse> {
  return apiFetch<EvaluateSignalResponse>(
    `/api/v1/signals/evaluate/${encodeURIComponent(symbol)}?interval=${interval}`,
    { method: "POST" },
  );
}

export function listSignals(options?: {
  symbol?: string;
  strategyId?: string;
  status?: SignalStatus;
  interval?: SupportedInterval;
  limit?: number;
}): Promise<SignalResponse[]> {
  const params = new URLSearchParams();
  if (options?.symbol) params.set("symbol", options.symbol);
  if (options?.strategyId) params.set("strategy_id", options.strategyId);
  if (options?.status) params.set("status", options.status);
  if (options?.interval) params.set("interval", options.interval);
  if (options?.limit) params.set("limit", String(options.limit));
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<SignalResponse[]>(`/api/v1/signals${query}`);
}

export function getSignal(id: string): Promise<SignalResponse> {
  return apiFetch<SignalResponse>(`/api/v1/signals/${encodeURIComponent(id)}`);
}
