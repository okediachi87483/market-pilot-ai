"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiError } from "@/lib/api";
import { type PaperPortfolio, getPaperPortfolio } from "@/lib/paperTrading";

function money(value: string): string {
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

/**
 * Dashboard portfolio panel — real paper-trading data as of Phase 7
 * (docs/paper-trading.md), replacing the earlier hardcoded "$128,402.19"
 * mock. See PaperTradingCenter.tsx for the full Paper Trading Center
 * this links out to.
 */
export function PortfolioPreview() {
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getPaperPortfolio()
      .then((result) => {
        if (!cancelled) setPortfolio(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load portfolio.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  if (loading) {
    return (
      <Card eyebrow="Portfolio Performance">
        <Skeleton className="h-9 w-40" />
        <Skeleton className="mt-2 h-4 w-56" />
      </Card>
    );
  }

  if (error || !portfolio) {
    return (
      <Card eyebrow="Portfolio Performance">
        <ErrorState
          message={error ?? "No portfolio data available."}
          onRetry={() => setReloadToken((t) => t + 1)}
        />
      </Card>
    );
  }

  const dailyPnl = Number(portfolio.daily_pnl);
  const totalReturnPct =
    Number(portfolio.starting_equity) > 0
      ? (Number(portfolio.total_pnl) / Number(portfolio.starting_equity)) * 100
      : 0;

  return (
    <Card eyebrow="Portfolio Performance">
      <div className="font-mono text-3xl font-semibold text-text-primary">
        {money(portfolio.equity)}
      </div>
      <div className="mt-1 flex gap-3 font-mono text-xs">
        <span style={{ color: dailyPnl >= 0 ? "var(--color-positive)" : "var(--color-negative)" }}>
          {dailyPnl >= 0 ? "+" : ""}
          {money(portfolio.daily_pnl)} today
        </span>
        <span className="text-text-tertiary">
          {totalReturnPct >= 0 ? "+" : ""}
          {totalReturnPct.toFixed(1)}% total return
        </span>
      </div>
    </Card>
  );
}
