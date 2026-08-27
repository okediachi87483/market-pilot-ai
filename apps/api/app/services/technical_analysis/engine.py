"""TechnicalAnalysisEngine — turns a candle series into the full set of
indicator series (Step 2/3). Deliberately independent of FastAPI, the
database, AI, paper trading, and broker integrations (Step 2): it takes
plain `Candle` objects in and returns plain dataclasses out, so it can be
unit-tested and reused without any of those. See docs/technical-analysis.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.services.technical_analysis import indicators as ind
from app.services.technical_analysis.indicators import Series

# Standard periods for every indicator in the core set (Step 3). Not
# user-configurable in this phase — these are the well-known conventional
# values (see docs/technical-analysis.md for citations).
SMA_PERIODS = (20, 50, 200)
EMA_PERIODS = (9, 21, 50, 200)
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
STOCHASTIC_PERIOD, STOCHASTIC_SMOOTH_D = 14, 3
ATR_PERIOD = 14
BOLLINGER_PERIOD, BOLLINGER_STD_DEV = 20, 2.0
VOLUME_SMA_PERIOD = 20

# The largest warm-up among the indicators that feed market features and
# regime classification (ema50 dominates; ema200/sma200 are informational
# only and are allowed to stay None past this point). See
# docs/technical-analysis.md §"Insufficient data".
MIN_CANDLES_FOR_FEATURES = 50


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class IndicatorSeries:
    timestamps: list[datetime]
    close: Series

    sma20: Series
    sma50: Series
    sma200: Series
    ema9: Series
    ema21: Series
    ema50: Series
    ema200: Series

    rsi14: Series
    macd: Series
    macd_signal: Series
    macd_histogram: Series
    stochastic_k: Series
    stochastic_d: Series

    atr14: Series
    bollinger_upper: Series
    bollinger_middle: Series
    bollinger_lower: Series
    bollinger_width: Series

    volume: Series
    volume_sma: Series
    relative_volume: Series

    def __len__(self) -> int:
        return len(self.timestamps)

    def latest_index(self) -> int | None:
        return len(self.timestamps) - 1 if self.timestamps else None


class TechnicalAnalysisEngine:
    """Stateless — `calculate` is a pure function of its input candles.
    Instantiated per call rather than held as a singleton; there is no
    internal state to hold."""

    def calculate(self, candles: list[Candle]) -> IndicatorSeries:
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]
        timestamps = [c.timestamp for c in candles]

        macd_line, macd_signal, macd_hist = ind.macd(closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
        stoch_k, stoch_d = ind.stochastic(
            highs, lows, closes, STOCHASTIC_PERIOD, STOCHASTIC_SMOOTH_D
        )
        boll_upper, boll_middle, boll_lower, boll_width = ind.bollinger_bands(
            closes, BOLLINGER_PERIOD, BOLLINGER_STD_DEV
        )
        vol_sma = ind.volume_sma(volumes, VOLUME_SMA_PERIOD)

        return IndicatorSeries(
            timestamps=timestamps,
            close=[c for c in closes],
            sma20=ind.sma(closes, SMA_PERIODS[0]),
            sma50=ind.sma(closes, SMA_PERIODS[1]),
            sma200=ind.sma(closes, SMA_PERIODS[2]),
            ema9=ind.ema(closes, EMA_PERIODS[0]),
            ema21=ind.ema(closes, EMA_PERIODS[1]),
            ema50=ind.ema(closes, EMA_PERIODS[2]),
            ema200=ind.ema(closes, EMA_PERIODS[3]),
            rsi14=ind.rsi(closes, RSI_PERIOD),
            macd=macd_line,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            stochastic_k=stoch_k,
            stochastic_d=stoch_d,
            atr14=ind.atr(highs, lows, closes, ATR_PERIOD),
            bollinger_upper=boll_upper,
            bollinger_middle=boll_middle,
            bollinger_lower=boll_lower,
            bollinger_width=boll_width,
            volume=[v for v in volumes],
            volume_sma=vol_sma,
            relative_volume=ind.relative_volume(volumes, vol_sma),
        )
