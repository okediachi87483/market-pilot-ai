import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandCenter } from "@/components/market/CommandCenter";

const ASSETS_RESPONSE = [
  { id: "1", symbol: "AAPL", name: "Apple Inc.", asset_type: "equity", exchange: "NASDAQ", currency: "USD", active: true, created_at: "", updated_at: "" },
];

const AI_STATUS_AVAILABLE = { configured: true, available: true, provider: "anthropic", model: "claude-sonnet-5" };
const AI_STATUS_UNAVAILABLE = { configured: false, available: false, provider: "anthropic", model: "claude-sonnet-5" };

function baseSnapshot(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: "2026-01-01T00:00:00Z",
    system_health: {
      api: "ok",
      database: "ok",
      redis: "ok",
      market_data: "ok",
      ai: AI_STATUS_AVAILABLE,
    },
    market: {
      symbol: "AAPL",
      asset_id: "asset-1",
      interval: "1d",
      source: "mock",
      is_mock: true,
      calculated_at: "2026-01-01T00:00:00Z",
      candle_count: 200,
      price: { timestamp: "2026-01-01T00:00:00Z", close: 190.5 },
      features: {
        price_above_ema21: true,
        ema9_above_ema21: true,
        ema21_above_ema50: true,
        ema50_above_ema200: true,
        trend_alignment_score: 2,
        trend_alignment_label: "strong",
        trend_direction: "bullish",
        rsi_state: "neutral",
        macd_state: "bullish",
        volume_state: "normal",
        volatility_state: "normal",
      },
      regime: { regime: "BULLISH", reasons: ["trend checks lean bullish with strong alignment"] },
    },
    watchlist: [
      { symbol: "AAPL", close: "190.50", change_pct: "1.20", timestamp: "2026-01-01T00:00:00Z", source: "mock", is_mock: true },
      { symbol: "MSFT", close: "400.00", change_pct: "-0.50", timestamp: "2026-01-01T00:00:00Z", source: "mock", is_mock: true },
    ],
    signals: [
      {
        id: "s1",
        symbol: "AAPL",
        interval: "1h",
        signal: "BUY",
        strategy_id: "trend_momentum",
        strategy_version: "1.0.0",
        strategy_label: "trend_momentum_v1",
        strength: "STRONG",
        market_regime: "BULLISH",
        reasons: ["trend confirmed"],
        supporting_features: {},
        invalidating_conditions: [],
        status: "RISK_APPROVED",
        generated_at: "2026-01-01T00:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    ai_analyses: [
      {
        id: "a1",
        signal_id: "s1",
        symbol: "AAPL",
        interval: "1h",
        provider: "anthropic",
        model: "claude-sonnet-5",
        prompt_version: "1.0.0",
        market_summary: "AAPL is trading above its 21-day EMA.",
        thesis: "The evidence suggests continuing bullish momentum, though confirmation is limited.",
        supporting_evidence: [],
        contradicting_evidence: [],
        risks: [],
        invalidating_conditions: [],
        suggested_action: "BUY",
        action_rationale: "Trend aligns with the signal.",
        uncertainty: "MEDIUM",
        model_metadata: {},
        generated_at: "2026-01-01T00:01:00Z",
        created_at: "2026-01-01T00:01:00Z",
      },
    ],
    risk: {
      portfolio: {
        equity: "100000",
        cash: "80000",
        high_water_mark: "100500",
        drawdown_pct: "0.5",
        open_position_count: 1,
        open_position_value: "20000",
        available_exposure_value: "30000",
        realized_pl_today: "150",
        as_of: "2026-01-01T00:00:00Z",
      },
      policy: {
        id: "p1",
        name: "default",
        version: 1,
        enabled: true,
        is_active: true,
        max_position_size_pct: "5.00",
        max_portfolio_exposure_pct: "50.00",
        max_daily_loss_pct: "3.00",
        max_drawdown_pct: "15.00",
        stop_loss_pct: "2.00",
        take_profit_pct: "4.00",
        risk_per_trade_pct: "1.00",
        max_concurrent_positions: 5,
        cooldown_after_loss_minutes: 60,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    },
    portfolio: {
      starting_equity: "100000",
      cash: "80000",
      market_value: "20000",
      equity: "100000",
      realized_pnl_total: "150",
      unrealized_pnl: "50",
      total_pnl: "200",
      daily_pnl: "150",
      peak_equity: "100500",
      drawdown_pct: "0.5",
      open_position_count: 1,
      as_of: "2026-01-01T00:00:00Z",
    },
    positions: [
      {
        id: "pos1",
        symbol: "AAPL",
        quantity: "10",
        avg_entry_price: "180.00",
        current_price: "190.50",
        market_value: "1905.00",
        unrealized_pnl: "105.00",
        realized_pnl: "0",
        status: "OPEN",
        opened_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        closed_at: null,
      },
    ],
    recent_fills: [],
    recent_activity: [
      {
        type: "SIGNAL_GENERATED",
        timestamp: "2026-01-01T00:00:00Z",
        symbol: "AAPL",
        summary: "BUY signal generated (trend_momentum)",
        signal_id: "s1",
      },
    ],
    ...overrides,
  };
}

const INDICATOR_SERIES_RESPONSE = {
  symbol: "AAPL",
  asset_id: "asset-1",
  interval: "1d",
  source: "mock",
  is_mock: true,
  start: "2025-12-01T00:00:00Z",
  end: "2026-01-01T00:00:00Z",
  count: 1,
  points: [
    {
      timestamp: "2026-01-01T00:00:00Z",
      close: 190.5,
      sma20: 188,
      sma50: null,
      sma200: null,
      ema9: 189,
      ema21: 187,
      ema50: null,
      ema200: null,
      rsi14: 55,
      macd: null,
      macd_signal: null,
      macd_histogram: null,
      stochastic_k: null,
      stochastic_d: null,
      atr14: null,
      bollinger_upper: 195,
      bollinger_middle: 188,
      bollinger_lower: 181,
      bollinger_width: null,
      volume: 1000000,
      volume_sma: null,
      relative_volume: null,
    },
  ],
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

function router(snapshot: unknown) {
  return (url: string) => {
    if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
    if (url.includes("/command-center")) return Promise.resolve(jsonResponse(snapshot));
    if (url.includes("/indicators")) return Promise.resolve(jsonResponse(INDICATOR_SERIES_RESPONSE));
    return Promise.resolve(jsonResponse({}, false, 404));
  };
}

describe("CommandCenter", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a loading state before the snapshot resolves", () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
      return new Promise(() => {}); // never resolves
    });

    render(<CommandCenter />);
    expect(screen.getAllByRole("status", { hidden: true }).length).toBeGreaterThan(0);
  });

  it("renders market overview, watchlist, signals, risk, and portfolio from one snapshot", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(router(baseSnapshot()));

    render(<CommandCenter />);

    await waitFor(() => expect(screen.getAllByText("190.50").length).toBeGreaterThan(0));
    expect(screen.getByText("Market Overview")).toBeInTheDocument();
    expect(screen.getByText("Watchlist")).toBeInTheDocument();
    expect(screen.getByText("Active Signals")).toBeInTheDocument();
    expect(screen.getByText("Risk Overview")).toBeInTheDocument();
    expect(screen.getByText("Paper Portfolio")).toBeInTheDocument();
    expect(screen.getByText("Recent Activity")).toBeInTheDocument();
    expect(screen.getByText("Paper Trading")).toBeInTheDocument();
  });

  it("shows an error state when the snapshot request fails entirely", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
      if (url.includes("/command-center")) {
        return Promise.resolve(
          jsonResponse({ error: { code: "not_found", message: "unknown asset symbol" } }, false, 404),
        );
      }
      return Promise.resolve(jsonResponse(INDICATOR_SERIES_RESPONSE));
    });

    render(<CommandCenter />);

    await waitFor(() => expect(screen.getByText(/unknown asset symbol/)).toBeInTheDocument());
  });

  it("shows an empty state when there are no active signals", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(router(baseSnapshot({ signals: [] })));

    render(<CommandCenter />);

    await waitFor(() =>
      expect(screen.getByText(/No signals yet/)).toBeInTheDocument(),
    );
  });

  it("shows an empty state when there is no recent activity", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(
      router(baseSnapshot({ recent_activity: [] })),
    );

    render(<CommandCenter />);

    await waitFor(() => expect(screen.getByText(/No activity yet/)).toBeInTheDocument());
  });

  it("shows the AI Analyst unavailable message when the provider isn't configured", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(
      router(
        baseSnapshot({
          system_health: {
            api: "ok",
            database: "ok",
            redis: "ok",
            market_data: "ok",
            ai: AI_STATUS_UNAVAILABLE,
          },
          ai_analyses: [],
        }),
      ),
    );

    render(<CommandCenter />);

    await waitFor(() =>
      expect(
        screen.getByText("AI Analyst unavailable — configure the Claude provider to enable analysis."),
      ).toBeInTheDocument(),
    );
    // No fabricated AI commentary anywhere.
    expect(screen.queryByText(/thesis/i)).not.toBeInTheDocument();
  });

  it("shows the AI Analyst thesis and suggested action when analyses exist", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(router(baseSnapshot()));

    render(<CommandCenter />);

    await waitFor(() =>
      expect(screen.getByText(/continuing bullish momentum/)).toBeInTheDocument(),
    );
    expect(screen.getByText("MEDIUM")).toBeInTheDocument();
    // No fabricated numeric confidence anywhere on screen.
    expect(screen.queryByText(/\d+%\s*confidence/i)).not.toBeInTheDocument();
  });

  it("shows an explicit disagreement banner when the AI suggestion differs from the signal", async () => {
    const disagreeing = baseSnapshot({
      ai_analyses: [
        {
          ...baseSnapshot().ai_analyses[0],
          suggested_action: "SELL",
        },
      ],
    });
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(router(disagreeing));

    render(<CommandCenter />);

    await waitFor(() =>
      expect(screen.getByText(/ANALYSIS DISAGREEMENT/)).toBeInTheDocument(),
    );
  });

  it("shows an empty state when there are no open positions", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(router(baseSnapshot({ positions: [] })));

    render(<CommandCenter />);

    await waitFor(() => expect(screen.getByText("No open positions.")).toBeInTheDocument());
  });

  it("renders system health for API, database, redis, market data, and AI provider", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(router(baseSnapshot()));

    render(<CommandCenter />);

    await waitFor(() => expect(screen.getByRole("status", { name: /system health/i })).toBeInTheDocument());
    const health = screen.getByRole("status", { name: /system health/i });
    expect(health).toHaveTextContent("API");
    expect(health).toHaveTextContent("Database");
    expect(health).toHaveTextContent("Redis");
    expect(health).toHaveTextContent("Market Data");
    expect(health).toHaveTextContent("AI Provider");
  });

  it("marks a down dependency in system health", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(
      router(baseSnapshot({ system_health: { api: "ok", database: "down", redis: "ok", market_data: "ok", ai: AI_STATUS_AVAILABLE } })),
    );

    render(<CommandCenter />);

    await waitFor(() => {
      const health = screen.getByRole("status", { name: /system health/i });
      expect(health).toHaveTextContent("DOWN");
    });
  });
});
