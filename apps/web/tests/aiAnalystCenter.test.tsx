import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AIAnalystCenter } from "@/components/market/AIAnalystCenter";

const ASSETS_RESPONSE = [
  {
    id: "1",
    symbol: "AAPL",
    name: "Apple Inc.",
    asset_type: "equity",
    exchange: "NASDAQ",
    currency: "USD",
    active: true,
    created_at: "",
    updated_at: "",
  },
];

const SIGNAL_RESPONSE = {
  id: "s1",
  symbol: "AAPL",
  interval: "1h",
  signal: "BUY",
  strategy_id: "trend_momentum",
  strategy_version: "1.0.0",
  strategy_label: "trend_momentum_v1",
  strength: "STRONG",
  market_regime: "BULLISH",
  reasons: ["Detected market regime is BULLISH"],
  supporting_features: { rsi14: 55.0 },
  invalidating_conditions: ["Price loses EMA21 support"],
  status: "CANDIDATE",
  generated_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  was_newly_created: true,
};

const AI_STATUS_AVAILABLE = { configured: true, available: true, provider: "anthropic", model: "claude-sonnet-5" };
const AI_STATUS_UNAVAILABLE = { configured: false, available: false, provider: "anthropic", model: "claude-sonnet-5" };

const AI_ANALYSIS_RESPONSE = {
  id: "a1",
  signal_id: "s1",
  symbol: "AAPL",
  interval: "1h",
  provider: "anthropic",
  model: "claude-sonnet-5",
  prompt_version: "1.0.0",
  market_summary: "AAPL is trading above its 21-day EMA with rising volume.",
  thesis: "The evidence suggests continuing bullish momentum, though confirmation is limited.",
  supporting_evidence: ["Price is above EMA21"],
  contradicting_evidence: ["RSI is approaching overbought territory"],
  risks: ["A reversal below EMA21 would weaken the thesis"],
  invalidating_conditions: ["Price closes below EMA21"],
  suggested_action: "BUY",
  action_rationale: "Trend and momentum evidence align with the signal's direction.",
  uncertainty: "MEDIUM",
  model_metadata: {},
  generated_at: "2026-01-01T00:01:00Z",
  created_at: "2026-01-01T00:01:00Z",
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

function baseRouter(overrides: Record<string, () => Promise<Response>>) {
  return (url: string, init?: RequestInit) => {
    for (const [match, handler] of Object.entries(overrides)) {
      if (url.includes(match)) return handler();
    }
    if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
    if (url.includes("/ai/status")) return Promise.resolve(jsonResponse(AI_STATUS_AVAILABLE));
    if (url.includes("/ai/analyses")) return Promise.resolve(jsonResponse([]));
    if (url.includes("/risk/evaluate/") && init?.method === "POST") {
      return Promise.resolve(jsonResponse({ error: { code: "not_found", message: "n/a" } }, false, 404));
    }
    return Promise.resolve(jsonResponse(SIGNAL_RESPONSE));
  };
}

describe("AIAnalystCenter", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows an unavailable message and no Run AI Analysis button when the provider isn't configured", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(
      baseRouter({ "/ai/status": () => Promise.resolve(jsonResponse(AI_STATUS_UNAVAILABLE)) }),
    );

    render(<AIAnalystCenter />);

    await waitFor(() =>
      expect(
        screen.getByText("AI Analyst unavailable — configure the Claude provider to enable analysis."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /run ai analysis/i })).not.toBeInTheDocument();
  });

  it("runs an AI analysis and shows the thesis, action, and uncertainty — with no fabricated confidence", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(
      baseRouter({
        "/ai/analyze/": () => Promise.resolve(jsonResponse(AI_ANALYSIS_RESPONSE)),
      }),
    );

    render(<AIAnalystCenter />);
    await waitFor(() => expect(screen.getByRole("button", { name: /run ai analysis/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /run ai analysis/i }));

    await waitFor(() =>
      expect(screen.getByText(/continuing bullish momentum/)).toBeInTheDocument(),
    );
    expect(screen.getByText("MEDIUM uncertainty")).toBeInTheDocument();
    expect(screen.getByText(/Price is above EMA21/)).toBeInTheDocument();
    expect(screen.getByText(/RSI is approaching overbought territory/)).toBeInTheDocument();
    // Step 39: no fabricated numeric confidence anywhere on screen.
    expect(screen.queryByText(/\d+%\s*confidence/i)).not.toBeInTheDocument();
    // No disagreement banner — the AI agrees with the deterministic BUY signal.
    expect(screen.queryByText(/Analysis disagreement/)).not.toBeInTheDocument();
  });

  it("shows an error message when the AI analysis request fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(
      baseRouter({
        "/ai/analyze/": () =>
          Promise.resolve(
            jsonResponse(
              { error: { code: "provider_error", message: "Claude request timed out" } },
              false,
              503,
            ),
          ),
      }),
    );

    render(<AIAnalystCenter />);
    await waitFor(() => expect(screen.getByRole("button", { name: /run ai analysis/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /run ai analysis/i }));

    await waitFor(() => expect(screen.getByText(/Claude request timed out/)).toBeInTheDocument());
  });

  it("shows an explicit disagreement status when the AI suggestion differs from the deterministic signal", async () => {
    const disagreeing = { ...AI_ANALYSIS_RESPONSE, suggested_action: "SELL" };
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(
      baseRouter({ "/ai/analyze/": () => Promise.resolve(jsonResponse(disagreeing)) }),
    );

    render(<AIAnalystCenter />);
    await waitFor(() => expect(screen.getByRole("button", { name: /run ai analysis/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /run ai analysis/i }));

    await waitFor(() => expect(screen.getByText(/STATUS: Analysis disagreement/)).toBeInTheDocument());
    // Disagreement is stated plainly, never implying either side "wins".
    expect(screen.getByText(/Neither overrides the other/)).toBeInTheDocument();
  });

  it("shows the AI analysis alongside a risk approval and a filled paper trade", async () => {
    const evaluationResponse = {
      id: "re1",
      signal_id: "s1",
      symbol: "AAPL",
      policy_id: "p1",
      policy_version: 1,
      decision: "APPROVED",
      reasons: [],
      checks: [],
      calculated_position_size: "10.0000000000",
      entry_price: "175.00000000",
      stop_loss_price: "171.50000000",
      take_profit_price: "182.00000000",
      position_value: "1750.00000000",
      portfolio_snapshot: {},
      evaluated_at: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    };
    const orderResponse = {
      id: "order1",
      signal_id: "s1",
      symbol: "AAPL",
      side: "BUY",
      order_type: "MARKET",
      quantity: "10.0000000000",
      requested_price: "175.00000000",
      status: "FILLED",
      filled_quantity: "10.0000000000",
      average_fill_price: "175.00000000",
      rejection_reason: null,
      created_at: "2026-01-01T00:00:00Z",
      submitted_at: "2026-01-01T00:00:00Z",
      filled_at: "2026-01-01T00:00:01Z",
      cancelled_at: null,
    };

    (fetch as ReturnType<typeof vi.fn>).mockImplementation(
      baseRouter({
        "/ai/analyze/": () => Promise.resolve(jsonResponse(AI_ANALYSIS_RESPONSE)),
        "/risk/evaluate/": () => Promise.resolve(jsonResponse(evaluationResponse)),
        "/paper/execute/": () => Promise.resolve(jsonResponse(orderResponse)),
      }),
    );

    render(<AIAnalystCenter />);
    await waitFor(() => expect(screen.getByRole("button", { name: /run ai analysis/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /run ai analysis/i }));
    await waitFor(() => expect(screen.getByText(/continuing bullish momentum/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /run risk review/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /execute paper order/i })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: /execute paper order/i }));
    await waitFor(() => expect(screen.getByText("Simulated Fill · Position Open")).toBeInTheDocument());

    // All three layers visible together: the AI's own opinion, the
    // deterministic signal's outcome, and the AI analyst never claiming
    // to have done any of the risk or execution work itself.
    expect(screen.getByText(/continuing bullish momentum/)).toBeInTheDocument();
    expect(screen.getByText(/Analytical interpretation only/)).toBeInTheDocument();
  });

  it("shows a loading state for the analysis history before it resolves", () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/ai/analyses")) return new Promise(() => {});
      return baseRouter({})(url);
    });

    render(<AIAnalystCenter />);
    expect(screen.getByTestId("ai-analyst-history-loading")).toBeInTheDocument();
  });

  it("shows an empty state when there is no analysis history", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(baseRouter({}));

    render(<AIAnalystCenter />);

    await waitFor(() =>
      expect(screen.getByText(/No AI analyses yet/)).toBeInTheDocument(),
    );
  });

  it("shows an error state when the analysis history fails to load", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/ai/analyses")) {
        return Promise.resolve(
          jsonResponse({ error: { code: "internal_error", message: "ai history unavailable" } }, false, 500),
        );
      }
      return baseRouter({})(url);
    });

    render(<AIAnalystCenter />);

    await waitFor(() => expect(screen.getByText(/ai history unavailable/)).toBeInTheDocument());
  });

  it("lists recent analyses with symbol, suggested action, and uncertainty", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/ai/analyses")) return Promise.resolve(jsonResponse([AI_ANALYSIS_RESPONSE]));
      return baseRouter({})(url);
    });

    render(<AIAnalystCenter />);

    await waitFor(() => expect(screen.getByText("Recent AI Analyses")).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByText(/continuing bullish momentum/)).toBeInTheDocument(),
    );
  });
});
