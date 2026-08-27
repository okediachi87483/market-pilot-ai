"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiError } from "@/lib/api";
import {
  type RiskEvaluation,
  type RiskSummary,
  getRiskSummary,
  listRiskEvaluations,
} from "@/lib/risk";

const DECISION_COLOR: Record<RiskEvaluation["decision"], string> = {
  APPROVED: "var(--color-positive)",
  REJECTED: "var(--color-negative)",
};

function pct(value: string): number {
  return Number(value);
}

function money(value: string): string {
  const n = Number(value);
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function LimitBar({
  label,
  current,
  limit,
  currentLabel,
  limitLabel,
}: {
  label: string;
  current: number;
  limit: number;
  currentLabel: string;
  limitLabel: string;
}) {
  const ratio = limit > 0 ? Math.min(current / limit, 1) : 0;
  const nearLimit = ratio >= 0.8;
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-xs">
        <span className="text-text-secondary">{label}</span>
        <span className="font-mono text-text-primary">
          {currentLabel} / {limitLabel}
        </span>
      </div>
      <div className="h-1.5 rounded-sm bg-bg-3">
        <div
          className="h-full rounded-sm"
          style={{
            width: `${ratio * 100}%`,
            backgroundColor: nearLimit ? "var(--color-accent-amber)" : "var(--color-accent-teal)",
          }}
        />
      </div>
    </div>
  );
}

/**
 * The Risk Center (Step 21) — the first real, data-backed view of the
 * deterministic risk boundary. Deliberately restrained: bar meters and
 * plain numbers, not alarms — the goal is CONTROL, DISCIPLINE, and
 * VISIBILITY, not a warning-heavy "danger" screen. Portfolio numbers are
 * a clean, position-free simulated starting equity until Phase 7 (paper
 * trading) exists — see docs/risk-engine.md §"Portfolio state".
 */
export function RiskCenter() {
  const [summary, setSummary] = useState<RiskSummary | null>(null);
  const [evaluations, setEvaluations] = useState<RiskEvaluation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([getRiskSummary(), listRiskEvaluations({ limit: 15 })])
      .then(([summaryResult, evaluationsResult]) => {
        if (cancelled) return;
        setSummary(summaryResult);
        setEvaluations(evaluationsResult);
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
      <div data-testid="risk-center-loading" className="flex flex-col gap-4">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error} onRetry={() => setReloadToken((t) => t + 1)} />;
  }

  if (!summary) {
    return <EmptyState message="No risk data available." />;
  }

  const { portfolio, policy } = summary;

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <section className="flex flex-col gap-4 rounded-md border border-border-subtle bg-bg-1 p-5">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
            Portfolio Risk
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-text-secondary">Equity</span>
            <span className="font-mono text-lg text-text-primary">{money(portfolio.equity)}</span>
          </div>
          <LimitBar
            label="Exposure"
            current={Number(portfolio.open_position_value)}
            limit={Number(portfolio.open_position_value) + Number(portfolio.available_exposure_value)}
            currentLabel={money(portfolio.open_position_value)}
            limitLabel={money(
              String(Number(portfolio.open_position_value) + Number(portfolio.available_exposure_value)),
            )}
          />
          <LimitBar
            label="Drawdown"
            current={pct(portfolio.drawdown_pct)}
            limit={pct(policy.max_drawdown_pct)}
            currentLabel={`${pct(portfolio.drawdown_pct).toFixed(1)}%`}
            limitLabel={`${pct(policy.max_drawdown_pct).toFixed(1)}%`}
          />
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-text-secondary">Daily P/L</span>
            <span className="font-mono text-text-primary">{money(portfolio.realized_pl_today)}</span>
          </div>
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-text-secondary">Daily loss limit</span>
            <span className="font-mono text-text-primary">
              {money(`-${(Number(portfolio.equity) * pct(policy.max_daily_loss_pct)) / 100}`)}
            </span>
          </div>
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-text-secondary">Concurrent positions</span>
            <span className="font-mono text-text-primary">
              {portfolio.open_position_count} / {policy.max_concurrent_positions}
            </span>
          </div>
        </section>

        <section className="flex flex-col gap-3 rounded-md border border-border-subtle bg-bg-1 p-5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
              Risk Policy
            </span>
            <span className="font-mono text-[10px] text-text-tertiary">
              {policy.name} v{policy.version}
            </span>
          </div>
          <PolicyRow label="Max position size" value={`${policy.max_position_size_pct}%`} />
          <PolicyRow label="Max exposure" value={`${policy.max_portfolio_exposure_pct}%`} />
          <PolicyRow label="Risk per trade" value={`${policy.risk_per_trade_pct}%`} />
          <PolicyRow label="Stop loss" value={`${policy.stop_loss_pct}%`} />
          <PolicyRow label="Take profit" value={`${policy.take_profit_pct}%`} />
          <PolicyRow label="Drawdown limit" value={`${policy.max_drawdown_pct}%`} />
          <PolicyRow label="Daily loss limit" value={`${policy.max_daily_loss_pct}%`} />
          <PolicyRow label="Cooldown after loss" value={`${policy.cooldown_after_loss_minutes} min`} />
          <div className="mt-1 flex items-center justify-between border-t border-border-subtle pt-3 text-xs">
            <span className="text-text-secondary">Status</span>
            <span
              className="font-semibold"
              style={{ color: policy.enabled ? "var(--color-positive)" : "var(--color-negative)" }}
            >
              {policy.enabled ? "ENABLED" : "PAUSED"}
            </span>
          </div>
        </section>
      </div>

      <section className="flex flex-col gap-3 rounded-md border border-border-subtle bg-bg-1 p-5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
          Recent Decisions
        </div>
        {evaluations.length === 0 ? (
          <EmptyState message="No risk evaluations yet — evaluate a signal from the Signal Center." />
        ) : (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {evaluations.map((evaluation) => (
              <li key={evaluation.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex items-center gap-3">
                  <span
                    className="text-xs font-bold uppercase tracking-wide"
                    style={{ color: DECISION_COLOR[evaluation.decision] }}
                  >
                    {evaluation.decision === "APPROVED" ? "Risk Approved" : "Risk Rejected"}
                  </span>
                  <span className="font-mono text-xs text-text-primary">{evaluation.symbol}</span>
                </div>
                <div className="flex items-center gap-3 text-right">
                  <span className="max-w-[280px] truncate text-[11px] text-text-tertiary">
                    {evaluation.decision === "REJECTED"
                      ? evaluation.reasons[0]
                      : evaluation.calculated_position_size
                        ? `${evaluation.calculated_position_size} sh @ ${evaluation.entry_price}`
                        : "—"}
                  </span>
                  <span className="font-mono text-[10px] text-text-tertiary">
                    {new Date(evaluation.evaluated_at).toLocaleTimeString()}
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

function PolicyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between text-xs">
      <span className="text-text-secondary">{label}</span>
      <span className="font-mono text-text-primary">{value}</span>
    </div>
  );
}
