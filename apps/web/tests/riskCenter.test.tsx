import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RiskCenter } from "@/components/market/RiskCenter";

const SUMMARY_RESPONSE = {
  portfolio: {
    equity: "100000",
    cash: "100000",
    high_water_mark: "100000",
    drawdown_pct: "0",
    open_position_count: 0,
    open_position_value: "0",
    available_exposure_value: "50000",
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

const EVALUATIONS_RESPONSE = [
  {
    id: "e1",
    signal_id: "s1",
    symbol: "AAPL",
    policy_id: "p1",
    policy_version: 1,
    decision: "APPROVED",
    reasons: [],
    checks: [],
    calculated_position_size: "50",
    entry_price: "100.00",
    stop_loss_price: "98.00",
    take_profit_price: "104.00",
    position_value: "5000",
    portfolio_snapshot: {},
    evaluated_at: "2026-01-01T00:05:00Z",
    created_at: "2026-01-01T00:05:00Z",
  },
  {
    id: "e2",
    signal_id: "s2",
    symbol: "MSFT",
    policy_id: "p1",
    policy_version: 1,
    decision: "REJECTED",
    reasons: ["Signal type 'SELL' is not an actionable long-entry candidate in this phase"],
    checks: [],
    calculated_position_size: null,
    entry_price: null,
    stop_loss_price: null,
    take_profit_price: null,
    position_value: null,
    portfolio_snapshot: {},
    evaluated_at: "2026-01-01T00:06:00Z",
    created_at: "2026-01-01T00:06:00Z",
  },
];

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

describe("RiskCenter", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a loading state before data resolves", () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(() => new Promise(() => {}));
    render(<RiskCenter />);
    expect(screen.getByTestId("risk-center-loading")).toBeInTheDocument();
  });

  it("renders portfolio risk, policy limits, and recent decisions", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/risk/evaluations")) return Promise.resolve(jsonResponse(EVALUATIONS_RESPONSE));
      if (url.endsWith("/risk")) return Promise.resolve(jsonResponse(SUMMARY_RESPONSE));
      return Promise.resolve(jsonResponse(SUMMARY_RESPONSE));
    });

    render(<RiskCenter />);

    await waitFor(() => expect(screen.getByText("Portfolio Risk")).toBeInTheDocument());
    expect(screen.getByText("Risk Policy")).toBeInTheDocument();
    expect(screen.getByText("$100,000")).toBeInTheDocument();
    expect(screen.getByText("Risk Approved")).toBeInTheDocument();
    expect(screen.getByText("Risk Rejected")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    // Never presents a decision as certainty.
    expect(screen.queryByText(/guaranteed/i)).not.toBeInTheDocument();
  });

  it("shows an empty state for recent decisions when none exist", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/risk/evaluations")) return Promise.resolve(jsonResponse([]));
      return Promise.resolve(jsonResponse(SUMMARY_RESPONSE));
    });

    render(<RiskCenter />);

    await waitFor(() =>
      expect(screen.getByText(/No risk evaluations yet/)).toBeInTheDocument(),
    );
  });

  it("shows an error state when the summary request fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ error: { code: "internal_error", message: "risk service unavailable" } }, false, 500),
    );

    render(<RiskCenter />);

    await waitFor(() => expect(screen.getByText(/risk service unavailable/)).toBeInTheDocument());
  });
});
