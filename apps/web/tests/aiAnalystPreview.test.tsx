import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AIAnalystPreview } from "@/components/market/AIAnalystPreview";

const AI_STATUS_AVAILABLE = { configured: true, available: true, provider: "anthropic", model: "claude-sonnet-5" };
const AI_STATUS_UNAVAILABLE = {
  configured: false,
  available: false,
  provider: "anthropic",
  model: "claude-sonnet-5",
};

const AI_ANALYSIS = {
  id: "a1",
  signal_id: "s1",
  symbol: "AAPL",
  interval: "1h",
  provider: "anthropic",
  model: "claude-sonnet-5",
  prompt_version: "1.0.0",
  market_summary: "AAPL is trading above its 21-day EMA with rising volume.",
  thesis: "The evidence suggests continuing bullish momentum, though confirmation is limited.",
  supporting_evidence: [],
  contradicting_evidence: [],
  risks: [],
  invalidating_conditions: [],
  suggested_action: "BUY",
  action_rationale: "Trend and momentum evidence align with the signal's direction.",
  uncertainty: "MEDIUM",
  model_metadata: {},
  generated_at: "2026-01-01T00:01:00Z",
  created_at: "2026-01-01T00:01:00Z",
};

const SIGNAL = {
  id: "s1",
  symbol: "AAPL",
  interval: "1h",
  signal: "BUY",
  strategy_id: "trend_momentum",
  strategy_version: "1.0.0",
  strategy_label: "trend_momentum_v1",
  strength: "STRONG",
  market_regime: "BULLISH",
  reasons: [],
  supporting_features: {},
  invalidating_conditions: [],
  status: "RISK_APPROVED",
  generated_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

describe("AIAnalystPreview", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows an unavailable message when the AI provider isn't configured", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/ai/status")) return Promise.resolve(jsonResponse(AI_STATUS_UNAVAILABLE));
      return Promise.resolve(jsonResponse({}, false, 500));
    });

    render(<AIAnalystPreview />);

    await waitFor(() =>
      expect(
        screen.getByText("AI Analyst unavailable — configure the Claude provider to enable analysis."),
      ).toBeInTheDocument(),
    );
  });

  it("shows an empty state when the provider is configured but no analyses exist yet", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/ai/status")) return Promise.resolve(jsonResponse(AI_STATUS_AVAILABLE));
      if (url.includes("/ai/analyses")) return Promise.resolve(jsonResponse([]));
      return Promise.resolve(jsonResponse({}, false, 500));
    });

    render(<AIAnalystPreview />);

    await waitFor(() => expect(screen.getByText(/No AI analyses yet/)).toBeInTheDocument());
  });

  it("shows the latest analysis's thesis, action, uncertainty, signal, and risk decision", async () => {
    const riskEvaluation = {
      id: "re1",
      signal_id: "s1",
      symbol: "AAPL",
      policy_id: "p1",
      policy_version: 1,
      decision: "APPROVED",
      reasons: [],
      checks: [],
      calculated_position_size: "10",
      entry_price: "175.00",
      stop_loss_price: "171.50",
      take_profit_price: "182.00",
      position_value: "1750.00",
      portfolio_snapshot: {},
      evaluated_at: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    };

    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/ai/status")) return Promise.resolve(jsonResponse(AI_STATUS_AVAILABLE));
      if (url.includes("/ai/analyses")) return Promise.resolve(jsonResponse([AI_ANALYSIS]));
      if (url.includes("/risk/evaluations")) return Promise.resolve(jsonResponse([riskEvaluation]));
      if (url.includes("/signals/")) return Promise.resolve(jsonResponse(SIGNAL));
      return Promise.resolve(jsonResponse({}, false, 500));
    });

    render(<AIAnalystPreview />);

    await waitFor(() => expect(screen.getByText(/continuing bullish momentum/)).toBeInTheDocument());
    // "BUY" appears twice: the AI's own suggested action badge, and the
    // deterministic signal direction shown alongside it (Step 22).
    expect(screen.getAllByText("BUY").length).toBe(2);
    expect(screen.getByText("MEDIUM")).toBeInTheDocument();
    expect(screen.getByText("APPROVED")).toBeInTheDocument();
    // No fabricated numeric confidence anywhere in the preview.
    expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument();
  });

  it("shows an error state when the status request fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ error: { code: "internal_error", message: "ai status unavailable" } }, false, 500),
    );

    render(<AIAnalystPreview />);

    await waitFor(() => expect(screen.getByText(/ai status unavailable/)).toBeInTheDocument());
  });
});
