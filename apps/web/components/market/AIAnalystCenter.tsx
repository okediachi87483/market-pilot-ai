"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { type AIAnalysis, listAIAnalyses } from "@/lib/aiAnalyst";
import { ApiError } from "@/lib/api";
import { SignalCenter } from "./SignalCenter";

const ACTION_COLOR: Record<AIAnalysis["suggested_action"], string> = {
  BUY: "var(--color-positive)",
  SELL: "var(--color-negative)",
  HOLD: "var(--color-neutral-signal)",
  NO_ACTION: "var(--color-text-tertiary)",
};

const UNCERTAINTY_COLOR: Record<AIAnalysis["uncertainty"], string> = {
  LOW: "var(--color-positive)",
  MEDIUM: "var(--color-accent-amber)",
  HIGH: "var(--color-negative)",
};

/**
 * The AI Analyst Center (Step 19) — the same evaluate-signal panel the
 * Signal Center uses (Step 20 requires the AI's analysis to sit
 * alongside the deterministic signal, the risk decision, and paper
 * trade status, never in isolation) plus a running history of past
 * analyses across symbols, mirroring RiskCenter's "Recent Decisions"
 * list.
 */
export function AIAnalystCenter() {
  const [analyses, setAnalyses] = useState<AIAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    listAIAnalyses({ limit: 15 })
      .then((rows) => {
        if (!cancelled) setAnalyses(rows);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load AI analyses.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  return (
    <div className="flex flex-col gap-5">
      <SignalCenter />

      <section className="flex flex-col gap-3 rounded-md border border-border-subtle bg-bg-1 p-5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
          Recent AI Analyses
        </div>

        {loading && (
          <div data-testid="ai-analyst-history-loading" className="flex flex-col gap-2">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        )}

        {!loading && error && (
          <ErrorState message={error} onRetry={() => setReloadToken((t) => t + 1)} />
        )}

        {!loading && !error && analyses.length === 0 && (
          <EmptyState message="No AI analyses yet — run one from the panel above." />
        )}

        {!loading && !error && analyses.length > 0 && (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {analyses.map((analysis) => (
              <li key={analysis.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-text-primary">{analysis.symbol}</span>
                  <span
                    className="text-xs font-bold uppercase tracking-wide"
                    style={{ color: ACTION_COLOR[analysis.suggested_action] }}
                  >
                    {analysis.suggested_action}
                  </span>
                  <span
                    className="rounded-sm border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
                    style={{
                      color: UNCERTAINTY_COLOR[analysis.uncertainty],
                      borderColor: UNCERTAINTY_COLOR[analysis.uncertainty],
                    }}
                  >
                    {analysis.uncertainty}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-right">
                  <span className="max-w-[320px] truncate text-[11px] text-text-tertiary">
                    {analysis.thesis}
                  </span>
                  <span className="font-mono text-[10px] text-text-tertiary">
                    {new Date(analysis.generated_at).toLocaleTimeString()}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
