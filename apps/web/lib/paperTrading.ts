import { apiFetch } from "@/lib/api";

// Mirrors apps/api/app/schemas/paper.py — kept in sync by hand until the
// generated-client tooling from docs/api.md §4 lands. Decimal-backed
// fields are typed `string` (Pydantic v2's default JSON encoding for
// `Decimal`), matching the convention used throughout lib/risk.ts and
// lib/marketData.ts — parse with `Number(...)` at the point of use.

export type OrderSide = "BUY" | "SELL";
export type OrderStatus = "PENDING" | "FILLED" | "REJECTED" | "CANCELLED";
export type PositionStatus = "OPEN" | "CLOSED";

export interface PaperOrder {
  id: string;
  signal_id: string | null;
  symbol: string;
  side: OrderSide;
  order_type: string;
  quantity: string;
  requested_price: string;
  status: OrderStatus;
  filled_quantity: string;
  average_fill_price: string | null;
  rejection_reason: string | null;
  created_at: string;
  submitted_at: string | null;
  filled_at: string | null;
  cancelled_at: string | null;
}

export interface PaperFill {
  id: string;
  order_id: string;
  symbol: string;
  side: OrderSide;
  quantity: string;
  fill_price: string;
  fee: string;
  realized_pnl: string | null;
  timestamp: string;
}

export interface PaperPosition {
  id: string;
  symbol: string;
  quantity: string;
  avg_entry_price: string;
  current_price: string;
  market_value: string;
  unrealized_pnl: string;
  realized_pnl: string;
  status: PositionStatus;
  opened_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface PaperPortfolio {
  starting_equity: string;
  cash: string;
  market_value: string;
  equity: string;
  realized_pnl_total: string;
  unrealized_pnl: string;
  total_pnl: string;
  daily_pnl: string;
  peak_equity: string;
  drawdown_pct: string;
  open_position_count: number;
  as_of: string;
}

export function getPaperPortfolio(): Promise<PaperPortfolio> {
  return apiFetch<PaperPortfolio>("/api/v1/paper/portfolio");
}

export function listPaperPositions(status?: PositionStatus): Promise<PaperPosition[]> {
  const query = status ? `?status=${status}` : "";
  return apiFetch<PaperPosition[]>(`/api/v1/paper/positions${query}`);
}

export function listPaperOrders(options?: {
  symbol?: string;
  status?: OrderStatus;
  limit?: number;
}): Promise<PaperOrder[]> {
  const params = new URLSearchParams();
  if (options?.symbol) params.set("symbol", options.symbol);
  if (options?.status) params.set("status", options.status);
  if (options?.limit) params.set("limit", String(options.limit));
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<PaperOrder[]>(`/api/v1/paper/orders${query}`);
}

export function getPaperOrder(id: string): Promise<PaperOrder> {
  return apiFetch<PaperOrder>(`/api/v1/paper/orders/${encodeURIComponent(id)}`);
}

export function listPaperFills(options?: {
  symbol?: string;
  orderId?: string;
  limit?: number;
}): Promise<PaperFill[]> {
  const params = new URLSearchParams();
  if (options?.symbol) params.set("symbol", options.symbol);
  if (options?.orderId) params.set("order_id", options.orderId);
  if (options?.limit) params.set("limit", String(options.limit));
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<PaperFill[]>(`/api/v1/paper/fills${query}`);
}

export function executePaperOrder(signalId: string): Promise<PaperOrder> {
  return apiFetch<PaperOrder>(`/api/v1/paper/execute/${encodeURIComponent(signalId)}`, {
    method: "POST",
  });
}

export function closePaperPosition(symbol: string): Promise<PaperOrder> {
  return apiFetch<PaperOrder>(`/api/v1/paper/positions/${encodeURIComponent(symbol)}/close`, {
    method: "POST",
  });
}
