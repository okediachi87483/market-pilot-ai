import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SignalCenter } from "@/components/market/SignalCenter";

const ASSETS_RESPONSE = [
  { id: "1", symbol: "AAPL", name: "Apple Inc.", asset_type: "equity", exchange: "NASDAQ", currency: "USD", active: true, created_at: "", updated_at: "" },
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
  reasons: [
    "Detected market regime is BULLISH",
    "MACD is bullish (histogram positive)",
    "RSI at 55.0 (neutral) — not extremely overbought",
  ],
  supporting_features: { rsi14: 55.0 },
  invalidating_conditions: ["Price loses EMA21 support", "MACD turns bearish"],
  status: "CANDIDATE",
  generated_at: "2024-06-01T00:00:00Z",
  created_at: "2024-06-01T00:00:00Z",
  was_newly_created: true,
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

describe("SignalCenter", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a loading state before the evaluation resolves", () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
      return new Promise(() => {}); // evaluate never resolves
    });
    render(<SignalCenter />);
    expect(screen.getByTestId("signal-center-loading")).toBeInTheDocument();
  });

  it("renders the evaluated signal with its reasons and invalidating conditions", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
      return Promise.resolve(jsonResponse(SIGNAL_RESPONSE));
    });

    render(<SignalCenter />);

    await waitFor(() => expect(screen.getByText("BUY")).toBeInTheDocument());
    expect(screen.getByText("STRONG")).toBeInTheDocument();
    expect(screen.getByText(/Detected market regime is BULLISH/)).toBeInTheDocument();
    expect(screen.getByText(/Price loses EMA21 support/)).toBeInTheDocument();
    expect(screen.getByText("CANDIDATE")).toBeInTheDocument();
    // No fabricated probability anywhere on screen.
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("shows an error state when evaluation fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
      return Promise.resolve(
        jsonResponse({ error: { code: "not_found", message: "unknown asset symbol" } }, false, 404),
      );
    });

    render(<SignalCenter />);

    await waitFor(() => expect(screen.getByText(/unknown asset symbol/)).toBeInTheDocument());
  });
});
