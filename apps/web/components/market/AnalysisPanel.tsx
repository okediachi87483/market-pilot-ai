"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusTag, type MarketState } from "@/components/ui/StatusTag";
import { ApiError } from "@/lib/api";
import { type AnalysisResponse, getAnalysis } from "@/lib/analysis";
import type { SupportedInterval } from "@/lib/marketData";

function fmt(value: number | null, digits = 2): string {
  return value === null ? "—" : value.toFixed(digits);
}

function SectionHeading({ title, help }: { title: string; help: string }) {
  return (
    <div className="mb-2">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
        {title}
      </div>
      <div className="text-[11px] text-text-tertiary">{help}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-border-subtle py-1.5 text-xs last:border-0">
      <span className="text-text-secondary">{label}</span>
      <span className="font-mono text-text-primary">{value}</span>
    </div>
  );
}

/**
 * Sophisticated but explained analysis panel (Step 11) — trend, momentum,
 * volatility, volume, and detected regime, all from the real backend
 * (docs/technical-analysis.md). No BUY/SELL language anywhere: this
 * describes conditions, not decisions.
 */
export function AnalysisPanel({
  symbol,
  interval = "1h",
}: {
  symbol: string;
  interval?: SupportedInterval;
}) {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getAnalysis(symbol, interval)
      .then((result) => {
        if (!cancelled) setAnalysis(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load analysis.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, interval]);

  if (loading) {
    return (
      <Card eyebrow="Technical Analysis" mock>
        <div className="flex flex-col gap-2">
          <Skeleton className="h-6" />
          <Skeleton className="h-32" />
        </div>
      </Card>
    );
  }

  if (error || !analysis) {
    return (
      <Card eyebrow="Technical Analysis" mock>
        <ErrorState message={error ?? "No analysis available."} retryable={false} />
      </Card>
    );
  }

  const { indicators, features, regime } = analysis;

  return (
    <Card eyebrow="Technical Analysis" mock>
      <div className="mb-4 flex items-center justify-between">
        <StatusTag state={regime.regime as MarketState} />
        <span className="text-[11px] text-text-tertiary">
          {analysis.candle_count} candles &middot; {analysis.interval}
        </span>
      </div>
      <p className="mb-4 text-xs leading-relaxed text-text-secondary">
        {regime.reasons.join("; ")}. Detected from the available dataset, not a guarantee of
        future direction.
      </p>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div>
          <SectionHeading title="Trend" help="Moving averages — is price generally rising or falling?" />
          <Row label="SMA 20 / 50 / 200" value={`${fmt(indicators.trend.sma20)} / ${fmt(indicators.trend.sma50)} / ${fmt(indicators.trend.sma200)}`} />
          <Row label="EMA 9 / 21 / 50 / 200" value={`${fmt(indicators.trend.ema9)} / ${fmt(indicators.trend.ema21)} / ${fmt(indicators.trend.ema50)} / ${fmt(indicators.trend.ema200)}`} />
          <Row label="Alignment" value={`${features.trend_alignment_label ?? "n/a"} · ${features.trend_direction ?? "n/a"}`} />
        </div>

        <div>
          <SectionHeading title="Momentum" help="Speed and direction of recent price change." />
          <Row label="RSI (14)" value={`${fmt(indicators.momentum.rsi14, 1)} · ${features.rsi_state ?? "n/a"}`} />
          <Row label="MACD" value={`${fmt(indicators.momentum.macd)} / ${fmt(indicators.momentum.macd_signal)} · ${features.macd_state ?? "n/a"}`} />
          <Row label="Stochastic %K / %D" value={`${fmt(indicators.momentum.stochastic_k, 1)} / ${fmt(indicators.momentum.stochastic_d, 1)}`} />
        </div>

        <div>
          <SectionHeading title="Volatility" help="How much price is moving, regardless of direction." />
          <Row label="ATR (14)" value={fmt(indicators.volatility.atr14)} />
          <Row
            label="Bollinger Bands"
            value={`${fmt(indicators.volatility.bollinger_lower)} – ${fmt(indicators.volatility.bollinger_upper)}`}
          />
          <Row label="State" value={features.volatility_state ?? "n/a"} />
        </div>

        <div>
          <SectionHeading title="Volume" help="Trading activity relative to its recent average." />
          <Row label="Volume" value={fmt(indicators.volume.volume, 0)} />
          <Row label="Volume SMA (20)" value={fmt(indicators.volume.volume_sma, 0)} />
          <Row
            label="Relative volume"
            value={`${fmt(indicators.volume.relative_volume)}x · ${features.volume_state ?? "n/a"}`}
          />
        </div>
      </div>
    </Card>
  );
}
