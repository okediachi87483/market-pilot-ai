"""Shared types for the signal engine — kept in their own module so
engine.py, rules.py, and scoring.py can all depend on them without a
circular import between engine.py (which orchestrates) and rules.py/
scoring.py (which it calls).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.services.technical_analysis.features import MarketFeatures
from app.services.technical_analysis.regime import RegimeResult

SignalType = Literal["BUY", "SELL", "HOLD"]
SignalStrength = Literal["WEAK", "MODERATE", "STRONG"]

STRATEGY_ID = "trend_momentum"
STRATEGY_VERSION = "1.0.0"
# Convenience label combining id + major version, matching the shorthand
# used in docs/signal-engine.md and the API examples (e.g. "trend_momentum_v1").
STRATEGY_LABEL = f"{STRATEGY_ID}_v{STRATEGY_VERSION.split('.')[0]}"


@dataclass(frozen=True)
class SignalInput:
    """Everything the engine needs to evaluate one symbol at one point in
    time — deliberately narrow (not the full IndicatorSeries) so the
    engine's dependency surface is easy to reason about and test."""

    symbol: str
    interval: str
    timestamp: datetime
    candle_count: int
    regime: RegimeResult
    features: MarketFeatures
    rsi14: float | None


@dataclass(frozen=True)
class RuleOutcome:
    signal: SignalType
    reasons: list[str]
    invalidating_conditions: list[str]


@dataclass(frozen=True)
class SignalCandidate:
    symbol: str
    signal: SignalType
    strategy_id: str
    strategy_version: str
    timestamp: datetime
    reasons: list[str]
    supporting_features: dict[str, object]
    invalidating_conditions: list[str]
    market_regime: str
    strength: SignalStrength | None
    status: Literal["CANDIDATE"] = "CANDIDATE"
    score_breakdown: dict[str, int] = field(default_factory=dict)
