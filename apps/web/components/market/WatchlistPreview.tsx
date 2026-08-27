"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { type QuoteResponse, getQuote } from "@/lib/marketData";

const WATCHLIST_SYMBOLS = ["NVDA", "AAPL", "TSLA"];

/**
 * See docs/component-architecture.md (Watchlist). Real API-backed data
 * (Step 13) — the underlying data is still mock market data end to end
 * (docs/market-data.md), so every row is clearly source-labeled, never
 * presented as live.
 */
export function WatchlistPreview() {
  const [quotes, setQuotes] = useState<QuoteResponse[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all(WATCHLIST_SYMBOLS.map((symbol) => getQuote(symbol)))
      .then((results) => {
        if (!cancelled) setQuotes(results);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card eyebrow="Watchlist" mock>
      {failed && <EmptyState message="Couldn't load watchlist quotes." />}
      {!failed && !quotes && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-6" />
          <Skeleton className="h-6" />
          <Skeleton className="h-6" />
        </div>
      )}
      {!failed && quotes && (
        <table className="w-full text-sm">
          <tbody>
            {quotes.map((quote) => {
              const open = Number(quote.bar.open);
              const close = Number(quote.bar.close);
              const changePct = open === 0 ? 0 : ((close - open) / open) * 100;
              const positive = changePct >= 0;
              return (
                <tr key={quote.symbol} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 font-semibold text-text-primary">{quote.symbol}</td>
                  <td className="py-2 text-right font-mono text-text-primary">
                    {close.toFixed(2)}
                  </td>
                  <td
                    className={`py-2 text-right font-mono ${positive ? "text-positive" : "text-negative"}`}
                  >
                    {positive ? "+" : ""}
                    {changePct.toFixed(2)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}
