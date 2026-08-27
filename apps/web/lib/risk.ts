import { apiFetch } from "@/lib/api";

// Mirrors apps/api/app/schemas/risk.py — kept in sync by hand until the
// generated-client tooling from docs/api.md §4 lands. Decimal-backed
// fields are typed `string` (Pydantic v2's default JSON encoding for
// `Decimal`), matching the convention already used in lib/marketData.ts
// for OHLCV fields — parse with `Number(...)` at the point of use.

export type RiskDecision = "APPROVED" | "REJECTED";

export interface RiskPolicy {
  id: string;
  name: string;
  version: number;
  enabled: boolean;
  is_active: boolean;
  max_position_size_pct: string;
  max_portfolio_exposure_pct: string;
  max_daily_loss_pct: string;
  max_drawdown_pct: string;
  stop_loss_pct: string;
  take_profit_pct: string;
  risk_per_trade_pct: string;
  max_concurrent_positions: number;
  cooldown_after_loss_minutes: number;
  created_at: string;
  updated_at: string;
}

export interface RiskPolicyUpdateRequest {
  enabled: boolean;
  max_position_size_pct: string;
  max_portfolio_exposure_pct: string;
  max_daily_loss_pct: string;
  max_drawdown_pct: string;
  stop_loss_pct: string;
  take_profit_pct: string;
  risk_per_trade_pct: string;
  max_concurrent_positions: number;
  cooldown_after_loss_minutes: number;
}

export interface RiskCheck {
  name: string;
  passed: boolean;
  detail: string;
  skipped: boolean;
}

export interface RiskEvaluation {
  id: string;
  signal_id: string;
  symbol: string;
  policy_id: string;
  policy_version: number;
  decision: RiskDecision;
  reasons: string[];
  checks: RiskCheck[];
  calculated_position_size: string | null;
  entry_price: string | null;
  stop_loss_price: string | null;
  take_profit_price: string | null;
  position_value: string | null;
  portfolio_snapshot: Record<string, unknown>;
  evaluated_at: string;
  created_at: string;
}

export interface PortfolioState {
  equity: string;
  cash: string;
  high_water_mark: string;
  drawdown_pct: string;
  open_position_count: number;
  open_position_value: string;
  available_exposure_value: string;
  realized_pl_today: string;
  as_of: string;
}

export interface RiskSummary {
  portfolio: PortfolioState;
  policy: RiskPolicy;
}

export function getRiskSummary(): Promise<RiskSummary> {
  return apiFetch<RiskSummary>("/api/v1/risk");
}

export function getRiskRules(): Promise<RiskPolicy> {
  return apiFetch<RiskPolicy>("/api/v1/risk/rules");
}

export function updateRiskRules(body: RiskPolicyUpdateRequest): Promise<RiskPolicy> {
  return apiFetch<RiskPolicy>("/api/v1/risk/rules", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function evaluateRisk(signalId: string): Promise<RiskEvaluation> {
  return apiFetch<RiskEvaluation>(`/api/v1/risk/evaluate/${encodeURIComponent(signalId)}`, {
    method: "POST",
  });
}

export function listRiskEvaluations(options?: {
  signalId?: string;
  decision?: RiskDecision;
  symbol?: string;
  limit?: number;
}): Promise<RiskEvaluation[]> {
  const params = new URLSearchParams();
  if (options?.signalId) params.set("signal_id", options.signalId);
  if (options?.decision) params.set("decision", options.decision);
  if (options?.symbol) params.set("symbol", options.symbol);
  if (options?.limit) params.set("limit", String(options.limit));
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<RiskEvaluation[]>(`/api/v1/risk/evaluations${query}`);
}

export function getRiskEvaluation(id: string): Promise<RiskEvaluation> {
  return apiFetch<RiskEvaluation>(`/api/v1/risk/evaluations/${encodeURIComponent(id)}`);
}
