import { apiFetch } from "@/lib/api";

// Mirrors apps/api/app/schemas/ai.py — kept in sync by hand until the
// generated-client tooling from docs/api.md §4 lands.

export type AISuggestedAction = "BUY" | "SELL" | "HOLD" | "NO_ACTION";
export type AIUncertainty = "LOW" | "MEDIUM" | "HIGH";

export interface AIAnalysis {
  id: string;
  signal_id: string;
  symbol: string;
  interval: string;
  provider: string;
  model: string;
  prompt_version: string;
  market_summary: string;
  thesis: string;
  supporting_evidence: string[];
  contradicting_evidence: string[];
  risks: string[];
  invalidating_conditions: string[];
  suggested_action: AISuggestedAction;
  action_rationale: string;
  uncertainty: AIUncertainty;
  model_metadata: Record<string, unknown>;
  generated_at: string;
  created_at: string;
}

export interface AIStatus {
  configured: boolean;
  available: boolean;
  provider: string;
  model: string;
}

export function getAIStatus(): Promise<AIStatus> {
  return apiFetch<AIStatus>("/api/v1/ai/status");
}

export function analyzeSignal(signalId: string): Promise<AIAnalysis> {
  return apiFetch<AIAnalysis>(`/api/v1/ai/analyze/${encodeURIComponent(signalId)}`, {
    method: "POST",
  });
}

export function listAIAnalyses(options?: {
  symbol?: string;
  signalId?: string;
  limit?: number;
}): Promise<AIAnalysis[]> {
  const params = new URLSearchParams();
  if (options?.symbol) params.set("symbol", options.symbol);
  if (options?.signalId) params.set("signal_id", options.signalId);
  if (options?.limit) params.set("limit", String(options.limit));
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<AIAnalysis[]>(`/api/v1/ai/analyses${query}`);
}

export function getAIAnalysis(id: string): Promise<AIAnalysis> {
  return apiFetch<AIAnalysis>(`/api/v1/ai/analyses/${encodeURIComponent(id)}`);
}

export function listAIAnalysesForSignal(signalId: string): Promise<AIAnalysis[]> {
  return apiFetch<AIAnalysis[]>(`/api/v1/ai/signals/${encodeURIComponent(signalId)}`);
}
