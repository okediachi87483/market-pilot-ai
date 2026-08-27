import { StatusTag, type MarketState } from "@/components/ui/StatusTag";
import type { PaperOrder } from "@/lib/paperTrading";
import type { RiskEvaluation } from "@/lib/risk";
import type { SignalResponse, SignalStrength, SignalType } from "@/lib/signals";

const SIGNAL_COLOR: Record<SignalType, string> = {
  BUY: "var(--color-positive)",
  SELL: "var(--color-negative)",
  HOLD: "var(--color-neutral-signal)",
};

const STRENGTH_COLOR: Record<SignalStrength, string> = {
  STRONG: "var(--color-accent-teal)",
  MODERATE: "var(--color-text-secondary)",
  WEAK: "var(--color-text-tertiary)",
};

const DECISION_COLOR: Record<RiskEvaluation["decision"], string> = {
  APPROVED: "var(--color-positive)",
  REJECTED: "var(--color-negative)",
};

type LifecycleStage =
  | "CANDIDATE"
  | "RISK_REVIEW"
  | "RISK_APPROVED"
  | "RISK_REJECTED"
  | "FILLED"
  | "EXECUTION_FAILED";

function currentStage(
  signal: SignalResponse,
  riskEvaluation: RiskEvaluation | null,
  paperOrder: PaperOrder | null,
): LifecycleStage {
  if (paperOrder) return paperOrder.status === "FILLED" ? "FILLED" : "EXECUTION_FAILED";
  if (riskEvaluation) return riskEvaluation.decision === "APPROVED" ? "RISK_APPROVED" : "RISK_REJECTED";
  if (signal.status === "RISK_APPROVED" || signal.status === "RISK_REJECTED") {
    return signal.status;
  }
  return "CANDIDATE";
}

/**
 * The full signal lifecycle stepper (Step 22/25): Candidate -> Risk
 * Review -> Risk Approved -> Filled (Position Open), branching to Risk
 * Rejected or Execution Failed. Plain text + muted color, not a flashy
 * progress animation — this documents where a candidate is in a
 * deterministic pipeline, not a countdown to a payout.
 */
function LifecycleStepper({ stage }: { stage: LifecycleStage }) {
  const branch: { key: LifecycleStage; label: string } =
    stage === "RISK_REJECTED"
      ? { key: "RISK_REJECTED", label: "Risk Rejected" }
      : stage === "EXECUTION_FAILED"
        ? { key: "EXECUTION_FAILED", label: "Execution Failed" }
        : stage === "FILLED"
          ? { key: "FILLED", label: "Position Open" }
          : { key: "RISK_APPROVED", label: "Risk Approved" };

  const steps: { key: LifecycleStage; label: string }[] = [
    { key: "CANDIDATE", label: "Candidate" },
    { key: "RISK_REVIEW", label: "Risk Review" },
    branch,
  ];
  const activeIndex = steps.findIndex((step) => step.key === stage);
  const isFailureBranch = stage === "RISK_REJECTED" || stage === "EXECUTION_FAILED";

  return (
    <div className="flex items-center gap-2 text-[11px]" data-testid="lifecycle-stepper">
      {steps.map((step, index) => {
        const isActive = index === activeIndex;
        const isPast = index < activeIndex;
        const isFailure = isFailureBranch && step.key === branch.key;
        const color =
          isActive || isPast
            ? isFailure
              ? "var(--color-negative)"
              : "var(--color-accent-teal)"
            : "var(--color-text-tertiary)";
        return (
          <div key={step.key} className="flex items-center gap-2">
            <span className="font-semibold uppercase tracking-wider" style={{ color }}>
              {step.label}
            </span>
            {index < steps.length - 1 && <span className="text-text-tertiary">&rarr;</span>}
          </div>
        );
      })}
    </div>
  );
}

/**
 * The professional Signal Center card (Step 13/22/25) — precise and
 * disciplined, never celebratory. No color-flashing, no emoji, no
 * "you're about to win" framing: STRONG uses the same restrained teal
 * accent as any other emphasized value elsewhere in the design system,
 * not gold or flashing green. This is a deterministic strategy's
 * *suggestion*, presented with its full reasoning — a filled paper
 * order is always labeled "Simulated Fill," never "trade executed"
 * without qualification (Step 19/23).
 */
export function SignalCard({
  signal,
  riskEvaluation = null,
  onRunRiskReview,
  riskReviewLoading = false,
  riskReviewError = null,
  paperOrder = null,
  onExecutePaperOrder,
  paperExecutionLoading = false,
  paperExecutionError = null,
}: {
  signal: SignalResponse;
  riskEvaluation?: RiskEvaluation | null;
  onRunRiskReview?: () => void;
  riskReviewLoading?: boolean;
  riskReviewError?: string | null;
  paperOrder?: PaperOrder | null;
  onExecutePaperOrder?: () => void;
  paperExecutionLoading?: boolean;
  paperExecutionError?: string | null;
}) {
  const stage = currentStage(signal, riskEvaluation, paperOrder);
  const canRunRiskReview = signal.status === "CANDIDATE" && !riskEvaluation && onRunRiskReview;
  const canExecutePaperOrder =
    riskEvaluation?.decision === "APPROVED" && !paperOrder && onExecutePaperOrder;

  return (
    <section className="flex flex-col gap-4 rounded-md border border-border-subtle bg-bg-1 p-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xl font-bold text-text-primary">{signal.symbol}</div>
          <div className="text-[11px] text-text-tertiary">
            {signal.strategy_label} &middot; {signal.interval}
          </div>
        </div>
        <StatusTag state={signal.market_regime as MarketState} />
      </div>

      <div className="flex items-center gap-3">
        <span
          className="text-2xl font-bold tracking-wide"
          style={{ color: SIGNAL_COLOR[signal.signal] }}
        >
          {signal.signal}
        </span>
        {signal.strength && (
          <span
            className="rounded-sm border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider"
            style={{
              color: STRENGTH_COLOR[signal.strength],
              borderColor: STRENGTH_COLOR[signal.strength],
            }}
          >
            {signal.strength}
          </span>
        )}
      </div>

      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
          Why this signal exists
        </div>
        <ul className="flex flex-col gap-1.5">
          {signal.reasons.map((reason) => (
            <li key={reason} className="flex gap-2 text-xs text-text-secondary">
              <svg width="12" height="12" viewBox="0 0 20 20" className="mt-0.5 shrink-0 text-positive" aria-hidden="true">
                <path d="M4 10 L8 14 L16 5" fill="none" stroke="currentColor" strokeWidth="2" />
              </svg>
              {reason}
            </li>
          ))}
        </ul>
      </div>

      {signal.invalidating_conditions.length > 0 && (
        <div>
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
            Invalidated if
          </div>
          <ul className="flex flex-col gap-1.5">
            {signal.invalidating_conditions.map((condition) => (
              <li key={condition} className="flex gap-2 text-xs text-text-secondary">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-text-tertiary" aria-hidden="true" />
                {condition}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-3 border-t border-border-subtle pt-3">
        <LifecycleStepper stage={stage} />

        {canRunRiskReview && (
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={onRunRiskReview}
              disabled={riskReviewLoading}
              className="self-start rounded-md border border-border-default bg-bg-2 px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-bg-3 disabled:opacity-50"
            >
              {riskReviewLoading ? "Running risk review…" : "Run Risk Review"}
            </button>
            {riskReviewError && <p className="text-xs text-negative">{riskReviewError}</p>}
          </div>
        )}

        {riskEvaluation && riskEvaluation.decision === "APPROVED" && !paperOrder && (
          <div className="flex flex-col gap-2 rounded-md border border-border-subtle bg-bg-2 p-3">
            <div
              className="text-xs font-bold uppercase tracking-wide"
              style={{ color: DECISION_COLOR.APPROVED }}
            >
              Risk Approved &middot; Paper Trade Eligible
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
              <RiskFact label="Position size" value={riskEvaluation.calculated_position_size} />
              <RiskFact label="Entry" value={riskEvaluation.entry_price} />
              <RiskFact label="Stop loss" value={riskEvaluation.stop_loss_price} />
              <RiskFact label="Take profit" value={riskEvaluation.take_profit_price} />
            </dl>
            <div className="text-[10px] text-text-tertiary">
              Policy v{riskEvaluation.policy_version} &middot; no paper trade has been placed yet.
            </div>
            {canExecutePaperOrder && (
              <div className="mt-1 flex flex-col gap-2">
                <button
                  type="button"
                  onClick={onExecutePaperOrder}
                  disabled={paperExecutionLoading}
                  className="self-start rounded-md border border-border-default bg-bg-2 px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-bg-3 disabled:opacity-50"
                >
                  {paperExecutionLoading ? "Executing paper order…" : "Execute Paper Order"}
                </button>
                {paperExecutionError && <p className="text-xs text-negative">{paperExecutionError}</p>}
              </div>
            )}
          </div>
        )}

        {riskEvaluation && riskEvaluation.decision === "REJECTED" && (
          <div className="flex flex-col gap-2 rounded-md border border-border-subtle bg-bg-2 p-3">
            <div
              className="text-xs font-bold uppercase tracking-wide"
              style={{ color: DECISION_COLOR.REJECTED }}
            >
              Risk Rejected
            </div>
            <ul className="flex flex-col gap-1">
              {riskEvaluation.reasons.map((reason) => (
                <li key={reason} className="text-[11px] text-text-secondary">
                  {reason}
                </li>
              ))}
            </ul>
            {riskEvaluation.checks.some((check) => !check.passed && !check.skipped) && (
              <div className="mt-1 text-[10px] text-text-tertiary">
                Failed checks:{" "}
                {riskEvaluation.checks
                  .filter((check) => !check.passed && !check.skipped)
                  .map((check) => check.name)
                  .join(", ")}
              </div>
            )}
          </div>
        )}

        {paperOrder && paperOrder.status === "FILLED" && (
          <div className="flex flex-col gap-2 rounded-md border border-border-subtle bg-bg-2 p-3">
            <div className="text-xs font-bold uppercase tracking-wide" style={{ color: "var(--color-positive)" }}>
              Simulated Fill &middot; Position Open
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
              <RiskFact label="Filled quantity" value={paperOrder.filled_quantity} />
              <RiskFact label="Fill price" value={paperOrder.average_fill_price} />
            </dl>
            <div className="text-[10px] text-text-tertiary">
              Simulated order — no real money moved. See Paper Trading for the full position.
            </div>
          </div>
        )}

        {paperOrder && paperOrder.status !== "FILLED" && (
          <div className="flex flex-col gap-2 rounded-md border border-border-subtle bg-bg-2 p-3">
            <div className="text-xs font-bold uppercase tracking-wide" style={{ color: "var(--color-negative)" }}>
              Execution Failed
            </div>
            <p className="text-[11px] text-text-secondary">
              {paperOrder.rejection_reason ?? "The simulated order was not filled."}
            </p>
          </div>
        )}

        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-text-tertiary">Status</span>
          <span className="font-mono text-xs text-text-primary">{signal.status}</span>
        </div>
      </div>
    </section>
  );
}

function RiskFact({ label, value }: { label: string; value: string | null }) {
  return (
    <>
      <dt className="text-text-tertiary">{label}</dt>
      <dd className="text-right font-mono text-text-primary">{value ?? "—"}</dd>
    </>
  );
}
