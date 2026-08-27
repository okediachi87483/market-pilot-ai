# MarketPilot AI — Technical Analysis

Phase 4. Turns normalized OHLCV market data ([market-data.md](market-data.md)) into deterministic technical indicators, market features, and a detected market regime. **No AI is involved anywhere in this layer** — every calculation is a documented, reproducible formula, and this document exists partly so that claim is checkable. **This layer does not produce trading decisions** — no BUY/SELL/SHORT/EXIT anywhere; that's Phase 5's signal engine.

## 1. Architecture

```
MARKET DATA (Postgres, Phase 3)
        │
        ▼
Candle conversion (Decimal -> float, see §8)
        │
        ▼
TechnicalAnalysisEngine.calculate()   — app/services/technical_analysis/engine.py
        │
        ▼
IndicatorSeries   (per-bar arrays: SMA/EMA/RSI/MACD/Stochastic/ATR/Bollinger/Volume)
        │
        ▼
extract_features()   — app/services/technical_analysis/features.py
        │
        ▼
classify_regime()    — app/services/technical_analysis/regime.py
        │
        ▼
API (docs/api.md) -> frontend analysis panel + signature visualization
```

`app/services/technical_analysis/` is deliberately independent of FastAPI, the database, AI, paper trading, and broker integrations (Step 2 of the Phase 4 plan): `indicators.py` and `engine.py` take plain lists/dataclasses in and return plain dataclasses out. `TechnicalAnalysisService` (`service.py`) is the only piece that knows about `MarketDataService` and the database — the calculation core could be lifted into a standalone package or library without modification.

## 2. Indicators (Step 3)

| Category | Indicators | Periods |
|---|---|---|
| Trend | SMA, EMA | SMA: 20, 50, 200 · EMA: 9, 21, 50, 200 |
| Momentum | RSI, MACD (line/signal/histogram), Stochastic (%K/%D) | RSI: 14 · MACD: 12/26/9 · Stochastic: 14, smoothed 3 |
| Volatility | ATR, Bollinger Bands (upper/middle/lower/width) | ATR: 14 · Bollinger: 20, ±2σ |
| Volume | Volume SMA, Relative Volume | 20 |

These are the well-known standard periods (Wilder's original RSI/ATR parameters, the classic 12/26/9 MACD, John Bollinger's 20/2 convention) — not proprietary or invented values (Step 4).

## 3. Formulas and warm-up periods

All formulas live in `app/services/technical_analysis/indicators.py`, each with its warm-up period documented in its own docstring. Summarized:

| Indicator | Formula | Warm-up (bars before first value) |
|---|---|---|
| SMA(n) | mean of the last n closes | n − 1 |
| EMA(n) | seeded with SMA(n), then `(close − prev) × 2/(n+1) + prev` | n − 1 |
| RSI(14) | Wilder-smoothed average gain / average loss → `100 − 100/(1+RS)` | 14 |
| MACD | EMA(12) − EMA(26); signal = EMA(9) of the MACD line | line: 26 · histogram: 26 + 9 − 1 = 34 |
| Stochastic | `%K = (close − lowest_low_n)/(highest_high_n − lowest_low_n) × 100`; `%D = SMA(3)` of %K | %K: 13 · %D: 13 + 2 |
| ATR(14) | Wilder-smoothed average of True Range (`max(high−low, |high−prev_close|, |low−prev_close|)`) | 14 |
| Bollinger(20, 2σ) | middle = SMA(20); bands = middle ± 2 × population stddev of the same 20-close window; width = (upper−lower)/middle | 19 |
| Volume SMA(20) | mean of the last 20 volumes | 19 |
| Relative Volume | current volume / Volume SMA(20) | same as Volume SMA |

Every function returns a list the same length as its input candles, `None` for bars still in warm-up — this is what lets the same computation serve both "the current value" (the last element) and a full time series for chart overlays (Step 13), with no special-casing.

### Documented edge-case handling (Step 4)

- **RSI, zero average loss**: `avg_loss == 0` would divide by zero computing `RS`. Defined instead as RSI = 100 when there's been gain with no loss, and RSI = 50 (neutral) when there's been neither gain nor loss (a perfectly flat run).
- **Stochastic, zero-width range**: if the `period`-bar high/low range has zero width (a flat market), `%K` is undefined by the raw formula; defined as 50 (neutral), matching RSI's flat-price convention.
- **Relative volume, zero average**: if Volume SMA is exactly 0 (an all-zero-volume window), the ratio is undefined; returned as `None` rather than a division-by-zero or a fabricated value.
- **Insufficient data**: every indicator function checks input length against its required warm-up and returns an all-`None` series rather than raising or guessing — never a fabricated early value.
- **Missing/malformed candles**: not applicable at this layer — `MarketDataService.get_history()` (Phase 3) already guarantees validated, normalized, gap-free-per-request candles before they reach the engine.

## 4. Indicator output model (Step 5)

`IndicatorSeries` (`engine.py`) holds one aligned array per indicator plus `timestamps` and `close`. The API never exposes this dataclass directly — `app/schemas/analysis.py` defines the response shapes (`AnalysisResponse`, `IndicatorSeriesResponse`, `RegimeEndpointResponse`) that translate it into the documented JSON contract (§7).

## 5. Market features (Step 6)

Deterministic, documented derivations — never a trading decision:

| Feature | Definition |
|---|---|
| `price_above_ema21`, `ema9_above_ema21`, `ema21_above_ema50`, `ema50_above_ema200` | Boolean comparisons; `None` if either side is undefined (most commonly the 200-period ones, absent shorter history) |
| `trend_alignment_score` / `_label` | See §6 |
| `trend_direction` | `"bullish"` / `"bearish"` / `"mixed"`, from the same trend checks (§6) |
| `rsi_state` | `rsi14 < 30` → `oversold` · `> 70` → `overbought` · else `neutral` |
| `macd_state` | sign of `macd_histogram`: `> 0` → `bullish` · `< 0` → `bearish` · `= 0` → `neutral` |
| `volume_state` | `relative_volume < 0.75` → `low` · `> 1.25` → `elevated` · else `normal` |
| `volatility_state` | `atr14 / close × 100`: `< 1%` → `low` · `> 3%` → `elevated` · else `normal` |

All thresholds (30/70, 0.75/1.25, 1%/3%) are documented, illustrative conventions — not claims of objective market truth (Step 8).

## 6. Trend alignment score — the worked truth table (Step 8)

No fake probability ("82% chance of increase") anywhere in this system. Instead, a transparent 0/1/2 score measuring how consistently the *available* trend checks agree:

1. Gather whichever of the four checks (`price_above_ema21`, `ema9_above_ema21`, `ema21_above_ema50`, `ema50_above_ema200`) are defined — a missing one (most often the 200-period comparison, for lack of history) is excluded, not treated as a failure.
2. `agree` = the larger of (count True, count False); `disagree` = the rest.
3. **Strong (2)**: unanimous agreement (`disagree == 0`) across **at least 3** checks.
4. **Partial (1)**: unanimous agreement across only 1–2 checks, *or* a majority (not unanimous) across any number.
5. **Weak (0)**: an even split (e.g. 2-2).
6. `None`: no checks available at all.

| Available checks | True count | Result |
|---|---|---|
| 4 | 4 or 0 | Strong (2) |
| 4 | 3 or 1 | Partial (1) |
| 4 | 2 | Weak (0) |
| 3 | 3 or 0 | Strong (2) |
| 3 | 2 or 1 | Partial (1) |
| 2 | 2 or 0 | Partial (1) |
| 2 | 1 | Weak (0) |
| 1 | either | Partial (1) |
| 0 | — | `None` |

`trend_direction` is computed the same way, from the same available checks: more True → `bullish`, more False → `bearish`, tie → `mixed`.

## 7. Market regime (Step 7)

Six labels: `BULLISH`, `BEARISH`, `SIDEWAYS`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `INSUFFICIENT_DATA`. Fully rule-based (`app/services/technical_analysis/regime.py`) — **no LLM anywhere in this module**. A regime is a *detected* condition, presented that way in every API response and UI surface — never "guaranteed market direction."

Precedence order (first match wins):

1. **INSUFFICIENT_DATA** — fewer than `MIN_CANDLES_FOR_FEATURES` (50) candles, or the trend alignment score itself is `None`.
2. **HIGH_VOLATILITY** — `volatility_state == "elevated"` (checked before trend, since an elevated-volatility market deserves the flag regardless of direction).
3. **LOW_VOLATILITY** — `volatility_state == "low"` and trend alignment is weak (0) — a quiet, directionless market.
4. **BULLISH** — `trend_direction == "bullish"` and alignment ≥ partial (1).
5. **BEARISH** — the bearish mirror of rule 4.
6. **SIDEWAYS** — everything else (the default).

Every result carries a `reasons` list (e.g. `"trend checks lean bullish with strong alignment"`) so the classification is always explainable, not a black box.

### Why 50 candles for "insufficient data"

The regime classifier and feature extraction depend on `ema50` (via `ema21_above_ema50`) as their longest *required* input — `ema200`/`sma200` are informational only (shown in the API/UI, allowed to stay `None`) and don't block classification. 50 candles is EMA50's own warm-up, so it's the natural threshold: below it, the trend-alignment score can't be meaningfully computed at all.

## 8. Numerical considerations (Step 15)

- **Persisted market data stays `Decimal`** (docs/database.md §1) — this layer never touches the stored `NUMERIC` columns.
- **Indicator math uses `float`**, converted from `Decimal` at the `TechnicalAnalysisService` boundary (`_get_candles`). This is a deliberate choice, not a shortcut: technical indicators are analytical/statistical smoothing (moving averages, standard deviation, ratios), not owed amounts — the same category of computation numpy/pandas/every mainstream TA library performs in float64. `Decimal` is reserved for values where exact arithmetic is a correctness requirement (money, quantities, fees — see docs/database.md §1); nothing in this layer is money.
- **No arbitrary intermediate rounding.** Every indicator function carries full float precision through its entire calculation; rounding (`.toFixed()` et al.) happens only at the display layer in the frontend, never inside `indicators.py`.
- **No claimed precision beyond what the math supports.** A ratio like `relative_volume` is exactly that — a ratio — never presented as a probability or confidence percentage.

## 9. API endpoints (Step 10)

All under `/api/v1/analysis`, full detail in [api.md](api.md):

| Endpoint | Purpose |
|---|---|
| `GET /analysis/{symbol}` | Current snapshot: price, all indicators at the latest bar, features, detected regime, calculation timestamp, candle count, source. |
| `GET /analysis/{symbol}/indicators` | Full per-bar time series (every indicator, aligned with `close`) for the requested range — what the chart overlays consume. |
| `GET /analysis/{symbol}/regime` | Just the regime label, reasons, and candle count — a lighter call when only the classification is needed. |

Query params: `interval` (one of `1m`/`5m`/`15m`/`1h`/`1d`), and `start`/`end` for the two range-based endpoints. Every response identifies `source` and `is_mock` (Step 12's "clearly identify the calculations are based on the available market dataset" — carried through from Phase 3's mock-data labeling).

## 10. Persistence decision (Step 9)

**Indicators are calculated on demand, not persisted.** `TechnicalAnalysisService` reads already-persisted `market_data` rows (via `MarketDataService`, which handles ingestion/idempotency — Phase 3) and computes the full `IndicatorSeries` fresh on every request. No `Indicator` table exists.

Reasoning:

- Indicator math is cheap, pure, single-pass-per-indicator (§11) over a request-capped dataset (`MarketDataService.MAX_HISTORY_BARS` = 2000 bars) — recomputation costs low milliseconds, not a meaningful load concern at current scale.
- Every indicator is a deterministic function of `market_data` that's already durable — persisting a derived copy would duplicate data already safely stored, and would need its own staleness/invalidation story (what happens when new bars are ingested for a range with cached indicators?) for no offsetting benefit.
- The `calculation_version` concept the Phase 4 brief anticipates for a persisted `Indicator` model is naturally satisfied instead by the formulas themselves being versioned in code (this document + `engine.py`'s constants) — reproducing a historical value means re-running the same well-documented function, not looking up a stored row that might reflect an old formula.

This is a decision to revisit, not a permanent one: if profiling ever shows on-demand calculation as an actual bottleneck (e.g. once a background scheduler is repeatedly requesting analysis for many symbols — see §11), the next step is a short-TTL cache (Redis, already available in this stack) keyed by `(symbol, interval, end_bucket)`, not a persisted table — caching solves a hot-path latency problem; persisting solves a durability problem indicators don't have, since the market data underneath is already durable.

## 11. Performance (Step 16)

- Every indicator function is single-pass or amortized O(n) — SMA/EMA/RSI/ATR use running sums or incremental smoothing rather than recomputing a window from scratch each step; Bollinger recomputes its window's variance per bar (O(n·period)) since a rolling-variance formula would trade simplicity for a marginal gain at `period=20`.
- `TechnicalAnalysisEngine.calculate()` is stateless and takes candles directly — safe to call concurrently for different symbols/intervals without shared state.
- No Celery, Kafka, or Kubernetes introduced for this phase, per the plan's explicit instruction. The architecture doesn't preclude them later: `TechnicalAnalysisService` is already the single seam where a background worker or scheduler would plug in (call `get_snapshot`/`get_series` on a schedule instead of per-request), without touching the calculation core.
- Multiple symbols/intervals are already independent by construction (no cross-symbol state) — the natural path to "periodic recalculation for every watched symbol" is a scheduler that calls this same service per symbol, not a rewrite.

## 12. Observability (Step 17)

`TechnicalAnalysisService.get_snapshot()` logs one structured line per calculation: `provider` is implicit (always the market-data layer beneath it), `symbol`, `interval`, `candle_count`, `duration_ms`, and the resulting `regime` — no sensitive information. Example:

```
technical analysis calculated symbol=AAPL interval=1h candles=240 duration_ms=3.2 regime=BULLISH
```

Metrics (`technical_analysis_requests_total`, `_duration`, `_errors_total`) are not yet wired to a collector — no Prometheus endpoint exists in this codebase yet (that's Phase 14's observability phase, per docs/architecture.md's roadmap). Structured logs are the present-day equivalent and carry the same fields a future metric would use, so wiring an actual counter/histogram later is additive, not a redesign.

## 13. Frontend (Step 11, 12, 13)

- **`AnalysisPanel`** (`apps/web/components/market/AnalysisPanel.tsx`) — the sophisticated-but-explained panel on `/markets`: Trend/Momentum/Volatility/Volume sections, each with a one-line plain-language explanation, plus the detected regime and its reasons.
- **`MarketStateVisualization`** (`apps/web/components/market/MarketStateVisualization.tsx`) — MarketPilot's signature visualization (Step 12), now real: the same semicircle-gauge visual language from the Phase 1 design system, driven by the actual `trend_alignment_score`/`trend_direction`/regime from the API. Answers "what does the market currently look like?" — never "what should I buy?": no BUY/SELL/SHORT/EXIT language anywhere in the component, and it replaces the Phase 1–3 placeholder that was mislabeled "AI Market Assessment" (there is no AI yet — see docs/ai-architecture.md, which hasn't been built). The needle position is derived transparently from `trend_alignment_score` (0/1/2 → 0/55/100% deflection) signed by `trend_direction` — documented in the component, not a separately invented number.
- **`PriceChart`** (`apps/web/components/market/PriceChart.tsx`) — enhanced for Step 13: renders close price, EMA9/EMA21, SMA20, and Bollinger Bands as overlays, plus a volume bar strip, all from `IndicatorPoint[]` returned by `GET /analysis/{symbol}/indicators`. The frontend only scales coordinates for display — every indicator value is backend-calculated.

## 14. What this phase does not do (Step 19)

This layer produces **INDICATORS**, **FEATURES**, and a **REGIME** — never `BUY`, `SELL`, `SHORT`, or `EXIT`. There is no signal-generation logic anywhere in `app/services/technical_analysis/`. Turning a detected regime and its features into an actionable, risk-gated trading signal is Phase 5's `signal_engine`, deliberately not started here.
