"""Pure technical-indicator math. No FastAPI, no database, no AI, no I/O —
every function here takes plain lists of floats and returns plain lists
of floats (or `None` for warm-up bars). See docs/technical-analysis.md
for formulas, warm-up periods, and the float-vs-Decimal rationale.

Every function returns a list the same length as its input, aligned
index-for-index with the input candles — `None` where the indicator
isn't yet defined (not enough history), a float everywhere else. This
is what makes the output usable both as a single "current value" (last
element) and as a full series for chart overlays (Step 13).

All indicators here are single-pass or amortized O(n) — no indicator
recomputes a window from scratch at every step.
"""

from __future__ import annotations

import math

Series = list[float | None]


def sma(values: list[float], period: int) -> Series:
    """Simple moving average. Warm-up: `period - 1` bars (first value at
    index `period - 1`)."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    running_sum = 0.0
    for i, value in enumerate(values):
        running_sum += value
        if i >= period:
            running_sum -= values[i - period]
        if i >= period - 1:
            out[i] = running_sum / period
    return out


def ema(values: list[float], period: int) -> Series:
    """Exponential moving average, seeded with the SMA of the first
    `period` values (the standard convention — see docs/technical-analysis.md).
    Warm-up: `period - 1` bars, same as SMA."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    if len(values) < period:
        return out

    multiplier = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * multiplier + prev
        out[i] = prev
    return out


def rsi(closes: list[float], period: int = 14) -> Series:
    """Wilder's RSI. Warm-up: `period` bars (needs `period` deltas, i.e.
    `period + 1` closes) before the first value.

    Edge case: a flat run (no losses) makes the average loss 0. Rather
    than divide by zero, RSI is defined as 100 when there's been gain
    with no loss, and 50 (neutral) when there's been neither gain nor
    loss at all — see docs/technical-analysis.md."""
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(closes)
    out: Series = [None] * n
    if n <= period:
        return out

    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        gains[i] = max(delta, 0.0)
        losses[i] = max(-delta, 0.0)

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    out[period] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = _rsi_from_averages(avg_gain, avg_loss)

    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[Series, Series, Series]:
    """MACD line (EMA[fast] - EMA[slow]), its signal line (EMA[signal] of
    the MACD line), and the histogram (MACD - signal). Warm-up: the MACD
    line needs `slow` bars; the signal line needs the MACD line to exist
    for `signal` bars beyond that, so the histogram's warm-up is
    `slow + signal - 1` bars."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    macd_line: Series = [None] * len(closes)
    for i in range(len(closes)):
        f, s = ema_fast[i], ema_slow[i]
        if f is not None and s is not None:
            macd_line[i] = f - s

    # EMA of the MACD line, computed only over the defined (non-None) tail.
    first_defined = next((i for i, v in enumerate(macd_line) if v is not None), None)
    signal_line: Series = [None] * len(closes)
    histogram: Series = [None] * len(closes)
    if first_defined is not None:
        macd_values = [v for v in macd_line[first_defined:] if v is not None]
        signal_values = ema(macd_values, signal)
        for offset, value in enumerate(signal_values):
            signal_line[first_defined + offset] = value

    for i in range(len(closes)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]  # type: ignore[operator]

    return macd_line, signal_line, histogram


def stochastic(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14, smooth_d: int = 3
) -> tuple[Series, Series]:
    """Stochastic oscillator. %K = (close - lowest_low) / (highest_high -
    lowest_low) * 100 over `period` bars; %D = SMA(`smooth_d`) of %K.
    Warm-up: %K needs `period - 1` bars, %D needs `smooth_d - 1` more.

    Edge case: a `period`-bar range with zero width (highest == lowest —
    a flat market) makes the ratio undefined; defined as 50 (neutral),
    matching RSI's flat-price convention."""
    n = len(closes)
    percent_k: Series = [None] * n
    for i in range(period - 1, n):
        window_high = max(highs[i - period + 1 : i + 1])
        window_low = min(lows[i - period + 1 : i + 1])
        span = window_high - window_low
        percent_k[i] = 50.0 if span == 0 else (closes[i] - window_low) / span * 100.0

    first_defined = next((i for i, v in enumerate(percent_k) if v is not None), None)
    percent_d: Series = [None] * n
    if first_defined is not None:
        k_values = [v for v in percent_k[first_defined:] if v is not None]
        d_values = sma(k_values, smooth_d)
        for offset, value in enumerate(d_values):
            percent_d[first_defined + offset] = value

    return percent_k, percent_d


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> Series:
    """Average True Range, Wilder-smoothed. True range needs a previous
    close, so it's defined from index 1; the first ATR value (a simple
    average of the first `period` true ranges) needs `period` more bars.
    Warm-up: `period` bars (first value at index `period`)."""
    n = len(closes)
    out: Series = [None] * n
    if n <= period:
        return out

    true_ranges = [0.0] * n
    for i in range(1, n):
        true_ranges[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    avg = sum(true_ranges[1 : period + 1]) / period
    out[period] = avg
    for i in range(period + 1, n):
        avg = (avg * (period - 1) + true_ranges[i]) / period
        out[i] = avg
    return out


def bollinger_bands(
    closes: list[float], period: int = 20, num_std_dev: float = 2.0
) -> tuple[Series, Series, Series, Series]:
    """Bollinger Bands: middle = SMA(period), bands = middle +/-
    num_std_dev * population standard deviation of the same window
    (population, not sample — the standard Bollinger Bands convention).
    `width` is normalized as (upper - lower) / middle, so it's comparable
    across assets at different price levels. Warm-up: `period - 1` bars."""
    n = len(closes)
    middle = sma(closes, period)
    upper: Series = [None] * n
    lower: Series = [None] * n
    width: Series = [None] * n

    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mean = middle[i]
        assert mean is not None
        variance = sum((v - mean) ** 2 for v in window) / period
        std_dev = math.sqrt(variance)
        upper[i] = mean + num_std_dev * std_dev
        lower[i] = mean - num_std_dev * std_dev
        width[i] = 0.0 if mean == 0 else (upper[i] - lower[i]) / mean  # type: ignore[operator]

    return upper, middle, lower, width


def volume_sma(volumes: list[float], period: int = 20) -> Series:
    """Simple moving average of volume. Same warm-up as `sma`."""
    return sma(volumes, period)


def relative_volume(volumes: list[float], volume_sma_series: Series) -> Series:
    """Current volume divided by its own SMA — a unitless ratio (1.0 =
    exactly average). Undefined (`None`) wherever the SMA itself is
    undefined or exactly zero (an all-zero-volume window), since the
    ratio has no meaningful value in that case."""
    out: Series = [None] * len(volumes)
    for i, avg in enumerate(volume_sma_series):
        if avg is not None and avg != 0:
            out[i] = volumes[i] / avg
    return out
