"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiError } from "@/lib/api";
import { type RiskSummary, getRiskSummary } from "@/lib/risk";

/**
 * Dashboard risk panel — real data as of Phase 6 (docs/risk-engine.md),
 * replacing the earlier "62% / 80%" mock bars. See RiskCenter.tsx for
 * the full Risk Center this links out to.
 */
export function RiskPreview() {
  const [summary, setSummary] = useState<RiskSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getRiskSummary()
      .then((result) => {
        if (!cancelled) setSummary(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load risk data.");
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
      <Card eyebrow="Risk Exposure">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-4" />
          <Skeleton className="h-4" />
        </div>
      </Card>
    );
  }

  if (error || !summary) {
    return (
      <Card eyebrow="Risk Exposure">
        <ErrorState
          message={error ?? "No risk data available."}
          onRetry={() => setReloadToken((t) => t + 1)}
        />
      </Card>
    );
  }

  const { portfolio, policy } = summary;
  const exposureValue = Number(portfolio.open_position_value);
  const exposureLimit = exposureValue + Number(portfolio.available_exposure_value);
  const exposurePct = exposureLimit > 0 ? (exposureValue / exposureLimit) * 100 : 0;
  const drawdownPct = Number(portfolio.drawdown_pct);
  const drawdownLimit = Number(policy.max_drawdown_pct);

  return (
    <Card eyebrow="Risk Exposure">
      <div className="flex flex-col gap-3">
        <div>
          <div className="mb-1.5 flex justify-between text-xs">
            <span className="text-text-secondary">Portfolio exposure</span>
            <span className="font-mono text-text-primary">
              {exposurePct.toFixed(0)}% / {policy.max_portfolio_exposure_pct}%
            </span>
          </div>
          <div className="h-1.5 rounded-sm bg-bg-3">
            <div
              className="h-full rounded-sm bg-accent-teal"
              style={{ width: `${Math.min(exposurePct, 100)}%` }}
            />
          </div>
        </div>
        <div>
          <div className="mb-1.5 flex justify-between text-xs">
            <span className="text-text-secondary">Drawdown</span>
            <span className="font-mono text-text-primary">
              {drawdownPct.toFixed(1)}% / {drawdownLimit.toFixed(0)}%
            </span>
          </div>
          <div className="h-1.5 rounded-sm bg-bg-3">
            <div
              className="h-full rounded-sm bg-accent-amber"
              style={{ width: `${drawdownLimit > 0 ? Math.min((drawdownPct / drawdownLimit) * 100, 100) : 0}%` }}
            />
          </div>
        </div>
      </div>
    </Card>
  );
}
