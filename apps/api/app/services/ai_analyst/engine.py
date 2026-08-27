"""AIAnalystEngine — the orchestration core of Phase 8 (Step 2).

Combines the provider call and the parser's validation into one
`analyze()` call. Independent of FastAPI and the database (Step 2's "as
independent as practical" — a network call to the provider is
unavoidable here, unlike `SignalEngine`/`RiskEngine`'s fully pure
cores, but nothing in this module touches SQLAlchemy or knows
`AIAnalystService` exists).
"""

from __future__ import annotations

from app.services.ai_analyst.client import AIProvider
from app.services.ai_analyst.parser import parse_and_validate
from app.services.ai_analyst.prompts import SYSTEM_PROMPT, build_user_prompt
from app.services.ai_analyst.types import AIAnalysisContext, AIAnalysisOutput


class AIAnalystEngine:
    def __init__(self, provider: AIProvider, *, provider_name: str) -> None:
        self.provider = provider
        self.provider_name = provider_name

    async def analyze(self, context: AIAnalysisContext) -> AIAnalysisOutput:
        user_prompt = build_user_prompt(context)
        response = await self.provider.analyze(SYSTEM_PROMPT, user_prompt)
        return parse_and_validate(
            response, symbol=context.symbol, interval=context.interval, provider=self.provider_name
        )
