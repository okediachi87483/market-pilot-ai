"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusTag, type MarketState } from "@/components/ui/StatusTag";
import { ApiError } from "@/lib/api";
import { type AnalysisResponse, getAnalysis } from "@/lib/analysis";

/**
 * MarketPilot's signature Market State visualization (Step 12) —
 * synthesizes trend, momentum, volatility, and volume into one glance.
 *
 * This answers "what does the market currently look like?", never "what
 * should I buy?" — there is no AI here yet (that's a later phase) and no
 * BUY/SELL/SHORT/EXIT language anywhere in this component. The needle
 * position is derived transparently from the same trend_alignment_score
 * and trend_direction already returned by the API (see
 * docs/technical-analysis.md §"Signature visualization mapping"), not a
 * separately invented number.
 */
export function MarketStateVisualization({ symbol = "AAPL" }: { symbol?: string }) {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAnalysis(symbol, "1d")
      .then((result) => {
        if (!cancelled) setAnalysis(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load market state.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (error) {
    return (
      <Card eyebrow="Market State" mock>
        <ErrorState message={error} retryable={false} />
      </Card>
    );
  }

  if (!analysis) {
    return (
      <Card eyebrow="Market State" mock className="flex flex-col items-center gap-3">
        <Skeleton className="h-40 w-[70%] max-w-[220px]" />
        <Skeleton className="h-4 w-24" />
      </Card>
    );
  }

  const needleAngle = needleAngleForFeatures(
    analysis.features.trend_direction,
    analysis.features.trend_alignment_score,
  );
  const regimeState = analysis.regime.regime as MarketState;

  return (
    <Card eyebrow="Market State" mock className="flex flex-col items-center gap-3">
      <svg viewBox="0 0 240 160" className="w-[70%] max-w-[220px]" aria-hidden="true">
        <path
          d="M20,130 A100,100 0 0 1 70,43.4"
          fill="none"
          stroke="var(--color-negative)"
          strokeWidth="10"
          strokeLinecap="round"
          opacity="0.55"
        />
        <path
          d="M70,43.4 A100,100 0 0 1 170,43.4"
          fill="none"
          stroke="var(--color-neutral-signal)"
          strokeWidth="10"
          strokeLinecap="round"
          opacity="0.4"
        />
        <path
          d="M170,43.4 A100,100 0 0 1 220,130"
          fill="none"
          stroke="var(--color-positive)"
          strokeWidth="10"
          strokeLinecap="round"
          opacity="0.55"
        />
        <circle
          cx="120"
          cy="130"
          r="6"
          fill="var(--color-bg-1)"
          stroke="var(--color-border-default)"
          strokeWidth="1.5"
        />
        <line
          x1="120"
          y1="130"
          x2={needleAngle.x}
          y2={needleAngle.y}
          stroke="var(--color-text-primary)"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <circle cx="120" cy="130" r="3" fill="var(--color-text-primary)" />
      </svg>

      <StatusTag state={regimeState} />

      <p className="text-center text-xs leading-relaxed text-text-secondary">
        Trend {analysis.features.trend_direction ?? "unknown"} (
        {analysis.features.trend_alignment_label ?? "n/a"} alignment) &middot; momentum{" "}
        {analysis.features.rsi_state ?? "n/a"} &middot; volatility{" "}
        {analysis.features.volatility_state ?? "n/a"} &middot; volume{" "}
        {analysis.features.volume_state ?? "n/a"}.
      </p>
      <p className="text-center text-[10px] text-text-tertiary">
        Detected from {analysis.candle_count} {analysis.interval} candles &middot; not a
        recommendation.
      </p>
    </Card>
  );
}

/**
 * Maps trend_alignment_score (0/1/2) + trend_direction into a needle tip
 * on the same semicircle gauge used elsewhere in the design system
 * (center 120,130 radius 80). weak=0 -> centered/up; partial=1 -> 55% of
 * full deflection; strong=2 -> full deflection. Direction flips the sign.
 */
function needleAngleForFeatures(
  direction: AnalysisResponse["features"]["trend_direction"],
  score: number | null,
): { x: number; y: number } {
  const sign = direction === "bullish" ? 1 : direction === "bearish" ? -1 : 0;
  const magnitude = score === 2 ? 100 : score === 1 ? 55 : 0;
  const value = sign * magnitude; // -100..100

  const angleDeg = 180 - ((value + 100) / 200) * 180;
  const rad = (angleDeg * Math.PI) / 180;
  const needleLen = 80;
  return {
    x: 120 + needleLen * Math.cos(rad),
    y: 130 - needleLen * Math.sin(rad),
  };
}
