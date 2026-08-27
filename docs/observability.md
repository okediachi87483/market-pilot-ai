# MarketPilot AI — Observability

MarketPilot is a monitoring system; it would be a poor one if it couldn't monitor itself. This document defines logs, metrics, traces, and health checks, and the metrics specific to a pipeline whose stages include an LLM call and a deterministic financial gate.

## 1. Structured logging

Every package logs structured JSON (not free-text) via a shared logger from `packages/shared/logging.py` — one configuration, one format, everywhere. Minimum fields on every log line: `timestamp`, `level`, `service` (package name), `message`, `request_id` (propagated from the API layer through the pipeline for a given cycle), and `user_id` where applicable. Secret-shaped values are redacted (see [security.md](security.md) §8). Logs ship to stdout/stderr in every environment (container-native) and are collected by the deployment platform's log aggregation rather than the application writing to files.

## 2. Metrics (Prometheus)

> **Status**: this section remains the Phase 1 plan — no phase through Phase 8 has wired up a `/metrics` endpoint or a Prometheus client library; that work is Phase 14 ("Observability (Prometheus/Grafana)" in the roadmap). Structured logging (§1) is real today for every phase, including the AI Analyst (docs/ai-analyst.md §16). The AI-specific metric names below (`marketpilot_ai_analysis_duration_seconds`, `marketpilot_ai_provider_errors_total`, `marketpilot_ai_tokens_total`) are the intended names *when* Phase 14 lands — Phase 8 deliberately did not add metrics infrastructure just for its own endpoints, matching the "proportional, no unnecessary infra" guidance for this phase specifically.

Exposed at `/metrics` on the API process (and the scheduler process once split out per [architecture.md](architecture.md) §9), scraped by Prometheus, visualized in Grafana.

| Metric | Type | Why it matters |
|---|---|---|
| `marketpilot_market_data_latency_seconds` | Histogram | Time from provider request to normalized `MarketData` write — flags a slow or degrading provider before it becomes a stale-data problem. |
| `marketpilot_api_request_duration_seconds` | Histogram, labeled by route + method | Standard API latency; the number a user actually feels. |
| `marketpilot_ai_analysis_duration_seconds` | Histogram | LLM call latency — the pipeline's slowest, most variable step; needs its own visibility separate from general API latency. |
| `marketpilot_signals_generated_total` | Counter, labeled by direction | Volume of deterministic signal output over time. |
| `marketpilot_orders_approved_total` / `marketpilot_orders_rejected_total` | Counter, labeled by rejection reason on the latter | Risk engine behavior — a sudden spike in rejections is either a market regime change or a misconfigured rule, and this metric is how you'd notice either. |
| `marketpilot_paper_trades_total` | Counter | Trading activity volume. |
| `marketpilot_portfolio_win_rate` | Gauge, per portfolio | Surfaced directly from the same computation backing `GET /portfolio`. |
| `marketpilot_portfolio_drawdown_pct` | Gauge, per portfolio | Feeds both the dashboard and an alerting rule on the metric itself (independent of the in-app [profit-protection.md](profit-protection.md) alerts — an infra-level watch on the same number). |
| `marketpilot_portfolio_pl_total` | Gauge, per portfolio | Realized + unrealized P/L. |
| `marketpilot_error_rate` | Counter, labeled by service + error type | Cross-cutting error visibility, one place to look regardless of which package failed. |
| `marketpilot_ai_provider_errors_total` | Counter, labeled by error type (timeout/schema_invalid/provider_error) | Distinguishes "the model gave a bad answer" from "the model didn't answer" from "we can't reach the provider" — each has a different fix. |

## 3. Traces

OpenTelemetry instrumentation on the API process and the pipeline scheduler, exported to whatever backend the deployment target supports (deferred choice — Grafana Tempo is the natural pairing with the rest of this stack if self-hosted, otherwise a managed APM). Priority spans: the full pipeline cycle (ingest → ... → alert) as one trace with a child span per stage, so a slow cycle is attributable to a specific stage without cross-referencing logs by timestamp. Traces are the "where exactly did the time go" tool; metrics are the "is something wrong right now" tool — both are kept, neither substitutes for the other.

## 4. Health checks

Three distinct checks, not one:

| Check | Endpoint / mechanism | Answers |
|---|---|---|
| **Liveness** | `GET /health` returns `200` whenever the process is running and able to respond at all | "Should this process be restarted?" |
| **Readiness** | Same endpoint's body reports `db`/`redis` connectivity (`ok`/`down`); orchestration treats a `down` dependency as not-ready | "Should this instance receive traffic right now?" |
| **Pipeline health** | A separate internal check (surfaced as a metric, `marketpilot_pipeline_last_success_timestamp`) tracking when the scheduler last completed a full cycle | "Is the system actually doing its job," which liveness/readiness alone can't answer — a process can be perfectly alive and ready while its scheduler is silently stuck. |

## 5. Stage-specific monitoring

- **Market data**: `marketpilot_market_data_latency_seconds`, plus a staleness gauge (`marketpilot_market_data_age_seconds` per asset) so a stalled provider is visible even between ingestion attempts, not just at request time.
- **AI requests**: `marketpilot_ai_analysis_duration_seconds`, `marketpilot_ai_provider_errors_total`, and a cost-adjacent counter (`marketpilot_ai_tokens_total`, labeled input/output) since LLM calls are the one variable-cost dependency in the pipeline.
- **Signal generation**: `marketpilot_signals_generated_total`; alerting on this hitting zero across a window that should have produced signals is as important as alerting on errors — a silently-broken rule set fails by producing nothing, not by throwing.
- **Risk engine**: `marketpilot_orders_approved_total` / `_rejected_total` with rejection-reason labels; a rule change that starts rejecting everything (or approving everything) shows up here before it shows up as a user complaint.
- **Paper trading**: `marketpilot_paper_trades_total`, plus fill-to-request latency (should be near-instant for a simulated fill — a regression here indicates a bug, not real market conditions).

## 6. Dashboards

Two Grafana dashboards ship in `infrastructure/monitoring/`: an **operational** dashboard (latency, error rate, health, pipeline cycle status — for "is the system working") and a **product** dashboard (signals, approval/rejection rates, win rate, drawdown, P/L — for "is the strategy working"), kept separate because they answer different questions for different moments, even though one team operates both in the MVP.
