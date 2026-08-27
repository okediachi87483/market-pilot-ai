"""Market features (Step 6) — deterministic, documented derivations from
raw indicator values. These describe *what the market currently looks
like*, never a trading decision (no BUY/SELL/SHORT/EXIT anywhere in this
module — that's Phase 5's signal engine, not this one).

Every threshold here is a documented, illustrative convention (see
docs/technical-analysis.md), not a claim of objective market truth.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.technical_analysis.engine import IndicatorSeries

TREND_ALIGNMENT_LABELS = {0: "weak", 1: "partial", 2: "strong"}

RSI_OVERSOLD_THRESHOLD = 30.0
RSI_OVERBOUGHT_THRESHOLD = 70.0

RELATIVE_VOLUME_LOW_THRESHOLD = 0.75
RELATIVE_VOLUME_ELEVATED_THRESHOLD = 1.25

# ATR as a percentage of price — a normalized volatility measure
# comparable across assets at different price levels.
ATR_PCT_LOW_THRESHOLD = 1.0
ATR_PCT_ELEVATED_THRESHOLD = 3.0


@dataclass(frozen=True)
class MarketFeatures:
    price_above_ema21: bool | None
    ema9_above_ema21: bool | None
    ema21_above_ema50: bool | None
    ema50_above_ema200: bool | None
    trend_alignment_score: int | None
    trend_alignment_label: str | None
    trend_direction: str | None  # "bullish" | "bearish" | "mixed"

    rsi_state: str | None
    macd_state: str | None
    volume_state: str | None
    volatility_state: str | None


def _trend_alignment(checks: list[bool | None]) -> tuple[int | None, str | None]:
    """Score how consistently the available trend checks agree, on a
    0/1/2 scale (Step 8) — never a fake probability.

    - Gather whichever of the (up to 4) checks are defined (missing
      ones, most often ema50-vs-ema200 for lack of 200 bars of history,
      are simply excluded rather than forcing the whole score to None).
    - unanimous agreement across >= 3 checks -> 2 (strong)
    - unanimous agreement across 1-2 checks, or a majority (not
      unanimous) across any number -> 1 (partial)
    - an even split (e.g. 2-2) -> 0 (weak)
    - no checks available at all -> None

    See docs/technical-analysis.md §"Trend alignment score" for the
    worked truth table.
    """
    available = [c for c in checks if c is not None]
    if not available:
        return None, None

    true_count = sum(available)
    false_count = len(available) - true_count
    agree = max(true_count, false_count)
    disagree = len(available) - agree

    if disagree == 0 and len(available) >= 3:
        return 2, TREND_ALIGNMENT_LABELS[2]
    if disagree == 0 or agree > disagree:
        return 1, TREND_ALIGNMENT_LABELS[1]
    return 0, TREND_ALIGNMENT_LABELS[0]


def _trend_direction(checks: list[bool | None]) -> str | None:
    available = [c for c in checks if c is not None]
    if not available:
        return None
    true_count = sum(available)
    false_count = len(available) - true_count
    if true_count > false_count:
        return "bullish"
    if false_count > true_count:
        return "bearish"
    return "mixed"


def extract_features(series: IndicatorSeries, index: int) -> MarketFeatures:
    close = series.close[index]
    ema9 = series.ema9[index]
    ema21 = series.ema21[index]
    ema50 = series.ema50[index]
    ema200 = series.ema200[index]

    price_above_ema21 = None if close is None or ema21 is None else close > ema21
    ema9_above_ema21 = None if ema9 is None or ema21 is None else ema9 > ema21
    ema21_above_ema50 = None if ema21 is None or ema50 is None else ema21 > ema50
    ema50_above_ema200 = None if ema50 is None or ema200 is None else ema50 > ema200

    trend_checks = [price_above_ema21, ema9_above_ema21, ema21_above_ema50, ema50_above_ema200]
    alignment_score, alignment_label = _trend_alignment(trend_checks)
    direction = _trend_direction(trend_checks)

    rsi14 = series.rsi14[index]
    if rsi14 is None:
        rsi_state = None
    elif rsi14 < RSI_OVERSOLD_THRESHOLD:
        rsi_state = "oversold"
    elif rsi14 > RSI_OVERBOUGHT_THRESHOLD:
        rsi_state = "overbought"
    else:
        rsi_state = "neutral"

    histogram = series.macd_histogram[index]
    if histogram is None:
        macd_state = None
    elif histogram > 0:
        macd_state = "bullish"
    elif histogram < 0:
        macd_state = "bearish"
    else:
        macd_state = "neutral"

    rel_volume = series.relative_volume[index]
    if rel_volume is None:
        volume_state = None
    elif rel_volume < RELATIVE_VOLUME_LOW_THRESHOLD:
        volume_state = "low"
    elif rel_volume > RELATIVE_VOLUME_ELEVATED_THRESHOLD:
        volume_state = "elevated"
    else:
        volume_state = "normal"

    atr14 = series.atr14[index]
    if atr14 is None or close is None or close == 0:
        volatility_state = None
    else:
        atr_pct = atr14 / close * 100.0
        if atr_pct < ATR_PCT_LOW_THRESHOLD:
            volatility_state = "low"
        elif atr_pct > ATR_PCT_ELEVATED_THRESHOLD:
            volatility_state = "elevated"
        else:
            volatility_state = "normal"

    return MarketFeatures(
        price_above_ema21=price_above_ema21,
        ema9_above_ema21=ema9_above_ema21,
        ema21_above_ema50=ema21_above_ema50,
        ema50_above_ema200=ema50_above_ema200,
        trend_alignment_score=alignment_score,
        trend_alignment_label=alignment_label,
        trend_direction=direction,
        rsi_state=rsi_state,
        macd_state=macd_state,
        volume_state=volume_state,
        volatility_state=volatility_state,
    )
