"use client";

import { useEffect, useState } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiError } from "@/lib/api";
import { type Asset, getAssets } from "@/lib/marketData";
import { type EvaluateSignalResponse, evaluateSignal } from "@/lib/signals";
import { SignalCard } from "./SignalCard";

const FALLBACK_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA"];

/**
 * The Signal Center (Step 13/14) — "what does the deterministic strategy
 * currently suggest?", kept visually and conceptually distinct from the
 * Market State visualization ("what does the market look like?"). This
 * screen is prescriptive within the bounds of one named, versioned
 * strategy; Market State is purely descriptive. They are never merged
 * into one component.
 */
export function SignalCenter() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [symbol, setSymbol] = useState("AAPL");
  const [signal, setSignal] = useState<EvaluateSignalResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    getAssets()
      .then(setAssets)
      .catch(() => {
        // Falls back to the fixed symbol list; the evaluation panel
        // below surfaces its own error state.
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    evaluateSignal(symbol, "1h")
      .then((result) => {
        if (!cancelled) setSignal(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to evaluate signal.");
        }
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
        <label htmlFor="signal-symbol-select" className="text-sm text-text-secondary">
          Symbol
        </label>
        <select
          id="signal-symbol-select"
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
        <span className="text-[11px] text-text-tertiary">
          Strategy: trend_momentum_v1 &middot; deterministic, no AI
        </span>
      </div>

      {error && (
        <ErrorState message={error} onRetry={() => setReloadToken((token) => token + 1)} />
      )}

      {loading && !error && (
        <div data-testid="signal-center-loading" className="flex flex-col gap-2">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-64" />
        </div>
      )}

      {!loading && !error && signal && <SignalCard signal={signal} />}
    </div>
  );
}
