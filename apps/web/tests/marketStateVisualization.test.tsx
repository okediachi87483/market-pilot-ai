import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MarketStateVisualization } from "@/components/market/MarketStateVisualization";

const ANALYSIS_RESPONSE = {
  symbol: "AAPL",
  asset_id: "1",
  interval: "1d",
  source: "mock",
  is_mock: true,
  calculated_at: "2024-06-01T00:00:00Z",
  candle_count: 200,
  price: { timestamp: "2024-06-01T00:00:00Z", close: 190 },
  indicators: {
    trend: { sma20: 188, sma50: 185, sma200: 180, ema9: 189, ema21: 187, ema50: 184, ema200: 179 },
    momentum: { rsi14: 58, macd: 0.4, macd_signal: 0.2, macd_histogram: 0.2, stochastic_k: 65, stochastic_d: 60 },
    volatility: { atr14: 1.8, bollinger_upper: 195, bollinger_middle: 188, bollinger_lower: 181, bollinger_width: 0.07 },
    volume: { volume: 1000000, volume_sma: 900000, relative_volume: 1.11 },
  },
  features: {
    price_above_ema21: true, ema9_above_ema21: true, ema21_above_ema50: true, ema50_above_ema200: true,
    trend_alignment_score: 2, trend_alignment_label: "strong", trend_direction: "bullish",
    rsi_state: "neutral", macd_state: "bullish", volume_state: "normal", volatility_state: "normal",
  },
  regime: { regime: "BULLISH", reasons: ["trend checks lean bullish with strong alignment"] },
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

describe("MarketStateVisualization", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the detected regime from the API, never BUY/SELL language", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(ANALYSIS_RESPONSE));

    render(<MarketStateVisualization symbol="AAPL" />);

    await waitFor(() => expect(screen.getByText("BULLISH")).toBeInTheDocument());
    expect(screen.getByText(/not a recommendation/i)).toBeInTheDocument();
    expect(screen.queryByText(/\bBUY\b/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\bSELL\b/i)).not.toBeInTheDocument();
  });

  it("shows an error state when the API call fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ error: { code: "internal_error", message: "boom" } }, false, 500),
    );

    render(<MarketStateVisualization symbol="AAPL" />);

    await waitFor(() => expect(screen.getByText(/boom/)).toBeInTheDocument());
  });
});
