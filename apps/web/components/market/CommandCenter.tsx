"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusTag, type MarketState } from "@/components/ui/StatusTag";
import { ApiError } from "@/lib/api";
import { type IndicatorPoint, getIndicatorSeries } from "@/lib/analysis";
import {
  type ActivityEvent,
  type ActivityEventType,
  type CommandCenterSnapshot,
  getCommandCenterSnapshot,
} from "@/lib/commandCenter";
import { type Asset, type SupportedInterval, getAssets } from "@/lib/marketData";
import { MarketStateVisualization } from "./MarketStateVisualization";
import { PriceChart } from "./PriceChart";

const REFRESH_INTERVAL_MS = 30_000;
const FALLBACK_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA"];
const INTERVALS: SupportedInterval[] = ["1m", "5m", "15m", "1h", "1d"];

const SIGNAL_COLOR: Record<string, string> = {
  BUY: "var(--color-positive)",
  SELL: "var(--color-negative)",
  HOLD: "var(--color-neutral-signal)",
};

const AI_ACTION_COLOR: Record<string, string> = {
  BUY: "var(--color-positive)",
  SELL: "var(--color-negative)",
  HOLD: "var(--color-neutral-signal)",
  NO_ACTION: "var(--color-text-tertiary)",
};

const UNCERTAINTY_COLOR: Record<string, string> = {
  LOW: "var(--color-positive)",
  MEDIUM: "var(--color-accent-amber)",
  HIGH: "var(--color-negative)",
};

const HEALTH_COLOR: Record<string, string> = {
  ok: "var(--color-positive)",
  down: "var(--color-negative)",
};

const ACTIVITY_META: Record<ActivityEventType, { label: string; href: string }> = {
  SIGNAL_GENERATED: { label: "Signal", href: "/signals" },
  RISK_APPROVED: { label: "Risk", href: "/risk" },
  RISK_REJECTED: { label: "Risk", href: "/risk" },
  AI_ANALYSIS_COMPLETED: { label: "AI Analyst", href: "/ai-analyst" },
  PAPER_ORDER_FILLED: { label: "Paper Trade", href: "/paper" },
  POSITION_CLOSED: { label: "Paper Trade", href: "/paper" },
};

function money(value: string, digits = 2): string {
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: digits,
  });
}

function pct(value: string, digits = 1): string {
  return `${Number(value).toFixed(digits)}%`;
}

function relativeTime(iso: string): string {
  const deltaMs = Date.now() - new Date(iso).getTime();
  const seconds = Math.max(Math.round(deltaMs / 1000), 0);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

/**
 * The MarketPilot Command Center (Phase 9) — the primary operational
 * dashboard, rebuilt on top of one aggregated snapshot
 * (`GET /api/v1/command-center`, docs/command-center.md) instead of the
 * ~10 separate per-panel requests the previous dashboard made. Every
 * value rendered below is either straight from that snapshot or a
 * deterministic derivation of it (a percentage, a relative time) —
 * nothing here is invented client-side.
 *
 * Refresh: polls the snapshot every 30s (REFRESH_INTERVAL_MS) plus
 * immediately on symbol/interval change — see docs/command-center.md
 * §"Refresh strategy" for why 30s and not a WebSocket at this scale.
 * A failed refresh keeps showing the last-good snapshot with a small
 * inline error, never a blank dashboard.
 */
export function CommandCenter() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [symbol, setSymbol] = useState("AAPL");
  const [interval, setInterval_] = useState<SupportedInterval>("1d");
  const [snapshot, setSnapshot] = useState<CommandCenterSnapshot | null>(null);
  const [chartPoints, setChartPoints] = useState<IndicatorPoint[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    getAssets()
      .then(setAssets)
      .catch(() => {
        // Falls back to the fixed symbol list; the panel below surfaces
        // its own error state if the selected symbol itself fails.
      });
  }, []);

  useEffect(() => {
    let cancelled = false;

    function load(isFirstLoad: boolean) {
      if (isFirstLoad) setLoading(true);
      Promise.all([
        getCommandCenterSnapshot({ symbol, interval, activityLimit: 15 }),
        getIndicatorSeries(symbol, { interval }),
      ])
        .then(([snapshotResult, seriesResult]) => {
          if (cancelled) return;
          setSnapshot(snapshotResult);
          setChartPoints(seriesResult.points);
          setRefreshError(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setRefreshError(err instanceof ApiError ? err.message : "Failed to refresh dashboard.");
        })
        .finally(() => {
          if (!cancelled && isFirstLoad) setLoading(false);
        });
    }

    load(true);
    const timer = window.setInterval(() => load(false), REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [symbol, interval, reloadToken]);

  const symbolOptions = assets.length > 0 ? assets.map((a) => a.symbol) : FALLBACK_SYMBOLS;

  if (loading) {
    return (
      <div className="flex flex-col gap-5">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-80" />
        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </div>
    );
  }

  if (!snapshot) {
    return (
      <ErrorState
        message={refreshError ?? "Failed to load the Command Center."}
        onRetry={() => setReloadToken((t) => t + 1)}
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <CommandCenterHeader
        symbol={symbol}
        symbolOptions={symbolOptions}
        onSymbolChange={setSymbol}
        interval={interval}
        onIntervalChange={setInterval_}
        generatedAt={snapshot.generated_at}
        systemHealth={snapshot.system_health}
        refreshError={refreshError}
      />

      {/* Hero row: this is the most important information on the
          screen, and visually dominates — full-width market overview +
          chart, paired with the signature Market State instrument. */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[2fr_1fr]">
        <MarketOverviewPanel snapshot={snapshot} chartPoints={chartPoints} />
        <MarketStateVisualization
          symbol={symbol}
          data={{
            features: snapshot.market.features,
            regime: snapshot.market.regime,
            candle_count: snapshot.market.candle_count,
            interval: snapshot.market.interval,
          }}
        />
      </div>

      <WatchlistStrip watchlist={snapshot.watchlist} />

      {/* Secondary row: AI Analyst, Risk, Paper Portfolio — each an
          authoritative summary of its own owning phase, side by side so
          none is visually mistaken for outranking the others. */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <AIAnalystSummary snapshot={snapshot} />
        <RiskOverviewPanel snapshot={snapshot} />
        <PaperPortfolioPanel snapshot={snapshot} />
      </div>

      {/* Tertiary row: signals (wide, scanning list) + activity (narrow,
          chronological feed). */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[3fr_2fr]">
        <ActiveSignalsPanel signals={snapshot.signals} />
        <RecentActivityFeed events={snapshot.recent_activity} />
      </div>
    </div>
  );
}

// --- header: symbol/interval controls, refresh state, system health ------

function CommandCenterHeader({
  symbol,
  symbolOptions,
  onSymbolChange,
  interval,
  onIntervalChange,
  generatedAt,
  systemHealth,
  refreshError,
}: {
  symbol: string;
  symbolOptions: string[];
  onSymbolChange: (s: string) => void;
  interval: SupportedInterval;
  onIntervalChange: (i: SupportedInterval) => void;
  generatedAt: string;
  systemHealth: CommandCenterSnapshot["system_health"];
  refreshError: string | null;
}) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="cc-symbol-select" className="text-sm text-text-secondary">
          Symbol
        </label>
        <select
          id="cc-symbol-select"
          value={symbol}
          onChange={(e) => onSymbolChange(e.target.value)}
          className="rounded-md border border-border-default bg-bg-1 px-3 py-1.5 text-sm text-text-primary"
        >
          {symbolOptions.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          id="cc-interval-select"
          aria-label="Interval"
          value={interval}
          onChange={(e) => onIntervalChange(e.target.value as SupportedInterval)}
          className="rounded-md border border-border-default bg-bg-1 px-3 py-1.5 text-sm text-text-primary"
        >
          {INTERVALS.map((i) => (
            <option key={i} value={i}>
              {i}
            </option>
          ))}
        </select>
        <span className="text-[11px] text-text-tertiary" aria-live="polite">
          Updated {relativeTime(generatedAt)} &middot; refreshes every 30s
        </span>
        {refreshError && (
          <span className="text-[11px] text-negative">Last refresh failed: {refreshError}</span>
        )}
      </div>
      <SystemHealthStrip health={systemHealth} />
    </div>
  );
}

function SystemHealthStrip({ health }: { health: CommandCenterSnapshot["system_health"] }) {
  const items: { label: string; status: string }[] = [
    { label: "API", status: health.api },
    { label: "Database", status: health.database },
    { label: "Redis", status: health.redis },
    { label: "Market Data", status: health.market_data },
    { label: "AI Provider", status: health.ai.available ? "ok" : "unavailable" },
  ];
  return (
    <div
      className="flex flex-wrap items-center gap-3 rounded-full border border-border-subtle bg-bg-1 px-3 py-1.5"
      role="status"
      aria-label="System health"
    >
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5 text-[11px]">
          <span
            aria-hidden="true"
            className="h-1.5 w-1.5 rounded-full motion-safe:transition-colors"
            style={{ backgroundColor: HEALTH_COLOR[item.status] ?? "var(--color-text-tertiary)" }}
          />
          <span className="text-text-secondary">{item.label}</span>
          <span
            className="font-mono font-semibold"
            style={{ color: HEALTH_COLOR[item.status] ?? "var(--color-text-tertiary)" }}
          >
            {item.status.toUpperCase()}
          </span>
        </span>
      ))}
    </div>
  );
}

// --- hero: market overview + chart ----------------------------------------

function MarketOverviewPanel({
  snapshot,
  chartPoints,
}: {
  snapshot: CommandCenterSnapshot;
  chartPoints: IndicatorPoint[] | null;
}) {
  const { market } = snapshot;
  return (
    <Card eyebrow="Market Overview" mock className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <span className="text-2xl font-bold text-text-primary">{market.symbol}</span>
          <span className="font-mono text-xl text-text-primary">
            {market.price.close.toFixed(2)}
          </span>
          <StatusTag state={market.regime.regime as MarketState} />
        </div>
        <span className="text-[11px] text-text-tertiary">
          {market.interval} &middot; as of {new Date(market.price.timestamp).toLocaleString()}
          {market.is_mock && <span className="ml-1.5 text-text-tertiary">(SOURCE: MOCK)</span>}
        </span>
      </div>

      {chartPoints ? (
        <PriceChart points={chartPoints} />
      ) : (
        <Skeleton className="h-48" />
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-border-subtle pt-3 text-[11px] sm:grid-cols-3">
        <Fact label="Trend" value={market.features.trend_direction ?? "unavailable"} />
        <Fact
          label="Trend alignment"
          value={market.features.trend_alignment_label ?? "unavailable"}
        />
        <Fact label="Momentum (RSI)" value={market.features.rsi_state ?? "unavailable"} />
        <Fact label="Volume" value={market.features.volume_state ?? "unavailable"} />
        <Fact label="Volatility" value={market.features.volatility_state ?? "unavailable"} />
        <Fact label="Candles analyzed" value={String(market.candle_count)} />
      </div>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="uppercase tracking-wider text-text-tertiary">{label}</span>
      <span className="font-mono text-text-primary">{value}</span>
    </div>
  );
}

// --- watchlist strip --------------------------------------------------------

function WatchlistStrip({ watchlist }: { watchlist: CommandCenterSnapshot["watchlist"] }) {
  if (watchlist.length === 0) {
    return (
      <Card eyebrow="Watchlist" mock>
        <EmptyState message="No watchlist quotes available right now." />
      </Card>
    );
  }
  return (
    <Card eyebrow="Watchlist" mock>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {watchlist.map((quote) => {
          const changePct = quote.change_pct === null ? null : Number(quote.change_pct);
          const positive = changePct !== null && changePct >= 0;
          return (
            <div
              key={quote.symbol}
              className="flex flex-col gap-1 rounded-md border border-border-subtle bg-bg-2 p-3"
            >
              <span className="text-sm font-semibold text-text-primary">{quote.symbol}</span>
              <span className="font-mono text-sm text-text-primary">
                {Number(quote.close).toFixed(2)}
              </span>
              <span
                className="font-mono text-xs"
                style={{ color: changePct === null ? "var(--color-text-tertiary)" : positive ? "var(--color-positive)" : "var(--color-negative)" }}
              >
                {changePct === null ? "unavailable" : `${positive ? "+" : ""}${changePct.toFixed(2)}%`}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// --- AI Analyst summary ------------------------------------------------------

function AIAnalystSummary({ snapshot }: { snapshot: CommandCenterSnapshot }) {
  const { ai_analyses, signals, system_health } = snapshot;

  if (!system_health.ai.available) {
    return (
      <Card eyebrow="AI Analyst">
        <EmptyState message="AI Analyst unavailable — configure the Claude provider to enable analysis." />
      </Card>
    );
  }

  const latest = ai_analyses[0];
  if (!latest) {
    return (
      <Card eyebrow="AI Analyst">
        <EmptyState message="No AI analyses yet — run one from the AI Analyst screen." />
      </Card>
    );
  }

  const matchedSignal = signals.find((s) => s.id === latest.signal_id);
  const disagrees = matchedSignal !== undefined && matchedSignal.signal !== latest.suggested_action;

  return (
    <Card eyebrow="AI Analyst">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-text-primary">{latest.symbol}</span>
          <div className="flex items-center gap-2">
            <span
              className="text-xs font-bold uppercase tracking-wide"
              style={{ color: AI_ACTION_COLOR[latest.suggested_action] }}
            >
              {latest.suggested_action}
            </span>
            <span
              className="rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
              style={{
                color: UNCERTAINTY_COLOR[latest.uncertainty],
                borderColor: UNCERTAINTY_COLOR[latest.uncertainty],
              }}
            >
              {latest.uncertainty}
            </span>
          </div>
        </div>

        <p className="line-clamp-3 text-[11px] text-text-secondary">{latest.thesis}</p>

        <div className="flex items-center justify-between border-t border-border-subtle pt-2 text-[11px]">
          <span className="text-text-tertiary">Deterministic signal</span>
          <span className="font-mono text-text-primary">{matchedSignal?.signal ?? "unavailable"}</span>
        </div>

        {disagrees && (
          <div className="rounded-sm border border-accent-amber px-2 py-1 text-[10px] font-semibold text-accent-amber">
            ANALYSIS DISAGREEMENT — AI and signal differ
          </div>
        )}

        <Link href="/ai-analyst" className="text-[11px] text-accent-teal hover:underline">
          Open AI Analyst Center &rarr;
        </Link>
      </div>
    </Card>
  );
}

// --- Risk Overview -----------------------------------------------------------

function RiskOverviewPanel({ snapshot }: { snapshot: CommandCenterSnapshot }) {
  const { portfolio, policy } = snapshot.risk;
  const exposureValue = Number(portfolio.open_position_value);
  const exposureLimit = exposureValue + Number(portfolio.available_exposure_value);
  const exposurePct = exposureLimit > 0 ? (exposureValue / exposureLimit) * 100 : 0;
  const drawdownPct = Number(portfolio.drawdown_pct);
  const drawdownLimit = Number(policy.max_drawdown_pct);

  return (
    <Card eyebrow="Risk Overview">
      <div className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <span className="text-xs text-text-secondary">Equity</span>
          <span className="font-mono text-lg text-text-primary">{money(portfolio.equity, 0)}</span>
        </div>
        <LimitBar
          label="Exposure"
          ratio={exposurePct}
          currentLabel={money(String(exposureValue), 0)}
          limitLabel={money(String(exposureLimit), 0)}
        />
        <LimitBar
          label="Drawdown"
          ratio={drawdownLimit > 0 ? (drawdownPct / drawdownLimit) * 100 : 0}
          currentLabel={pct(portfolio.drawdown_pct)}
          limitLabel={pct(policy.max_drawdown_pct, 0)}
        />
        <div className="flex items-baseline justify-between text-[11px]">
          <span className="text-text-tertiary">Daily P/L</span>
          <span
            className="font-mono"
            style={{
              color:
                Number(portfolio.realized_pl_today) >= 0
                  ? "var(--color-positive)"
                  : "var(--color-negative)",
            }}
          >
            {money(portfolio.realized_pl_today, 0)}
          </span>
        </div>
        <div className="flex items-baseline justify-between text-[11px]">
          <span className="text-text-tertiary">Concurrent positions</span>
          <span className="font-mono text-text-primary">
            {portfolio.open_position_count} / {policy.max_concurrent_positions}
          </span>
        </div>
        <div className="flex items-baseline justify-between border-t border-border-subtle pt-2 text-[11px]">
          <span className="text-text-tertiary">Active policy</span>
          <span className="font-mono text-text-primary">
            {policy.name} v{policy.version} &middot; {policy.enabled ? "ENABLED" : "PAUSED"}
          </span>
        </div>
        <Link href="/risk" className="text-[11px] text-accent-teal hover:underline">
          Open Risk Center &rarr;
        </Link>
      </div>
    </Card>
  );
}

function LimitBar({
  label,
  ratio,
  currentLabel,
  limitLabel,
}: {
  label: string;
  ratio: number;
  currentLabel: string;
  limitLabel: string;
}) {
  const clamped = Math.min(Math.max(ratio, 0), 100);
  const nearLimit = clamped >= 80;
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-[11px]">
        <span className="text-text-secondary">{label}</span>
        <span className="font-mono text-text-primary">
          {currentLabel} / {limitLabel}
        </span>
      </div>
      <div className="h-1.5 rounded-sm bg-bg-3">
        <div
          className="h-full rounded-sm motion-safe:transition-[width] motion-safe:duration-500"
          style={{
            width: `${clamped}%`,
            backgroundColor: nearLimit ? "var(--color-accent-amber)" : "var(--color-accent-teal)",
          }}
        />
      </div>
    </div>
  );
}

// --- Paper Portfolio ---------------------------------------------------------

function PaperPortfolioPanel({ snapshot }: { snapshot: CommandCenterSnapshot }) {
  const { portfolio, positions, recent_fills: recentFills } = snapshot;
  const dailyPnl = Number(portfolio.daily_pnl);

  return (
    <Card eyebrow="Paper Portfolio">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-2xl font-semibold text-text-primary">
            {money(portfolio.equity)}
          </span>
          <span className="rounded-sm border border-border-default px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">
            Paper Trading
          </span>
        </div>
        <div className="flex gap-3 font-mono text-[11px]">
          <span style={{ color: dailyPnl >= 0 ? "var(--color-positive)" : "var(--color-negative)" }}>
            {dailyPnl >= 0 ? "+" : ""}
            {money(portfolio.daily_pnl)} today
          </span>
          <span className="text-text-tertiary">{money(portfolio.unrealized_pnl)} unrealized</span>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 border-t border-border-subtle pt-2 text-[11px]">
          <Fact label="Cash" value={money(portfolio.cash, 0)} />
          <Fact label="Market value" value={money(portfolio.market_value, 0)} />
          <Fact label="Realized P/L" value={money(portfolio.realized_pnl_total, 0)} />
          <Fact label="Open positions" value={String(portfolio.open_position_count)} />
        </div>

        {positions.length > 0 ? (
          <ul className="flex flex-col gap-1 border-t border-border-subtle pt-2 text-[11px]">
            {positions.slice(0, 4).map((p) => (
              <li key={p.id} className="flex items-center justify-between">
                <span className="text-text-secondary">{p.symbol}</span>
                <span
                  className="font-mono"
                  style={{
                    color:
                      Number(p.unrealized_pnl) >= 0
                        ? "var(--color-positive)"
                        : "var(--color-negative)",
                  }}
                >
                  {money(p.unrealized_pnl, 0)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="border-t border-border-subtle pt-2 text-[11px] text-text-tertiary">
            No open positions.
          </p>
        )}

        {recentFills.length === 0 && (
          <p className="text-[11px] text-text-tertiary">No fills yet.</p>
        )}

        <Link href="/paper" className="text-[11px] text-accent-teal hover:underline">
          Open Paper Trading Center &rarr;
        </Link>
      </div>
    </Card>
  );
}

// --- Active Signals -----------------------------------------------------------

function ActiveSignalsPanel({ signals }: { signals: CommandCenterSnapshot["signals"] }) {
  return (
    <Card eyebrow="Active Signals">
      {signals.length === 0 ? (
        <EmptyState message="No signals yet — evaluate one from the Signal Center." />
      ) : (
        <ul className="flex flex-col divide-y divide-border-subtle">
          {signals.map((signal) => (
            <li key={signal.id} className="flex items-center justify-between gap-3 py-2.5 text-xs">
              <div className="flex items-center gap-3">
                <span
                  className="font-bold uppercase tracking-wide"
                  style={{ color: SIGNAL_COLOR[signal.signal] }}
                >
                  {signal.signal}
                </span>
                <span className="font-mono text-text-primary">{signal.symbol}</span>
                <span className="text-text-tertiary">{signal.strength ?? "—"}</span>
              </div>
              <div className="flex items-center gap-3">
                <SignalStatusTag status={signal.status} />
                <span className="font-mono text-[10px] text-text-tertiary">
                  {relativeTime(signal.generated_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

const SIGNAL_STATUS_COLOR: Record<string, string> = {
  CANDIDATE: "var(--color-neutral-signal)",
  RISK_APPROVED: "var(--color-positive)",
  RISK_REJECTED: "var(--color-negative)",
  EXPIRED: "var(--color-text-tertiary)",
  SUPERSEDED: "var(--color-text-tertiary)",
};

function SignalStatusTag({ status }: { status: string }) {
  return (
    <span
      className="rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
      style={{
        color: SIGNAL_STATUS_COLOR[status] ?? "var(--color-text-tertiary)",
        borderColor: SIGNAL_STATUS_COLOR[status] ?? "var(--color-text-tertiary)",
      }}
    >
      {status.replace("_", " ")}
    </span>
  );
}

// --- Recent Activity -----------------------------------------------------------

function RecentActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <Card eyebrow="Recent Activity">
      {events.length === 0 ? (
        <EmptyState message="No activity yet — nothing has happened this session." />
      ) : (
        <ul className="flex flex-col divide-y divide-border-subtle">
          {events.map((event, index) => {
            const meta = ACTIVITY_META[event.type];
            return (
              <li key={`${event.type}-${event.timestamp}-${index}`} className="py-2.5 text-xs">
                <Link href={meta.href} className="flex flex-col gap-0.5 hover:opacity-80">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-text-tertiary">
                      {meta.label}
                    </span>
                    <span className="font-mono text-[10px] text-text-tertiary">
                      {relativeTime(event.timestamp)}
                    </span>
                  </div>
                  <span className="text-text-secondary">{event.summary}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
