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

const HISTORY_RESPONSE = {
  symbol: "AAPL",
  asset_id: "11111111-1111-1111-1111-111111111111",
  interval: "1h",
  source: "mock",
  is_mock: true,
  start: "2024-06-01T00:00:00Z",
  end: "2024-06-01T05:00:00Z",
  count: 2,
  bars: [
    { timestamp: "2024-06-01T00:00:00Z", open: "190", high: "191", low: "189", close: "190.5", volume: "1000" },
    { timestamp: "2024-06-01T01:00:00Z", open: "190.5", high: "192", low: "190", close: "191.5", volume: "1100" },
  ],
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

  it("renders quote and history data from the API, with a mock source label", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/assets")) return Promise.resolve(jsonResponse(ASSETS_RESPONSE));
      if (url.includes("/history")) return Promise.resolve(jsonResponse(HISTORY_RESPONSE));
      return Promise.resolve(jsonResponse(QUOTE_RESPONSE));
    });

    render(<MarketExplorer />);

    await waitFor(() => expect(screen.getByText("191.00000000")).toBeInTheDocument());
    expect(screen.getByText(/SOURCE: MOCK/)).toBeInTheDocument();
    expect(screen.queryByTestId("market-explorer-loading")).not.toBeInTheDocument();
  });

  it("shows an error state when the API call fails", async () => {
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
