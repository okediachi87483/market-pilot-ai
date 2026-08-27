import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WatchlistPreview } from "@/components/market/WatchlistPreview";

function quoteFor(symbol: string, open: string, close: string) {
  return {
    symbol,
    asset_id: "1",
    interval: "1m",
    source: "mock",
    is_mock: true,
    bar: { timestamp: "2024-06-01T12:00:00Z", open, high: close, low: open, close, volume: "1000" },
  };
}

function jsonResponse(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => body } as Response;
}

describe("WatchlistPreview", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders quotes fetched from the API, not hardcoded values", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("NVDA")) return Promise.resolve(jsonResponse(quoteFor("NVDA", "100", "110")));
      if (url.includes("AAPL")) return Promise.resolve(jsonResponse(quoteFor("AAPL", "200", "198")));
      return Promise.resolve(jsonResponse(quoteFor("TSLA", "50", "50")));
    });

    render(<WatchlistPreview />);

    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    expect(screen.getByText("110.00")).toBeInTheDocument();
    expect(screen.getByText("+10.00%")).toBeInTheDocument();
    expect(screen.getByText("-1.00%")).toBeInTheDocument();
  });

  it("shows an empty state if the quotes fail to load", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ error: { code: "internal_error", message: "boom" } }, false),
    );

    render(<WatchlistPreview />);

    await waitFor(() => expect(screen.getByText(/couldn't load watchlist/i)).toBeInTheDocument());
  });
});
