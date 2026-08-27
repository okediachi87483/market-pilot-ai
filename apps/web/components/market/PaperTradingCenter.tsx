"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiError } from "@/lib/api";
import {
  type PaperFill,
  type PaperOrder,
  type PaperPortfolio,
  type PaperPosition,
  closePaperPosition,
  getPaperPortfolio,
  listPaperFills,
  listPaperOrders,
  listPaperPositions,
} from "@/lib/paperTrading";

function money(value: string): string {
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

function pl(value: string): string {
  const n = Number(value);
  const formatted = money(value);
  return n > 0 ? `+${formatted}` : formatted;
}

function plColor(value: string): string {
  const n = Number(value);
  if (n > 0) return "var(--color-positive)";
  if (n < 0) return "var(--color-negative)";
  return "var(--color-text-secondary)";
}

const STATUS_COLOR: Record<string, string> = {
  FILLED: "var(--color-positive)",
  REJECTED: "var(--color-negative)",
  PENDING: "var(--color-text-tertiary)",
  CANCELLED: "var(--color-text-tertiary)",
};

/**
 * The Paper Trading Center (Step 24) — Account, Positions, Orders, and
 * Recent Fills, all real data. Never "real trade" language anywhere
 * here (Step 19/23): every action is a "Simulated Order"/"Simulated
 * Fill" against this account's own paper ledger, not a live market.
 */
export function PaperTradingCenter() {
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [fills, setFills] = useState<PaperFill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [closingSymbol, setClosingSymbol] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      getPaperPortfolio(),
      listPaperPositions("OPEN"),
      listPaperOrders({ limit: 15 }),
      listPaperFills({ limit: 15 }),
    ])
      .then(([portfolioResult, positionsResult, ordersResult, fillsResult]) => {
        if (cancelled) return;
        setPortfolio(portfolioResult);
        setPositions(positionsResult);
        setOrders(ordersResult);
        setFills(fillsResult);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load paper trading data.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  function handleClose(symbol: string) {
    setClosingSymbol(symbol);
    closePaperPosition(symbol)
      .then(() => setReloadToken((t) => t + 1))
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Failed to close position.");
      })
      .finally(() => setClosingSymbol(null));
  }

  if (loading) {
    return (
      <div data-testid="paper-trading-loading" className="flex flex-col gap-4">
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error} onRetry={() => setReloadToken((t) => t + 1)} />;
  }

  if (!portfolio) {
    return <EmptyState message="No paper trading account available." />;
  }

  return (
    <div className="flex flex-col gap-5">
      <section className="grid grid-cols-2 gap-4 rounded-md border border-border-subtle bg-bg-1 p-5 md:grid-cols-6">
        <AccountStat label="Starting equity" value={money(portfolio.starting_equity)} />
        <AccountStat label="Cash" value={money(portfolio.cash)} />
        <AccountStat label="Equity" value={money(portfolio.equity)} emphasize />
        <AccountStat
          label="Total P/L"
          value={pl(portfolio.total_pnl)}
          color={plColor(portfolio.total_pnl)}
        />
        <AccountStat
          label="Daily P/L"
          value={pl(portfolio.daily_pnl)}
          color={plColor(portfolio.daily_pnl)}
        />
        <AccountStat
          label="Drawdown"
          value={`${Number(portfolio.drawdown_pct).toFixed(2)}%`}
          color={Number(portfolio.drawdown_pct) > 0 ? "var(--color-accent-amber)" : undefined}
        />
      </section>

      <section className="flex flex-col gap-3 rounded-md border border-border-subtle bg-bg-1 p-5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
          Positions
        </div>
        {positions.length === 0 ? (
          <EmptyState message="No paper positions yet." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-text-tertiary">
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4">Quantity</th>
                  <th className="pb-2 pr-4">Avg entry</th>
                  <th className="pb-2 pr-4">Current</th>
                  <th className="pb-2 pr-4">Market value</th>
                  <th className="pb-2 pr-4">Unrealized P/L</th>
                  <th className="pb-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {positions.map((position) => (
                  <tr key={position.id}>
                    <td className="py-2 pr-4 font-mono font-semibold text-text-primary">
                      {position.symbol}
                    </td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">{position.quantity}</td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">
                      {money(position.avg_entry_price)}
                    </td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">
                      {money(position.current_price)}
                    </td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">
                      {money(position.market_value)}
                    </td>
                    <td
                      className="py-2 pr-4 font-mono"
                      style={{ color: plColor(position.unrealized_pnl) }}
                    >
                      {pl(position.unrealized_pnl)}
                    </td>
                    <td className="py-2">
                      <button
                        type="button"
                        onClick={() => handleClose(position.symbol)}
                        disabled={closingSymbol === position.symbol}
                        className="rounded-md border border-border-default bg-bg-2 px-2.5 py-1 text-[11px] font-semibold text-text-primary hover:bg-bg-3 disabled:opacity-50"
                      >
                        {closingSymbol === position.symbol ? "Closing…" : "Close"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3 rounded-md border border-border-subtle bg-bg-1 p-5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
          Orders
        </div>
        {orders.length === 0 ? (
          <EmptyState message="No simulated orders yet." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-text-tertiary">
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4">Side</th>
                  <th className="pb-2 pr-4">Quantity</th>
                  <th className="pb-2 pr-4">Requested</th>
                  <th className="pb-2 pr-4">Fill price</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td className="py-2 pr-4 font-mono font-semibold text-text-primary">
                      {order.symbol}
                    </td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">{order.side}</td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">{order.quantity}</td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">
                      {money(order.requested_price)}
                    </td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">
                      {order.average_fill_price ? money(order.average_fill_price) : "—"}
                    </td>
                    <td className="py-2 pr-4">
                      <span
                        className="font-mono font-semibold"
                        style={{ color: STATUS_COLOR[order.status] }}
                        title={order.rejection_reason ?? undefined}
                      >
                        {order.status}
                      </span>
                    </td>
                    <td className="py-2 font-mono text-[10px] text-text-tertiary">
                      {new Date(order.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3 rounded-md border border-border-subtle bg-bg-1 p-5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
          Recent Fills
        </div>
        {fills.length === 0 ? (
          <EmptyState message="No simulated fills yet." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-text-tertiary">
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4">Side</th>
                  <th className="pb-2 pr-4">Quantity</th>
                  <th className="pb-2 pr-4">Fill price</th>
                  <th className="pb-2 pr-4">Fee</th>
                  <th className="pb-2">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {fills.map((fill) => (
                  <tr key={fill.id}>
                    <td className="py-2 pr-4 font-mono font-semibold text-text-primary">
                      {fill.symbol}
                    </td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">{fill.side}</td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">{fill.quantity}</td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">
                      {money(fill.fill_price)}
                    </td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">{money(fill.fee)}</td>
                    <td className="py-2 font-mono text-[10px] text-text-tertiary">
                      {new Date(fill.timestamp).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function AccountStat({
  label,
  value,
  color,
  emphasize = false,
}: {
  label: string;
  value: string;
  color?: string;
  emphasize?: boolean;
}) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-text-tertiary">{label}</div>
      <div
        className={`font-mono ${emphasize ? "text-lg font-semibold" : "text-sm"}`}
        style={{ color: color ?? "var(--color-text-primary)" }}
      >
        {value}
      </div>
    </div>
  );
}
