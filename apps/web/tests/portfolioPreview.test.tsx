import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PortfolioPreview } from "@/components/market/PortfolioPreview";

const PORTFOLIO_RESPONSE = {
  starting_equity: "100000",
  cash: "95000",
  market_value: "5200",
  equity: "100200",
  realized_pnl_total: "150",
  unrealized_pnl: "50",
  total_pnl: "200",
  daily_pnl: "80",
  peak_equity: "100200",
  drawdown_pct: "0",
  open_position_count: 1,
  as_of: "2026-01-01T00:00:00Z",
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

describe("PortfolioPreview", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders real equity and P/L from the API, not the old mock figure", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(PORTFOLIO_RESPONSE));

    render(<PortfolioPreview />);

    await waitFor(() => expect(screen.getByText("$100,200.00")).toBeInTheDocument());
    expect(screen.getByText(/\+\$80\.00 today/)).toBeInTheDocument();
    // The old hardcoded mock value must be gone.
    expect(screen.queryByText("$128,402.19")).not.toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ error: { code: "internal_error", message: "paper service unavailable" } }, false, 500),
    );

    render(<PortfolioPreview />);

    await waitFor(() => expect(screen.getByText(/paper service unavailable/)).toBeInTheDocument());
  });
});
