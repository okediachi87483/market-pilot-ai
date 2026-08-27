"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiError } from "@/lib/api";
import {
  type Asset,
  type HistoryResponse,
  type QuoteResponse,
  getAssets,
  getHistory,
  getQuote,
} from "@/lib/marketData";
import { PriceChart } from "./PriceChart";

const FALLBACK_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA"];

/**
 * Market overview experience (Step 14): symbol selector, current
 * price/OHLC/volume/last-updated/source, and a history chart — all from
 * the real API (docs/market-data.md), never fabricated in the frontend.
 */
export function MarketExplorer() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [symbol, setSymbol] = useState<string>("AAPL");
  const [quote, setQuote] = useState<QuoteResponse | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    getAssets()
      .then(setAssets)
      .catch(() => {
        // The symbol selector falls back to a fixed list; the main
        // quote/history panel below surfaces its own error state.
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([getQuote(symbol), getHistory(symbol, { interval: "1h" })])
      .then(([quoteResult, historyResult]) => {
        if (cancelled) return;
        setQuote(quoteResult);
        setHistory(historyResult);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load market data.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol, reloadToken]);

  const symbolOptions = assets.length > 0 ? assets.map((asset) => asset.symbol) : FALLBACK_SYMBOLS;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <label htmlFor="symbol-select" className="text-sm text-text-secondary">
          Symbol
        </label>
        <select
          id="symbol-select"
          value={symbol}
          onChange={(event) => setSymbol(event.target.value)}
          className="rounded-md border border-border-default bg-bg-1 px-3 py-1.5 text-sm text-text-primary"
        >
          {symbolOptions.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <ErrorState message={error} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {loading && !error && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-6" data-testid="market-explorer-loading">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {!loading && !error && quote && (
        <Card eyebrow="Current Quote" mock>
          <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-6">
            <Stat label="Price" value={quote.bar.close} />
            <Stat label="Open" value={quote.bar.open} />
            <Stat label="High" value={quote.bar.high} />
            <Stat label="Low" value={quote.bar.low} />
            <Stat label="Volume" value={quote.bar.volume} />
            <Stat label="Updated" value={new Date(quote.bar.timestamp).toLocaleTimeString()} />
          </div>
          <div className="mt-3 border-t border-border-subtle pt-3 text-xs text-text-tertiary">
            SOURCE: {quote.source.toUpperCase()}
            {quote.is_mock ? " — mock market data, not a live feed" : ""}
          </div>
        </Card>
      )}

      {!loading && !error && history && (
        <Card eyebrow={`Price History — ${history.interval}`} mock>
          <PriceChart bars={history.bars} />
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-text-tertiary">{label}</div>
      <div className="font-mono text-text-primary">{value}</div>
    </div>
  );
}
