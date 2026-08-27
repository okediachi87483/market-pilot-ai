"""Application settings, loaded once from environment variables.

This is the single place `os.environ` is read in the backend — every other
module receives configuration through `get_settings()`, never by reading
the environment directly. See docs/security.md §2.
"""

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    app_env: str = "development"
    api_port: int = 8000
    log_level: str = "INFO"

    cors_origins: str = "http://localhost:3000"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "marketpilot"
    postgres_user: str = "marketpilot"
    postgres_password: str = "marketpilot"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Represented architecturally per docs/ai-architecture.md; no key is
    # required to run the Phase 2 foundation. Phase 8 (docs/ai-analyst.md)
    # is the first phase that actually calls this provider — an empty
    # key here means "AI status = unavailable/not configured", never a
    # startup crash (Step 4).
    ai_provider: str = "anthropic"
    ai_model: str = "claude-sonnet-5"
    ai_provider_api_key: str | None = None

    # Phase 8 cost controls (docs/ai-analyst.md §"Cost controls", Step
    # 25) — bounded output, a request timeout, and a per-signal cooldown
    # so a chatty client can't rack up unbounded Claude spend.
    ai_analyst_max_output_tokens: int = 1024
    ai_analyst_timeout_seconds: float = 30.0
    ai_analyst_cooldown_minutes: int = 15

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_provider_api_key)

    # Phase 6/7: the one simulated paper-trading account's starting cash
    # and equity — see docs/paper-trading.md §"Cash accounting". Read
    # once, at account-creation time (the initial Alembic migration
    # seeds the single `paper_accounts` row from this value); changing
    # it afterward does not retroactively alter an existing account.
    risk_starting_equity: Decimal = Decimal("100000")

    # Phase 7: simulated trading fee, applied to every fill's notional
    # value (docs/paper-trading.md §"Fee model"). 0.001 = 10 basis
    # points — a representative flat commission rate, not hard-coded
    # throughout the paper-trading business logic.
    paper_trading_fee_rate: Decimal = Decimal("0.001")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
