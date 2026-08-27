import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MarketExplorer } from "@/components/market/MarketExplorer";

const QUOTE_RESPONSE = {
  symbol: "AAPL",
  asset_id: "11111111-1111-1111-1111-111111111111",
  interval: "1m",
  source: "mock",
  is_mock: true,
  bar: {
    timestamp: "2024-06-01T12:00:00Z",
    open: "190.00000000",
    high: "191.50000000",
    low: "189.20000000",
    close: "191.00000000",
    volume: "1200000.0000000000",
  },
};

const INDICATOR_SERIES_RESPONSE = {
  symbol: "AAPL",
  asset_id: "11111111-1111-1111-1111-111111111111",
  interval: "1h",
  source: "mock",
  is_mock: true,
  start: "2024-06-01T00:00:00Z",
  end: "2024-06-01T01:00:00Z",
  count: 2,
  points: [
    {
      timestamp: "2024-06-01T00:00:00Z", close: 190.5, sma20: null, sma50: null, sma200: null,
      ema9: null, ema21: null, ema50: null, ema200: null, rsi14: null, macd: null,
      macd_signal: null, macd_histogram: null, stochastic_k: null, stochastic_d: null,
      atr14: null, bollinger_upper: null, bollinger_middle: null, bollinger_lower: null,
      bollinger_width: null, volume: 1000, volume_sma: null, relative_volume: null,
    },
    {
      timestamp: "2024-06-01T01:00:00Z", close: 191.5, sma20: null, sma50: null, sma200: null,
      ema9: null, ema21: null, ema50: null, ema200: null, rsi14: null, macd: null,
      macd_signal: null, macd_histogram: null, stochastic_k: null, stochastic_d: null,
      atr14: null, bollinger_upper: null, bollinger_middle: null, bollinger_lower: null,
      bollinger_width: null, volume: 1100, volume_sma: null, relative_volume: null,
    },
  ],
};

const ANALYSIS_RESPONSE = {
  symbol: "AAPL",
  asset_id: "11111111-1111-1111-1111-111111111111",
  interval: "1h",
  source: "mock",
  is_mock: true,
  calculated_at: "2024-06-01T01:00:00Z",
  candle_count: 60,
  price: { timestamp: "2024-06-01T01:00:00Z", close: 191.5 },
  indicators: {
    trend: { sma20: 190, sma50: null, sma200: null, ema9: 191, ema21: 190.5, ema50: null, ema200: null },
    momentum: { rsi14: 55, macd: 0.2, macd_signal: 0.1, macd_histogram: 0.1, stochastic_k: 60, stochastic_d: 58 },
    volatility: { atr14: 1.2, bollinger_upper: 193, bollinger_middle: 190, bollinger_lower: 187, bollinger_width: 0.03 },
    volume: { volume: 1100, volume_sma: 1000, relative_volume: 1.1 },
  },
  features: {
    price_above_ema21: true, ema9_above_ema21: true, ema21_above_ema50: null, ema50_above_ema200: null,
    trend_alignment_score: 1, trend_alignment_label: "partial", trend_direction: "bullish",
    rsi_state: "neutral", macd_state: "bullish", volume_state: "normal", volatility_state: "normal",
  },
  regime: { regime: "BULLISH", reasons: ["trend checks lean bullish with partial alignment"] },
};

const ASSETS_RESPONSE = [
  { id: "1", symbol: "AAPL", name: "Apple Inc.", asset_type: "equity", exchange: "NASDAQ", currency: "USD", active: true, created_at: "", updated_at: "" },
];

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => body,
  } as Response;
}

function routeFetch(url: string) {
  if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
  if (url.includes("/indicators")) return Promise.resolve(jsonResponse(INDICATOR_SERIES_RESPONSE));
  if (url.includes("/analysis/")) return Promise.resolve(jsonResponse(ANALYSIS_RESPONSE));
  if (url.includes("/market/")) return Promise.resolve(jsonResponse(QUOTE_RESPONSE));
  return Promise.resolve(jsonResponse({ error: { code: "not_found", message: "unhandled route" } }, false, 404));
}

describe("MarketExplorer", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a loading state before data arrives", () => {
    (fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {})); // never resolves
    render(<MarketExplorer />);
    expect(screen.getByTestId("market-explorer-loading")).toBeInTheDocument();
  });

  it("renders quote and analysis data from the API, with a mock source label", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => routeFetch(url));

    render(<MarketExplorer />);

    await waitFor(() => expect(screen.getByText("191.00000000")).toBeInTheDocument());
    expect(screen.getByText(/SOURCE: MOCK/)).toBeInTheDocument();
    expect(screen.queryByTestId("market-explorer-loading")).not.toBeInTheDocument();
    // The technical-analysis panel renders from the same real API.
    await waitFor(() => expect(screen.getByText("BULLISH")).toBeInTheDocument());
  });

  it("shows an error state when the quote/series API call fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
      return Promise.resolve(
        jsonResponse({ error: { code: "not_found", message: "unknown asset symbol" } }, false, 404),
      );
    });

    render(<MarketExplorer />);

    await waitFor(() => expect(screen.getByText(/unknown asset symbol/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
