"""Integration tests: AIAnalystService against a live Postgres. Requires
`docker compose up -d postgres redis` — auto-skipped otherwise (see
tests/conftest.py db_engine).

Uses a fake `AIProvider` (never the real `anthropic` SDK — the live
Claude test, if run at all, lives elsewhere and is conditional on
`AI_PROVIDER_API_KEY` being set) so these tests are deterministic and
free, while still exercising the real database round-trip: context
assembly from `Signal` + a live `TechnicalAnalysisService` snapshot,
persistence, cooldown/dedup, and error translation.

Also covers Step 30 (AI safety invariants) and Step 31 (AI-vs-signal
disagreement) — both as integration-level assertions, since they depend
on how `AIAnalystService.analyze_signal` actually touches the database.

`interval` must be one of `SUPPORTED_INTERVALS` ("1m", "5m", "15m",
"1h", "1d") — `TechnicalAnalysisService.get_snapshot` fetches real
market data for it via `MarketDataService`, unlike `Signal.interval`
alone, which has no such constraint.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select

from app.core.config import Settings
from app.core.errors import NotFoundError, ProviderError, ValidationAppError
from app.models.ai_analysis import AIAnalysis
from app.models.asset import Asset
from app.models.signal import Signal
from app.services.ai_analyst.engine import AIAnalystEngine
from app.services.ai_analyst.service import AIAnalystService
from app.services.ai_analyst.types import (
    AIProviderTimeoutError,
    ProviderResponse,
)
from app.services.market_data.service import MarketDataService
from app.services.technical_analysis.service import TechnicalAnalysisService

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


class _FakeProvider:
    def __init__(self, *, raw_output=None, exc=None) -> None:
        self._raw_output = raw_output if raw_output is not None else VALID_RAW_OUTPUT
        self._exc = exc
        self.call_count = 0

    async def analyze(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        self.call_count += 1
        if self._exc is not None:
            raise self._exc
        return ProviderResponse(
            raw_output=self._raw_output,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            input_tokens=500,
            output_tokens=200,
        )


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _service(db_session, *, provider=None, cooldown_minutes: int = 15) -> AIAnalystService:
    market_data = MarketDataService(db_session)
    technical_analysis = TechnicalAnalysisService(market_data)
    engine = AIAnalystEngine(provider, provider_name="anthropic") if provider is not None else None
    settings = _settings(ai_analyst_cooldown_minutes=cooldown_minutes)
    return AIAnalystService(db_session, technical_analysis, engine, settings)


async def _make_signal(db_session, symbol: str, signal_type: str, *, interval: str) -> Signal:
    result = await db_session.execute(select(Asset).where(Asset.symbol == symbol))
    asset = result.scalar_one()
    row = Signal(
        asset_id=asset.id,
        interval=interval,
        signal=signal_type,
        strategy_id="trend_momentum",
        strategy_version="1.0.0",
        strength="STRONG" if signal_type in ("BUY", "SELL") else None,
        market_regime="BULLISH" if signal_type == "BUY" else "BEARISH",
        reasons=["test fixture signal"],
        supporting_features={"rsi14": 55.0},
        invalidating_conditions=[],
        status="CANDIDATE",
        generated_at=datetime.now(UTC),
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


# --- status ------------------------------------------------------------


def test_status_reports_the_expected_shape(db_session) -> None:
    service = _service(db_session, provider=_FakeProvider())
    status = service.get_status()
    # get_status() reads from Settings.ai_configured (a real API key),
    # not from whether an engine happens to be wired up for this test —
    # the fake provider bypasses that entirely, so this only proves the
    # response shape, not a specific configured/available value.
    assert set(status.keys()) == {"configured", "available", "provider", "model"}
    assert status["available"] == status["configured"]


# --- not configured ------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_signal_raises_provider_error_when_not_configured(db_session) -> None:
    signal = await _make_signal(db_session, "AAPL", "BUY", interval="5m")
    service = _service(db_session, provider=None)

    with pytest.raises(ProviderError):
        await service.analyze_signal(signal.id)


@pytest.mark.asyncio
async def test_analyze_unknown_signal_raises_not_found(db_session) -> None:
    service = _service(db_session, provider=_FakeProvider())
    with pytest.raises(NotFoundError):
        await service.analyze_signal(uuid.uuid4())


# --- success path --------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_signal_persists_and_returns_analysis(db_session) -> None:
    signal = await _make_signal(db_session, "MSFT", "BUY", interval="15m")
    service = _service(db_session, provider=_FakeProvider())

    row = await service.analyze_signal(signal.id)

    assert row.signal_id == signal.id
    assert row.asset_id == signal.asset_id
    assert row.suggested_action == "BUY"
    assert row.uncertainty == "MEDIUM"
    assert row.provider == "anthropic"
    assert row.prompt_version == "1.0.0"

    fetched = await service.get_analysis(row.id)
    assert fetched.id == row.id


@pytest.mark.asyncio
async def test_get_analysis_unknown_id_raises_not_found(db_session) -> None:
    service = _service(db_session, provider=_FakeProvider())
    with pytest.raises(NotFoundError):
        await service.get_analysis(uuid.uuid4())


@pytest.mark.asyncio
async def test_list_analyses_filters_by_signal_id(db_session) -> None:
    signal = await _make_signal(db_session, "NVDA", "BUY", interval="1h")
    service = _service(db_session, provider=_FakeProvider())
    row = await service.analyze_signal(signal.id)

    rows = await service.list_for_signal(signal.id)

    assert len(rows) == 1
    assert rows[0].id == row.id


@pytest.mark.asyncio
async def test_list_analyses_filters_by_symbol(db_session) -> None:
    signal = await _make_signal(db_session, "TSLA", "BUY", interval="1d")
    service = _service(db_session, provider=_FakeProvider())
    await service.analyze_signal(signal.id)

    rows = await service.list_analyses(symbol="TSLA")

    assert len(rows) >= 1
    assert all(row.asset_id == signal.asset_id for row in rows)


# --- cooldown / dedup (Step 17) ------------------------------------------


@pytest.mark.asyncio
async def test_repeated_analysis_within_cooldown_returns_the_same_row(db_session) -> None:
    signal = await _make_signal(db_session, "AMZN", "BUY", interval="1m")
    provider = _FakeProvider()
    service = _service(db_session, provider=provider, cooldown_minutes=15)

    first = await service.analyze_signal(signal.id)
    second = await service.analyze_signal(signal.id)

    assert first.id == second.id
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_repeated_analysis_past_cooldown_creates_a_new_row(db_session) -> None:
    signal = await _make_signal(db_session, "AAPL", "BUY", interval="1h")
    provider = _FakeProvider()
    service = _service(db_session, provider=provider, cooldown_minutes=0)

    first = await service.analyze_signal(signal.id)
    second = await service.analyze_signal(signal.id)

    assert first.id != second.id
    assert provider.call_count == 2

    rows = await service.list_for_signal(signal.id)
    assert len(rows) == 2


# --- error translation -----------------------------------------------------


@pytest.mark.asyncio
async def test_provider_timeout_is_translated_to_provider_error(db_session) -> None:
    signal = await _make_signal(db_session, "MSFT", "BUY", interval="5m")
    provider = _FakeProvider(exc=AIProviderTimeoutError("Claude request timed out"))
    service = _service(db_session, provider=provider)

    with pytest.raises(ProviderError):
        await service.analyze_signal(signal.id)


@pytest.mark.asyncio
async def test_unsafe_content_is_translated_to_validation_app_error(db_session) -> None:
    signal = await _make_signal(db_session, "NVDA", "BUY", interval="15m")
    unsafe = dict(VALID_RAW_OUTPUT, thesis="You should execute the trade immediately.")
    provider = _FakeProvider(raw_output=unsafe)
    service = _service(db_session, provider=provider)

    with pytest.raises(ValidationAppError):
        await service.analyze_signal(signal.id)

    rows = await service.list_for_signal(signal.id)
    assert rows == []  # a rejected analysis must not be persisted


@pytest.mark.asyncio
async def test_malformed_schema_is_translated_to_validation_app_error(db_session) -> None:
    signal = await _make_signal(db_session, "TSLA", "BUY", interval="1h")
    provider = _FakeProvider(raw_output={"not": "the right shape"})
    service = _service(db_session, provider=provider)

    with pytest.raises(ValidationAppError):
        await service.analyze_signal(signal.id)


# --- Step 30: AI safety invariants ------------------------------------------


def test_ai_analysis_model_has_no_position_sizing_or_price_fields() -> None:
    """Structural guarantee: the AI Analyst's persisted output has no
    column through which a position size, stop-loss, or take-profit
    could ever be recorded — those remain the Risk Engine's exclusive
    domain (docs/risk-engine.md)."""
    columns = {c.key for c in inspect(AIAnalysis).columns}
    forbidden = {
        "position_size",
        "stop_loss",
        "stop_loss_price",
        "take_profit",
        "take_profit_price",
    }
    assert columns.isdisjoint(forbidden)


@pytest.mark.asyncio
async def test_analyze_signal_never_changes_the_signal_status(db_session) -> None:
    """Unlike RiskService.evaluate_signal (which transitions CANDIDATE ->
    RISK_APPROVED/RISK_REJECTED), AI analysis is purely advisory — it
    must never touch `Signal.status`."""
    signal = await _make_signal(db_session, "AAPL", "BUY", interval="15m")
    service = _service(db_session, provider=_FakeProvider())

    await service.analyze_signal(signal.id)

    await db_session.refresh(signal)
    assert signal.status == "CANDIDATE"


@pytest.mark.asyncio
async def test_analyze_signal_never_changes_the_signal_direction(db_session) -> None:
    signal = await _make_signal(db_session, "MSFT", "BUY", interval="1d")
    # The AI's suggested_action disagrees with the deterministic signal.
    disagreeing = dict(VALID_RAW_OUTPUT, suggested_action="SELL")
    service = _service(db_session, provider=_FakeProvider(raw_output=disagreeing))

    row = await service.analyze_signal(signal.id)

    await db_session.refresh(signal)
    assert signal.signal == "BUY"  # untouched by the AI's own opinion
    assert row.suggested_action == "SELL"  # the AI's opinion, stored separately


# --- Step 31: AI disagreement — all BUY/SELL/HOLD combinations -------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "signal_direction,ai_suggested_action,interval",
    [
        ("BUY", "BUY", "1m"),
        ("BUY", "SELL", "5m"),
        ("BUY", "HOLD", "15m"),
        ("SELL", "BUY", "1h"),
        ("SELL", "SELL", "1d"),
        ("SELL", "HOLD", "1m"),
    ],
)
async def test_ai_suggestion_is_recorded_independently_of_signal_direction(
    db_session, signal_direction, ai_suggested_action, interval
) -> None:
    symbol = "AAPL" if signal_direction == "BUY" else "MSFT"
    signal = await _make_signal(db_session, symbol, signal_direction, interval=interval)
    raw_output = dict(VALID_RAW_OUTPUT, suggested_action=ai_suggested_action)
    service = _service(db_session, provider=_FakeProvider(raw_output=raw_output))

    row = await service.analyze_signal(signal.id)

    await db_session.refresh(signal)
    assert signal.signal == signal_direction  # the deterministic signal never moves
    assert row.suggested_action == ai_suggested_action  # the AI's opinion, whatever it is
