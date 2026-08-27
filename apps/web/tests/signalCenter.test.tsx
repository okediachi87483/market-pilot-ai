import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("offers Run Risk Review for a CANDIDATE signal and shows the approved result", async () => {
    const evaluationResponse = {
      id: "re1",
      signal_id: "s1",
      symbol: "AAPL",
      policy_id: "p1",
      policy_version: 1,
      decision: "APPROVED",
      reasons: [],
      checks: [],
      calculated_position_size: "50.0000000000",
      entry_price: "100.00000000",
      stop_loss_price: "98.00000000",
      take_profit_price: "104.00000000",
      position_value: "5000.00000000",
      portfolio_snapshot: {},
      evaluated_at: "2024-06-01T00:00:00Z",
      created_at: "2024-06-01T00:00:00Z",
    };

    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
      if (url.includes("/risk/evaluate/") && init?.method === "POST") {
        return Promise.resolve(jsonResponse(evaluationResponse));
      }
      return Promise.resolve(jsonResponse(SIGNAL_RESPONSE));
    });

    render(<SignalCenter />);
    await waitFor(() => expect(screen.getByText("BUY")).toBeInTheDocument());

    const button = screen.getByRole("button", { name: /run risk review/i });
    fireEvent.click(button);

    await waitFor(() =>
      expect(screen.getByText("Risk Approved · Paper Trade Eligible")).toBeInTheDocument(),
    );
    expect(screen.getByText("98.00000000")).toBeInTheDocument(); // stop-loss
    // Never presented as an executed trade.
    expect(screen.queryByText(/trade executed/i)).not.toBeInTheDocument();
  });

  it("fetches and shows an existing risk decision for an already-evaluated signal", async () => {
    const alreadyApproved = { ...SIGNAL_RESPONSE, status: "RISK_APPROVED" };
    const evaluationResponse = {
      id: "re2",
      signal_id: "s1",
      symbol: "AAPL",
      policy_id: "p1",
      policy_version: 1,
      decision: "APPROVED",
      reasons: [],
      checks: [],
      calculated_position_size: "10",
      entry_price: "150.00",
      stop_loss_price: "147.00",
      take_profit_price: "156.00",
      position_value: "1500",
      portfolio_snapshot: {},
      evaluated_at: "2024-06-01T00:00:00Z",
      created_at: "2024-06-01T00:00:00Z",
    };

    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
      if (url.includes("/risk/evaluations")) return Promise.resolve(jsonResponse([evaluationResponse]));
      return Promise.resolve(jsonResponse(alreadyApproved));
    });

    render(<SignalCenter />);

    await waitFor(() =>
      expect(screen.getByText("Risk Approved · Paper Trade Eligible")).toBeInTheDocument(),
    );
    // No "Run Risk Review" button once a decision already exists.
    expect(screen.queryByRole("button", { name: /run risk review/i })).not.toBeInTheDocument();
  });
});
