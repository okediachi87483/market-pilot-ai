"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { type AIAnalysis, type AIStatus, getAIStatus, listAIAnalyses } from "@/lib/aiAnalyst";
import { ApiError } from "@/lib/api";
import { type RiskEvaluation, listRiskEvaluations } from "@/lib/risk";
import { type SignalResponse, getSignal } from "@/lib/signals";

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

const DECISION_COLOR: Record<RiskEvaluation["decision"], string> = {
  APPROVED: "var(--color-positive)",
  REJECTED: "var(--color-negative)",
};

/**
 * Dashboard AI Analyst panel (Step 22) — the most recent analysis's
 * thesis, suggested action, and qualitative uncertainty, alongside the
 * deterministic signal direction it was based on and the Risk Engine's
 * decision if one exists. Never a numeric confidence figure (Step 39:
 * no fake AI). Shows an explicit unavailable state rather than an empty
 * card when the provider isn't configured, rather than a plain "no
 * data" message that could be mistaken for a real absence of activity.
 */
export function AIAnalystPreview() {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null);
  const [signal, setSignal] = useState<SignalResponse | null>(null);
  const [riskEvaluation, setRiskEvaluation] = useState<RiskEvaluation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getAIStatus()
      .then((statusResult) => {
        if (cancelled) return;
        setStatus(statusResult);
        if (!statusResult.available) return null;
        return listAIAnalyses({ limit: 1 }).then((rows) => {
          if (cancelled) return;
          const [latest] = rows;
          if (!latest) return;
          setAnalysis(latest);
          return Promise.all([
            getSignal(latest.signal_id).catch(() => null),
            listRiskEvaluations({ signalId: latest.signal_id, limit: 1 }).catch(() => []),
          ]).then(([signalResult, riskRows]) => {
            if (cancelled) return;
            setSignal(signalResult);
            setRiskEvaluation(riskRows[0] ?? null);
          });
        });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load AI Analyst data.");
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
      <Card eyebrow="AI Analyst">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4" />
          <Skeleton className="h-14" />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card eyebrow="AI Analyst">
        <ErrorState message={error} onRetry={() => setReloadToken((t) => t + 1)} />
      </Card>
    );
  }

  if (!status?.available) {
    return (
      <Card eyebrow="AI Analyst">
        <EmptyState message="AI Analyst unavailable — configure the Claude provider to enable analysis." />
      </Card>
    );
  }

  if (!analysis) {
    return (
      <Card eyebrow="AI Analyst">
        <EmptyState message="No AI analyses yet — run one from the AI Analyst screen." />
      </Card>
    );
  }

  const disagrees = signal !== null && analysis.suggested_action !== signal.signal;

  return (
    <Card eyebrow="AI Analyst">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-text-primary">{analysis.symbol}</span>
          <div className="flex items-center gap-2">
            <span
              className="text-xs font-bold uppercase tracking-wide"
              style={{ color: ACTION_COLOR[analysis.suggested_action] }}
            >
              {analysis.suggested_action}
            </span>
            <span
              className="rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
              style={{
                color: UNCERTAINTY_COLOR[analysis.uncertainty],
                borderColor: UNCERTAINTY_COLOR[analysis.uncertainty],
              }}
            >
              {analysis.uncertainty}
            </span>
          </div>
        </div>

        <p className="line-clamp-2 text-[11px] text-text-secondary">{analysis.thesis}</p>

        <div className="flex items-center justify-between border-t border-border-subtle pt-2 text-[11px]">
          <span className="text-text-tertiary">Deterministic signal</span>
          <span className="font-mono text-text-primary">{signal?.signal ?? "—"}</span>
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-text-tertiary">Risk decision</span>
          <span
            className="font-mono"
            style={{
              color: riskEvaluation ? DECISION_COLOR[riskEvaluation.decision] : "var(--color-text-tertiary)",
            }}
          >
            {riskEvaluation?.decision ?? "Not yet evaluated"}
          </span>
        </div>

        {disagrees && (
          <div className="rounded-sm border border-accent-amber px-2 py-1 text-[10px] font-semibold text-accent-amber">
            Analysis disagreement — AI and signal differ
          </div>
        )}
      </div>
    </Card>
  );
}
