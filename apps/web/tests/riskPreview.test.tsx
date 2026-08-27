import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RiskPreview } from "@/components/market/RiskPreview";

const SUMMARY_RESPONSE = {
  portfolio: {
    equity: "100000",
    cash: "100000",
    high_water_mark: "100000",
    drawdown_pct: "3.2",
    open_position_count: 0,
    open_position_value: "20000",
    available_exposure_value: "30000",
    realized_pl_today: "0",
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
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

describe("RiskPreview", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders real exposure and drawdown from the API, not the old mock numbers", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(jsonResponse(SUMMARY_RESPONSE));

    render(<RiskPreview />);

    await waitFor(() => expect(screen.getByText(/40% \/ 50.00%/)).toBeInTheDocument());
    expect(screen.getByText(/3.2% \/ 15%/)).toBeInTheDocument();
    // The old hardcoded mock values must be gone.
    expect(screen.queryByText("62% / 80%")).not.toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ error: { code: "internal_error", message: "risk service unavailable" } }, false, 500),
    );

    render(<RiskPreview />);

    await waitFor(() => expect(screen.getByText(/risk service unavailable/)).toBeInTheDocument());
  });
});
