import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PaperTradingCenter } from "@/components/market/PaperTradingCenter";

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

const POSITIONS_RESPONSE = [
  {
    id: "pos1",
    symbol: "AAPL",
    quantity: "10",
    avg_entry_price: "175.00",
    current_price: "180.20",
    market_value: "1802.00",
    unrealized_pnl: "52.00",
    realized_pnl: "0",
    status: "OPEN",
    opened_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    closed_at: null,
  },
];

const ORDERS_RESPONSE = [
  {
    id: "order1",
    signal_id: "sig1",
    symbol: "AAPL",
    side: "BUY",
    order_type: "MARKET",
    quantity: "10",
    requested_price: "175.00",
    status: "FILLED",
    filled_quantity: "10",
    average_fill_price: "175.00",
    rejection_reason: null,
    created_at: "2026-01-01T00:00:00Z",
    submitted_at: "2026-01-01T00:00:00Z",
    filled_at: "2026-01-01T00:00:01Z",
    cancelled_at: null,
  },
];

const FILLS_RESPONSE = [
  {
    id: "fill1",
    order_id: "order1",
    symbol: "AAPL",
    side: "BUY",
    quantity: "10",
    fill_price: "175.00",
    fee: "1.75",
    realized_pnl: null,
    timestamp: "2026-01-01T00:00:01Z",
  },
];

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body } as Response;
}

function mockFetchImplementation() {
  return (url: string) => {
    if (url.includes("/paper/portfolio")) return Promise.resolve(jsonResponse(PORTFOLIO_RESPONSE));
    if (url.includes("/paper/positions")) return Promise.resolve(jsonResponse(POSITIONS_RESPONSE));
    if (url.includes("/paper/orders")) return Promise.resolve(jsonResponse(ORDERS_RESPONSE));
    if (url.includes("/paper/fills")) return Promise.resolve(jsonResponse(FILLS_RESPONSE));
    return Promise.resolve(jsonResponse({}));
  };
}

describe("PaperTradingCenter", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a loading state before data resolves", () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(() => new Promise(() => {}));
    render(<PaperTradingCenter />);
    expect(screen.getByTestId("paper-trading-loading")).toBeInTheDocument();
  });

  it("renders account, positions, orders, and fills from the API", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(mockFetchImplementation());

    render(<PaperTradingCenter />);

    await waitFor(() => expect(screen.getByText("$100,200.00")).toBeInTheDocument());
    expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    expect(screen.getByText("FILLED")).toBeInTheDocument();
    // Never presents a simulated fill as a real trade.
    expect(screen.queryByText(/real trade/i)).not.toBeInTheDocument();
  });

  it("shows empty states when there are no positions, orders, or fills", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      if (url.includes("/paper/portfolio")) return Promise.resolve(jsonResponse(PORTFOLIO_RESPONSE));
      if (url.includes("/paper/positions")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper/orders")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/paper/fills")) return Promise.resolve(jsonResponse([]));
      return Promise.resolve(jsonResponse({}));
    });

    render(<PaperTradingCenter />);

    await waitFor(() => expect(screen.getByText("No paper positions yet.")).toBeInTheDocument());
    expect(screen.getByText("No simulated orders yet.")).toBeInTheDocument();
    expect(screen.getByText("No simulated fills yet.")).toBeInTheDocument();
  });

  it("shows an error state when the portfolio request fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ error: { code: "internal_error", message: "paper service unavailable" } }, false, 500),
    );

    render(<PaperTradingCenter />);

    await waitFor(() => expect(screen.getByText(/paper service unavailable/)).toBeInTheDocument());
  });

  it("closes a position via the Close button", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/positions/AAPL/close") && init?.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            ...ORDERS_RESPONSE[0],
            id: "order2",
            side: "SELL",
            signal_id: null,
          }),
        );
      }
      return mockFetchImplementation()(url);
    });

    render(<PaperTradingCenter />);
    await waitFor(() => expect(screen.getByText("$100,200.00")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /close/i }));

    await waitFor(() =>
      expect(
        (fetch as ReturnType<typeof vi.fn>).mock.calls.some((call) => {
          const [url, init] = call as [string, RequestInit?];
          return url.includes("/positions/AAPL/close") && init?.method === "POST";
        }),
      ).toBe(true),
    );
  });
});
