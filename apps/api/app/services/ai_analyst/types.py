"""Shared types for the AI Analyst — kept in their own module so
`prompts.py`, `parser.py`, and `engine.py` can all depend on them
without a circular import, mirroring `signal_engine`/`risk_engine`/
`paper_trading`'s own `types.py`.

Nothing here imports FastAPI, SQLAlchemy, or an AI provider SDK (Step
2): these are plain dataclasses describing evidence in and a validated
analysis out. `AIAnalysisContext` is deliberately narrow (a bounded
snapshot, Step 6) — never a full market history, never a live handle to
mutate anything downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

SuggestedAction = Literal["BUY", "SELL", "HOLD", "NO_ACTION"]
Uncertainty = Literal["LOW", "MEDIUM", "HIGH"]

SUGGESTED_ACTIONS: tuple[SuggestedAction, ...] = ("BUY", "SELL", "HOLD", "NO_ACTION")
UNCERTAINTY_LEVELS: tuple[Uncertainty, ...] = ("LOW", "MEDIUM", "HIGH")


# --- provider-facing errors (Step 12) --------------------------------------


class AIProviderError(Exception):
    """Base class for every way `AIProvider.analyze()` can fail. Never
    raised for a *rejected analysis* (that's `AIValidationError` below,
    from the parser) — only for the provider call itself not producing
    a usable response at all."""


class AIProviderNotConfiguredError(AIProviderError):
    """No API key configured (Step 4) — the provider is never even
    called. Distinct from every other failure mode: this is an expected,
    permanent state until an operator sets `AI_PROVIDER_API_KEY`, not a
    transient error worth retrying or alarming about."""


class AIProviderTimeoutError(AIProviderError):
    pass


class AIProviderUnavailableError(AIProviderError):
    """Network failure, non-2xx from the provider, rate limit, or any
    other "the call did not succeed" outcome that isn't a timeout."""


class AIValidationError(Exception):
    """Raised by `parser.py` when a provider response — however
    successfully it was received — fails schema or content-safety
    validation (Step 10/11). A plain Python exception, independent of
    `app.core.errors` (an HTTP-envelope concept); `AIAnalystService` is
    what translates this into a `ProviderError`/`422`-shaped response."""


# --- input contract (Step 5/6) ----------------------------------------------


@dataclass(frozen=True)
class MarketContext:
    latest_price: float
    recent_prices: list[float]  # bounded — see prompts.py RECENT_PRICES_WINDOW
    volume: float


@dataclass(frozen=True)
class TechnicalContext:
    """Latest-value snapshot only (Step 6) — never the full indicator
    series. Mirrors `technical_analysis.engine.IndicatorSeries`'s actual
    field names exactly (docs/technical-analysis.md), not invented
    ones."""

    sma20: float | None
    sma50: float | None
    sma200: float | None
    ema9: float | None
    ema21: float | None
    ema50: float | None
    ema200: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    stochastic_k: float | None
    stochastic_d: float | None
    atr14: float | None
    bollinger_upper: float | None
    bollinger_middle: float | None
    bollinger_lower: float | None
    relative_volume: float | None


@dataclass(frozen=True)
class FeaturesContext:
    """Mirrors `technical_analysis.features.MarketFeatures` exactly."""

    trend_alignment_score: int | None
    trend_alignment_label: str | None
    trend_direction: str | None
    rsi_state: str | None
    macd_state: str | None
    volume_state: str | None
    volatility_state: str | None


@dataclass(frozen=True)
class RegimeContext:
    label: str
    reasons: list[str]


@dataclass(frozen=True)
class SignalContext:
    strategy_id: str
    strategy_version: str
    direction: str  # the Signal Engine's own BUY/SELL/HOLD — evidence, not the AI's to set
    strength: str | None
    reasons: list[str]
    supporting_features: dict[str, object]
    invalidating_conditions: list[str]


@dataclass(frozen=True)
class RiskContext:
    """Present only when a `RiskEvaluation` already exists for this
    signal (Step 16: AI analysis can happen before risk evaluation in
    the conceptual lifecycle) — `None` on the parent context otherwise,
    never fabricated."""

    policy_version: int
    decision: str  # "APPROVED" | "REJECTED"
    reasons: list[str]
    calculated_position_size: str | None
    stop_loss_price: str | None
    take_profit_price: str | None


@dataclass(frozen=True)
class AIAnalysisContext:
    """The complete, bounded evidence packet handed to the provider
    (Step 5). Everything here is read-only evidence about what the
    deterministic systems already observed — the AI is never given a
    way to write back through this object, because it doesn't hold a
    database session or any mutable handle at all."""

    signal_id: str
    symbol: str
    interval: str
    timestamp: datetime
    market: MarketContext
    technical: TechnicalContext
    features: FeaturesContext
    regime: RegimeContext
    signal: SignalContext
    risk: RiskContext | None


# --- provider output (before validation) ------------------------------------


@dataclass(frozen=True)
class ProviderResponse:
    """What `AIProvider.analyze()` returns — the provider's job ends at
    "here is the structured JSON the model produced and some request
    metadata"; it does not itself decide whether that JSON is safe to
    trust (`parser.py` does)."""

    raw_output: dict[str, object]
    model: str
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None


# --- validated output (Step 7) ----------------------------------------------


@dataclass(frozen=True)
class AIAnalysisOutput:
    """The safe, validated result of one analysis — everything an
    `AIAnalysis` database row is built from. Deliberately has no
    `position_size`/`stop_loss`/`take_profit` field anywhere in this
    type: the schema itself is the strongest defense against the AI
    ever supplying one (Step 10), not just a prompt instruction."""

    symbol: str
    interval: str
    provider: str
    model: str
    prompt_version: str
    market_summary: str
    thesis: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    risks: list[str]
    invalidating_conditions: list[str]
    suggested_action: SuggestedAction
    action_rationale: str
    uncertainty: Uncertainty
    generated_at: datetime
    model_metadata: dict[str, object] = field(default_factory=dict)
