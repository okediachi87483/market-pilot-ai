import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SignalPreview } from "@/components/market/SignalPreview";

function signalFor(symbol: string, signal: string, regime: string) {
  return {
    id: symbol,
    symbol,
    interval: "1h",
    signal,
    strategy_id: "trend_momentum",
    strategy_version: "1.0.0",
    strategy_label: "trend_momentum_v1",
    strength: signal === "HOLD" ? null : "MODERATE",
    market_regime: regime,
    reasons: ["test reason"],
    supporting_features: {},
    invalidating_conditions: [],
    status: "CANDIDATE",
    generated_at: "2024-06-01T00:00:00Z",
    created_at: "2024-06-01T00:00:00Z",
    was_newly_created: true,
  };
}

function jsonResponse(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => body } as Response;
}

describe("SignalPreview", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders only non-HOLD signals from the API, never a fabricated confidence percentage", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("NVDA")) return Promise.resolve(jsonResponse(signalFor("NVDA", "BUY", "BULLISH")));
      if (url.includes("AAPL")) return Promise.resolve(jsonResponse(signalFor("AAPL", "HOLD", "SIDEWAYS")));
      return Promise.resolve(jsonResponse(signalFor("TSLA", "SELL", "BEARISH")));
    });

    render(<SignalPreview />);

    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument(); // HOLD filtered out
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("shows an empty state when every symbol is HOLD", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(signalFor("X", "HOLD", "SIDEWAYS")),
    );

    render(<SignalPreview />);

    await waitFor(() =>
      expect(screen.getByText(/No BUY\/SELL candidates/)).toBeInTheDocument(),
    );
  });
});
