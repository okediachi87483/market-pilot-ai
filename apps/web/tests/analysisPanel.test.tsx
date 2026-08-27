import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AnalysisPanel } from "@/components/market/AnalysisPanel";

const ANALYSIS_RESPONSE = {
  symbol: "NVDA",
  asset_id: "1",
  interval: "1h",
  source: "mock",
  is_mock: true,
  calculated_at: "2024-06-01T01:00:00Z",
  candle_count: 120,
  price: { timestamp: "2024-06-01T01:00:00Z", close: 128.44 },
  indicators: {
    trend: { sma20: 125, sma50: 120, sma200: null, ema9: 127, ema21: 126, ema50: 122, ema200: null },
    momentum: { rsi14: 62, macd: 0.5, macd_signal: 0.3, macd_histogram: 0.2, stochastic_k: 70, stochastic_d: 65 },
    volatility: { atr14: 2.1, bollinger_upper: 130, bollinger_middle: 125, bollinger_lower: 120, bollinger_width: 0.08 },
    volume: { volume: 900000, volume_sma: 800000, relative_volume: 1.125 },
  },
  features: {
    price_above_ema21: true, ema9_above_ema21: true, ema21_above_ema50: true, ema50_above_ema200: null,
    trend_alignment_score: 2, trend_alignment_label: "strong", trend_direction: "bullish",
    rsi_state: "neutral", macd_state: "bullish", volume_state: "normal", volatility_state: "normal",
  },
  regime: { regime: "BULLISH", reasons: ["trend checks lean bullish with strong alignment"] },
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

describe("AnalysisPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders indicators, features, and the detected regime from the API", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(ANALYSIS_RESPONSE));

    render(<AnalysisPanel symbol="NVDA" />);

    await waitFor(() => expect(screen.getByText("BULLISH")).toBeInTheDocument());
    expect(screen.getByText(/strong · bullish/)).toBeInTheDocument();
    expect(screen.getByText(/62\.0 · neutral/)).toBeInTheDocument();
    expect(screen.getByText(/120 candles/)).toBeInTheDocument();
  });

  it("shows an error state when the analysis API call fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ error: { code: "not_found", message: "unknown asset symbol" } }, false, 404),
    );

    render(<AnalysisPanel symbol="ZZZZ" />);

    await waitFor(() => expect(screen.getByText(/unknown asset symbol/)).toBeInTheDocument());
  });
});
