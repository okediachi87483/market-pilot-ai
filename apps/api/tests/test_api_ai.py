"""API tests for /api/v1/ai. Require the live Postgres + seeded fixture
assets — auto-skipped if Postgres is unreachable (see tests/conftest.py
db_engine).

`AI_PROVIDER_API_KEY` is empty in this environment's `.env` (Step 36's
live Claude test is reported separately as skipped for that reason), so
the real dependency graph naturally exercises the "not configured" (503)
path. To also exercise the 200/422 paths that need an actual analysis,
these tests override `get_ai_analyst_service` with a service backed by
an in-process fake `AIProvider` — never the real `anthropic` SDK — via
FastAPI's own `app.dependency_overrides`, cleaned up after each test.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_analyst_service
from app.core.config import Settings
from app.db.session import get_db
from app.main import app
from app.models.asset import Asset
from app.models.signal import Signal
from app.services.ai_analyst.engine import AIAnalystEngine
from app.services.ai_analyst.service import AIAnalystService
from app.services.ai_analyst.types import ProviderResponse
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
    def __init__(self, *, raw_output=None) -> None:
        self._raw_output = raw_output if raw_output is not None else VALID_RAW_OUTPUT

    async def analyze(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        return ProviderResponse(
            raw_output=self._raw_output,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            input_tokens=500,
            output_tokens=200,
        )


@contextmanager
def _configured_ai_service(*, raw_output=None) -> Iterator[None]:
    """Overrides `get_ai_analyst_service` so a request made through
    `client` within this block is served by a fake, always-configured
    provider — used only to exercise 200/422 response shapes; every
    other test in this file relies on the real (unconfigured) wiring.

    Depends on the app's own `get_db` (not the test's `db_session`
    fixture) so FastAPI resolves the session on the same event loop it
    runs the request on — reusing `db_session` here previously caused
    an asyncpg "attached to a different loop" error, since TestClient
    drives the ASGI app on its own loop, distinct from the one
    pytest-asyncio created `db_session` on."""

    async def _override(db: AsyncSession = Depends(get_db)) -> AIAnalystService:
        market_data = MarketDataService(db)
        technical_analysis = TechnicalAnalysisService(market_data)
        engine = AIAnalystEngine(_FakeProvider(raw_output=raw_output), provider_name="anthropic")
        settings = Settings(_env_file=None, ai_analyst_cooldown_minutes=15)
        return AIAnalystService(db, technical_analysis, engine, settings)

    app.dependency_overrides[get_ai_analyst_service] = _override
    try:
        yield
    finally:
        del app.dependency_overrides[get_ai_analyst_service]


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


def test_get_ai_status_reports_not_configured(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/ai/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["available"] is False
    assert body["provider"] == "anthropic"
    assert "model" in body


def test_get_ai_status_never_exposes_a_key_field(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/ai/status")
    body = resp.json()
    serialized_keys = {k.lower() for k in body}
    assert not any("key" in k or "secret" in k or "token" in k for k in serialized_keys)


# --- not configured (real wiring) ---------------------------------------


@pytest.mark.asyncio
async def test_analyze_signal_returns_503_when_ai_not_configured(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_signal(db_session, "AAPL", "BUY", interval="1m")

    resp = client.post(f"/api/v1/ai/analyze/{signal.id}")

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "provider_error"
    assert "sk-" not in resp.text  # no stray key material in any error body


def test_analyze_unknown_signal_returns_404(client: TestClient, db_engine) -> None:
    resp = client.post(f"/api/v1/ai/analyze/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_analyze_malformed_signal_id_returns_422(client: TestClient, db_engine) -> None:
    resp = client.post("/api/v1/ai/analyze/not-a-uuid")
    assert resp.status_code == 422


def test_get_ai_analysis_unknown_id_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get(f"/api/v1/ai/analyses/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_list_ai_analyses_for_unknown_signal_returns_empty_list(
    client: TestClient, db_engine
) -> None:
    resp = client.get(f"/api/v1/ai/signals/{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_ai_analyses_returns_200(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/ai/analyses")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# --- configured (dependency override) -------------------------------------


@pytest.mark.asyncio
async def test_analyze_signal_returns_200_with_expected_shape(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_signal(db_session, "MSFT", "BUY", interval="5m")

    with _configured_ai_service():
        resp = client.post(f"/api/v1/ai/analyze/{signal.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["signal_id"] == str(signal.id)
    assert body["symbol"] == "MSFT"
    assert body["suggested_action"] == "BUY"
    assert body["uncertainty"] == "MEDIUM"
    assert body["prompt_version"] == "1.0.0"
    assert "id" in body and "generated_at" in body
    # no numeric confidence, no position sizing / stop-loss / take-profit
    # fields anywhere in the response envelope (Step 39: no fake AI)
    assert "confidence" not in body
    assert "position_size" not in body
    assert "stop_loss" not in body
    assert "take_profit" not in body


@pytest.mark.asyncio
async def test_analyze_signal_unsafe_content_returns_422(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_signal(db_session, "NVDA", "BUY", interval="15m")
    unsafe = dict(VALID_RAW_OUTPUT, thesis="You should execute the trade immediately.")

    with _configured_ai_service(raw_output=unsafe):
        resp = client.post(f"/api/v1/ai/analyze/{signal.id}")

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_analyze_signal_twice_is_deduplicated_not_conflicted(
    client: TestClient, db_session, db_engine
) -> None:
    """Unlike /risk/evaluate (409 on a second call), a repeated
    /ai/analyze within the cooldown window returns 200 with the same
    analysis — AI analysis is advisory and repeatable, not a one-shot
    state transition (Step 17)."""
    signal = await _make_signal(db_session, "TSLA", "BUY", interval="1h")

    with _configured_ai_service():
        first = client.post(f"/api/v1/ai/analyze/{signal.id}")
        second = client.post(f"/api/v1/ai/analyze/{signal.id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_get_and_list_after_a_successful_analysis(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_signal(db_session, "AMZN", "BUY", interval="1d")

    with _configured_ai_service():
        created = client.post(f"/api/v1/ai/analyze/{signal.id}").json()

    fetched = client.get(f"/api/v1/ai/analyses/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]

    listed = client.get(f"/api/v1/ai/signals/{signal.id}")
    assert listed.status_code == 200
    assert any(row["id"] == created["id"] for row in listed.json())

    filtered = client.get("/api/v1/ai/analyses", params={"symbol": "AMZN"})
    assert filtered.status_code == 200
    assert any(row["id"] == created["id"] for row in filtered.json())
