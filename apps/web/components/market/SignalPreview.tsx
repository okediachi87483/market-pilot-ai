"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusTag, type MarketState } from "@/components/ui/StatusTag";
import { type SignalResponse, evaluateSignal } from "@/lib/signals";

const PREVIEW_SYMBOLS = ["NVDA", "AAPL", "TSLA"];

/**
 * See docs/component-architecture.md (SignalPanel). Real API-backed data
 * (Phase 5) — deliberately shows signal type + strength (WEAK/MODERATE/
 * STRONG), never a fabricated confidence percentage (docs/signal-engine.md
 * §"Strength calculation"). Full detail lives on /signals.
 */
export function SignalPreview() {
  const [signals, setSignals] = useState<SignalResponse[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all(PREVIEW_SYMBOLS.map((symbol) => evaluateSignal(symbol, "1h")))
      .then((results) => {
        if (!cancelled) setSignals(results.filter((s) => s.signal !== "HOLD"));
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card eyebrow="Active Signals" mock>
      {failed && <EmptyState message="Couldn't load signals." />}
      {!failed && !signals && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      )}
      {!failed && signals && signals.length === 0 && (
        <EmptyState message="No BUY/SELL candidates right now — see /signals for full detail." />
      )}
      {!failed && signals && signals.length > 0 && (
        <div className="flex flex-col gap-2">
          {signals.map((signal) => (
            <div
              key={signal.id}
              className="flex flex-col gap-1.5 rounded-md border border-border-subtle bg-bg-2 p-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-text-primary">{signal.symbol}</span>
                <StatusTag state={signal.market_regime as MarketState} />
              </div>
              <div className="flex justify-between font-mono text-xs text-text-tertiary">
                <span>{signal.signal}</span>
                <span className="text-text-primary">{signal.strength ?? "—"}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
