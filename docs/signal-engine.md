# MarketPilot AI — Signal Engine

Phase 5. Turns Phase 4's technical-analysis output (regime + features) into a structured trade *candidate* — a suggestion another system can evaluate, never an instruction that executes. **No AI, no broker access, no order placement, no autonomous financial decision anywhere in this layer.**

## 1. Architecture

```
MARKET DATA (Phase 3)
        │
        ▼
TECHNICAL ANALYSIS (Phase 4)  — regime + features
        │
        ▼
SignalEngine.evaluate()        — app/services/signal_engine/engine.py
        │
        ▼
SignalCandidate (status: CANDIDATE)
        │
        ▼
SignalService                  — cooldown/dedup, persistence
        │
        ▼
Signal (Postgres)
        │
        ▼
API (docs/api.md) → Signal Center UI
        │
        ▼
(future) RiskEvaluationRequest → RiskEngine → APPROVED / REJECTED   [Phase 6, not built yet]
```

`app/services/signal_engine/` is independent of FastAPI, the database, and AI (Step 2): `rules.py`, `scoring.py`, and `engine.py` take a plain `SignalInput` dataclass in and return a plain `SignalCandidate` dataclass out — no I/O, no randomness. `SignalService` is the only piece that knows about the database, `TechnicalAnalysisService`, or cooldown state.

## 2. Signal types (Step 3)

`BUY`, `SELL`, `HOLD`. No `SHORT` — nothing in the existing architecture (paper trading isn't built yet, and Phase 1's `ADR-007` commits to long/short architecture being decided when paper trading actually lands) gives a strong reason to add it now, and Step 3 explicitly says not to without one.

**What `SELL` means**: a potential exit/reduce signal for a position that may exist — never an instruction to liquidate an account, and never connected to any real holding (there is no paper trading yet either — Phase 7). It carries the same weight as `BUY`: a detected condition worth reviewing, gated by the same quality filters.

## 3. Strategy: `trend_momentum`

One strategy, versioned (Step 5): `strategy_id = "trend_momentum"`, `strategy_version = "1.0.0"`, displayed as `trend_momentum_v1`. Combines TREND, MOMENTUM, VOLUME, and MARKET REGIME (VOLATILITY is folded in — see the note in rule 3 below) using the **actual** Phase 4 feature names (`docs/technical-analysis.md`), not invented ones.

### Rules (precedence order — first match wins)

Implemented in `app/services/signal_engine/rules.py`:

| # | Condition | Result |
|---|---|---|
| 1 | `regime == INSUFFICIENT_DATA` | `HOLD` — no directional read possible |
| 2 | `regime == SIDEWAYS` | `HOLD` — no dominant trend |
| 3 | `regime == HIGH_VOLATILITY` | `HOLD` — avoiding entries during a volatility event |
| 4 | `regime == LOW_VOLATILITY` | `HOLD` — no directional catalyst |
| 5 | `regime == BULLISH` and `macd_state != "bullish"` | `HOLD` — conflicting indicators |
| 6 | `regime == BULLISH` and `rsi14` unavailable | `HOLD` — momentum data unavailable |
| 7 | `regime == BULLISH` and `rsi14 > 80` | `HOLD` — extremely overbought, avoiding a late entry |
| 8 | `regime == BULLISH` and `volume_state == "low"` | `HOLD` — insufficient participation |
| 9 | `regime == BULLISH` and none of the above | **`BUY`** |
| 10-13 | the exact mirror of 5-8 for `regime == BEARISH` (MACD not bearish / RSI unavailable / `rsi14 < 20` / low volume) | `HOLD` |
| 14 | `regime == BEARISH` and none of the above | **`SELL`** |

**Why volatility isn't re-checked in rules 5-9**: Phase 4's regime classifier (`docs/technical-analysis.md` §7) checks `HIGH_VOLATILITY` *before* `BULLISH`/`BEARISH`. Reaching rule 5 or later already structurally guarantees `volatility_state != "elevated"` — re-checking it would be dead code, not extra safety. This is a direct, deliberate consequence of building on Phase 4's classifier rather than a shortcut.

**RSI thresholds** (80/20) are intentionally stricter than Phase 4's own descriptive overbought/oversold thresholds (70/30, `docs/technical-analysis.md` §5) — a genuinely extreme reading is treated as a *signal-quality* filter (Step 8's "quality filters" requirement), while a merely-stretched reading (70-80, or 20-30) is allowed through and instead lowers the strength score (§5 below).

### Reasons (Step 6/11)

Every `BUY`/`SELL` candidate's `reasons` list is built from the specific conditions that held true — not a template disconnected from the actual evaluation. Example for a `BUY`:

```
"Detected market regime is BULLISH"
"Trend alignment is strong (bullish)"
"MACD is bullish (histogram positive)"
"RSI at 61.2 (neutral) — not extremely overbought"
"Volume is elevated, supporting the move"
```

Every `HOLD` also carries a reason (e.g. `"Regime is BULLISH but volume is low — insufficient participation to confirm the move"`) — a `HOLD` is never unexplained.

### Invalidating conditions (Step 6)

Structural, documented per signal type (not a live re-check on every request) — what would remove the basis for *this* signal:

- `BUY`: price loses EMA21 support · MACD turns bearish · regime shifts away from BULLISH · RSI becomes extremely overbought without follow-through.
- `SELL`: the exact mirror.

## 4. Signal strength (Step 7) — no fabricated probability

`STRONG` never means "87% chance of winning" — it means four independently-documented components all scored near their maximum. Computed in `app/services/signal_engine/scoring.py`, only for `BUY`/`SELL` (a `HOLD` has no strength — there's no directional conviction to score).

### Component scores (each 0-2)

| Component | Derivation |
|---|---|
| `trend` | Direct reuse of Phase 4's own `trend_alignment_score` (0/1/2). Reaching `BUY`/`SELL` already requires alignment ≥ 1, so this is 1 or 2 in practice, never 0. |
| `momentum` | `rsi_state == "neutral"` → 2; `"overbought"` or `"oversold"` (the extreme end already blocked by the rules) → 1. Symmetric by design — a stretched-but-valid RSI scores the same whether the setup is bullish or bearish. |
| `volume` | `"elevated"` → 2; `"normal"` → 1. (`"low"` is already excluded by the rules before scoring runs.) |
| `volatility` | `"normal"` → 2; `"low"` → 1. (`"elevated"` is structurally excluded by the regime gate — see §3.) |

### Strength formula

Sum of the four components (range 4-8 in practice):

| Total | Strength |
|---|---|
| ≤ 4 | `WEAK` |
| 5-6 | `MODERATE` |
| ≥ 7 | `STRONG` |

The full `score_breakdown` (the four component values) is available on the in-process `SignalCandidate` for transparency and is logged (§9); it is not currently a persisted database column (see §6) but is trivially re-derivable from the same `supporting_features` that *are* stored, since the score is a pure function of them.

## 5. Signal quality filters (Step 8)

A `HOLD` is a legitimate, expected output — not a failure state. The engine is not "forced to trade." Rules 1-4 (regime-level) and the MACD/RSI/volume checks within rules 5-13 are exactly this: insufficient data, a sideways market, a volatility event, conflicting indicators (regime says one thing, MACD another), and thin volume all produce `HOLD` rather than a low-conviction `BUY`/`SELL`.

## 6. Cooldown / deduplication (Step 9)

Re-evaluating a symbol repeatedly (`AAPL BUY` four times a minute apart) must not become four meaningful signals. Implemented in `SignalService._persist()`:

1. Look up the most recent `Signal` row with `status = CANDIDATE` for the same `(asset_id, interval, strategy_id, strategy_version)`.
2. If one exists, its `signal` value matches the newly-computed one, **and** it's less than `COOLDOWN` (15 minutes) old → return the existing row unchanged. No new row, no duplicate.
3. Otherwise (no existing candidate, the cooldown has elapsed, or the signal value has changed) → mark any existing `CANDIDATE` for that key `SUPERSEDED`, insert the new one as `CANDIDATE`.

This is a single process-local time window, not a distributed rate limiter or queue (Step 9 explicitly asks not to overcomplicate this yet). `COOLDOWN` is a module-level constant (`app/services/signal_engine/service.py`), easy to find and change.

## 7. Signal lifecycle and database (Step 10)

`Signal` (`app/models/signal.py`), Alembic-migrated. Statuses: `CANDIDATE`, `RISK_APPROVED`, `RISK_REJECTED`, `EXPIRED`, `SUPERSEDED`. **The Signal Engine only ever writes `CANDIDATE`** (on insert) or moves an old row to `SUPERSEDED` (as part of its own cooldown bookkeeping, §6) — it never writes `RISK_APPROVED`/`RISK_REJECTED`. Those belong exclusively to the future Risk Engine (§8); `EXPIRED` is reserved for a future time-based cleanup job, not written by anything yet.

Columns: `id`, `asset_id` (FK), `interval`, `signal`, `strategy_id`, `strategy_version`, `strength` (nullable), `market_regime`, `reasons` (JSONB array), `supporting_features` (JSONB object), `invalidating_conditions` (JSONB array), `status`, `generated_at` (the business/evaluation timestamp), `created_at` (row-insert time). `CHECK` constraints mirror the same enum sets as the Python-level `Literal` types. Indexes: `asset_id`, `created_at`, and a composite `(asset_id, interval, strategy_id, status)` matching the cooldown lookup's exact query shape.

### Why persist at all (unlike Phase 4's indicators)

Unlike technical-analysis indicators (deliberately *not* persisted — `docs/technical-analysis.md` §10), signals **are** persisted, because:

- Cooldown/dedup (§6) requires knowing what was already suggested and when — that's inherently stateful, not a pure recomputation.
- Auditability (§8/Step 11) requires a durable record of exactly what was suggested, with what reasoning, that a future Risk Engine decision can be traced back to.
- A signal is a *decision point* in the pipeline (something a user or a future Risk Engine reacts to), unlike an indicator value, which is purely descriptive input.

## 8. Auditability (Step 11)

Every persisted `Signal` row answers "why did MarketPilot generate this?" without needing to re-run anything: `strategy_id` + `strategy_version` pin the exact rule set (§3) that produced it; `supporting_features` is a snapshot of every input value the rules and scoring actually used (`trend_alignment_score`, `trend_direction`, `rsi14`, `rsi_state`, `macd_state`, `volume_state`, `volatility_state`, `regime`); `reasons` and `invalidating_conditions` are the human-readable explanation; `market_regime` and `generated_at` place it in context. Nothing is ever stored as a bare `"BUY"` without this evidence attached.

## 9. API (Step 12)

All under `/api/v1/signals`, full detail in `docs/api.md`:

| Endpoint | Purpose |
|---|---|
| `GET /signals` | List, filterable by `symbol`, `strategy_id`, `status`, `interval`. |
| `GET /signals/{id}` | Single signal by UUID. |
| `POST /signals/evaluate/{symbol}` | Evaluates `symbol` against `trend_momentum` right now and returns the resulting `CANDIDATE` (existing or newly created — see `was_newly_created`). No request body; `interval` is an optional query param (default `1h`). Never executes anything. |

**Routing note**: the Phase 5 plan sketches both `GET /signals/{id}` and `GET /signals/{symbol}` at the same path shape, which FastAPI cannot distinguish (a UUID and a ticker are both just path strings). Resolved by folding symbol-scoped listing into `GET /signals`'s `symbol` query parameter — more conventional REST besides, and the same kind of fix already applied to a routing ambiguity in Phase 3.

## 10. Frontend (Step 13/14)

- **Signal Center** (`/signals`, `apps/web/components/market/SignalCenter.tsx` + `SignalCard.tsx`) — symbol selector, the evaluated signal's type/strength/regime, full reasons (✓ list) and invalidating conditions (• list), and status. Deliberately restrained visual language (Step 13): `STRONG` uses the same institutional teal accent as any other emphasized value in the design system, not gold, flashing, or celebratory — this is a deterministic strategy's suggestion with full reasoning attached, not a bet.
- **Market State vs. Signal Center** (Step 14, kept strictly separate): `MarketStateVisualization` (Phase 4) answers *"what does the market currently look like?"* — purely descriptive, no strategy involved. The Signal Center answers *"what does the `trend_momentum` strategy currently suggest?"* — prescriptive, but only within the declared bounds of one named, versioned, deterministic strategy. They are different components, on different screens, never merged.
- Dashboard's `SignalPreview` now shows real evaluated signals (type + strength) for a small watchlist, replacing the Phase 1-era mock panel that displayed a fabricated `"Confidence 82%"` — exactly the kind of number this phase's design explicitly forbids.

## 11. The Risk Engine boundary (Step 16) — not implemented yet

`app/services/signal_engine/risk_boundary.py` defines `RiskEvaluationRequest`, the typed shape the *future* Phase 6 `RiskEngine` will consume, and `to_risk_evaluation_request()`, a pure builder function. **Nothing calls this yet.** It exists now so the boundary is concrete from the start rather than retrofitted, and so its shape is validated against a real `SignalCandidate` in this phase's own code, not just written down in prose.

The Signal Engine **never bypasses this boundary**: a `SignalCandidate` is data with `status = "CANDIDATE"` always — only a future `RiskEngine` may change that to `RISK_APPROVED` or `RISK_REJECTED`. No code path in this phase sets those statuses.

## 12. Why AI is excluded from this stage (Step 15)

Every rule in §3 is a fixed, documented, testable condition — the same inputs always produce the same output (verified directly in `tests/test_signal_rules.py`, `test_signal_engine.py`). An LLM introduces exactly the properties this stage must not have: non-determinism, a probability of a different answer on retry, and reasoning that can't be fully enumerated in a table. The intended future role of AI (`docs/ai-architecture.md`) is downstream of this — analyzing and narrating a signal after it's generated, never producing the signal itself, and never with authority to change what the deterministic engine decided:

```
Signal (this phase) → AI Analyst → Structured AI Assessment → Risk Engine
```

## 13. Testing (Step 17/18)

`tests/test_signal_rules.py` — the full precedence table, one test per row (strong bullish, bearish, all four no-edge regimes, conflicting indicators both directions, extreme-RSI boundary on both sides, low volume, missing RSI, determinism, "changing one feature flips the result"). `tests/test_signal_scoring.py` — every component's boundary values, the full strength lookup table, an exhaustive 3×3×3×3 sweep asserting strength is always one of the three defined values. `tests/test_signal_engine.py` — end-to-end candidate shape, strategy identity, `status` is always `CANDIDATE`, no fabricated probability string anywhere in the output. `tests/test_signal_service.py` / `test_api_signals.py` — persistence, cooldown/dedup, `SUPERSEDED` transitions, 404/422 handling, auditability of the persisted row.

**A note on test isolation with a wall-clock cooldown**: because §6's cooldown is keyed on real elapsed time, tests that assert "this is the first-ever signal for X" are inherently fragile if the suite is re-run within 15 minutes and touches the same `(symbol, interval)` pair twice. The fix used throughout this test suite is to give tests that exercise persistence disjoint `(symbol, interval)` pairs (never asserting `was_newly_created is True` as a precondition) rather than only disjoint symbols — the real invariant under test is "repeated evaluation doesn't create duplicates," which doesn't require assuming a pristine database.

## 14. Limitations

- One strategy only (`trend_momentum`). No strategy selection, no per-user configuration.
- No backtesting integration yet (Phase 12 per the roadmap) — though `SignalService.evaluate()`'s optional `end` parameter (used throughout this phase's own tests for determinism) is exactly the seam a future backtester would call repeatedly across historical dates.
- Cooldown is process-local wall-clock time, not tied to the market data's own timestamps — evaluating far-apart historical dates in quick succession (as this phase's tests do) can still dedupe against each other if they share a `(symbol, interval)` key; production usage (always evaluating "now") is unaffected.
- No scheduler — signals are generated on demand (`POST /signals/evaluate/{symbol}`), matching Phase 4's same on-demand posture for indicators.
