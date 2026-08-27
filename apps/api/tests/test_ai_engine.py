"""Unit tests for AIAnalystEngine — pure orchestration (build prompt ->
call provider -> parse/validate), exercised against a fake AIProvider
so no network or database is involved."""

from datetime import UTC, datetime

import pytest

from app.services.ai_analyst.engine import AIAnalystEngine
from app.services.ai_analyst.types import (
    AIAnalysisContext,
    AIProviderTimeoutError,
    AIValidationError,
    FeaturesContext,
    MarketContext,
    ProviderResponse,
    RegimeContext,
    SignalContext,
    TechnicalContext,
)

VALID_RAW_OUTPUT = {
    "market_summary": "AAPL is trading above its 21-day EMA with rising volume.",
    "thesis": "The evidence suggests continuing bullish momentum, though confirmation is limited.",
    "supporting_evidence": ["Price is above EMA21"],
    "contradicting_evidence": ["RSI is approaching overbought territory"],
    "risks": ["A reversal below EMA21 would weaken the thesis"],
    "invalidating_conditions": ["Price closes below EMA21"],
    "suggested_action": "BUY",
    "action_rationale": "Trend and momentum evidence align with the signal's direction.",
    "uncertainty": "MEDIUM",
}


def _context() -> AIAnalysisContext:
    return AIAnalysisContext(
        signal_id="11111111-1111-1111-1111-111111111111",
        symbol="AAPL",
        interval="1d",
        timestamp=datetime(2032, 1, 1, tzinfo=UTC),
        market=MarketContext(
            latest_price=150.0, recent_prices=[148.0, 149.0, 150.0], volume=1_000_000.0
        ),
        technical=TechnicalContext(
            sma20=149.0,
            sma50=145.0,
            sma200=140.0,
            ema9=150.5,
            ema21=148.0,
            ema50=146.0,
            ema200=141.0,
            rsi14=58.0,
            macd=1.2,
            macd_signal=0.9,
            macd_histogram=0.3,
            stochastic_k=60.0,
            stochastic_d=55.0,
            atr14=2.1,
            bollinger_upper=153.0,
            bollinger_middle=149.0,
            bollinger_lower=145.0,
            relative_volume=1.3,
        ),
        features=FeaturesContext(
            trend_alignment_score=4,
            trend_alignment_label="STRONG_UPTREND",
            trend_direction="UP",
            rsi_state="NEUTRAL",
            macd_state="BULLISH",
            volume_state="ELEVATED",
            volatility_state="NORMAL",
        ),
        regime=RegimeContext(label="BULLISH", reasons=["price above all major moving averages"]),
        signal=SignalContext(
            strategy_id="trend_momentum",
            strategy_version="1.0.0",
            direction="BUY",
            strength="STRONG",
            reasons=["trend alignment"],
            supporting_features={"rsi14": 58.0},
            invalidating_conditions=[],
        ),
        risk=None,
    )


class _FakeProvider:
    def __init__(self, *, raw_output=None, exc=None) -> None:
        self._raw_output = raw_output
        self._exc = exc
        self.calls: list[tuple[str, str]] = []

    async def analyze(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        self.calls.append((system_prompt, user_prompt))
        if self._exc is not None:
            raise self._exc
        return ProviderResponse(
            raw_output=self._raw_output,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            input_tokens=500,
            output_tokens=200,
        )


@pytest.mark.asyncio
async def test_analyze_returns_validated_output_on_success() -> None:
    provider = _FakeProvider(raw_output=VALID_RAW_OUTPUT)
    engine = AIAnalystEngine(provider, provider_name="anthropic")

    output = await engine.analyze(_context())

    assert output.suggested_action == "BUY"
    assert output.uncertainty == "MEDIUM"
    assert output.symbol == "AAPL"
    assert output.provider == "anthropic"
    assert output.model == "claude-sonnet-5"


@pytest.mark.asyncio
async def test_analyze_passes_the_symbol_and_interval_into_the_prompt() -> None:
    provider = _FakeProvider(raw_output=VALID_RAW_OUTPUT)
    engine = AIAnalystEngine(provider, provider_name="anthropic")

    await engine.analyze(_context())

    system_prompt, user_prompt = provider.calls[0]
    assert "MarketPilot AI Analyst" in system_prompt
    assert "AAPL" in user_prompt
    assert "1d" in user_prompt


@pytest.mark.asyncio
async def test_analyze_propagates_provider_errors_uncaught() -> None:
    provider = _FakeProvider(exc=AIProviderTimeoutError("Claude request timed out"))
    engine = AIAnalystEngine(provider, provider_name="anthropic")

    with pytest.raises(AIProviderTimeoutError):
        await engine.analyze(_context())


@pytest.mark.asyncio
async def test_analyze_propagates_validation_errors_for_malformed_output() -> None:
    provider = _FakeProvider(raw_output={"not": "the right shape"})
    engine = AIAnalystEngine(provider, provider_name="anthropic")

    with pytest.raises(AIValidationError):
        await engine.analyze(_context())


@pytest.mark.asyncio
async def test_analyze_propagates_validation_errors_for_unsafe_content() -> None:
    unsafe = dict(VALID_RAW_OUTPUT, thesis="You should execute the trade immediately.")
    provider = _FakeProvider(raw_output=unsafe)
    engine = AIAnalystEngine(provider, provider_name="anthropic")

    with pytest.raises(AIValidationError):
        await engine.analyze(_context())
