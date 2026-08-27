"""The provider boundary (Step 2/3):

    AIAnalyst (engine.py)
            |
            v
    AIProvider (this module's Protocol)
            |
            v
    ClaudeProvider (this module's only implementation)

Nothing outside this module imports the `anthropic` SDK — every other
piece of the AI Analyst (prompts, parsing, orchestration, persistence)
depends only on the plain dataclasses in `types.py`. A future second
provider (a different model vendor) is a second implementation of
`AIProvider`, not a rewrite of anything that calls it.
"""

from __future__ import annotations

from typing import Protocol

import anthropic

from app.services.ai_analyst.prompts import RESPONSE_TOOL_NAME, RESPONSE_TOOL_SCHEMA
from app.services.ai_analyst.types import (
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    ProviderResponse,
)


class AIProvider(Protocol):
    async def analyze(self, system_prompt: str, user_prompt: str) -> ProviderResponse: ...


class ClaudeProvider:
    """Forces structured output via Claude's tool-use mechanism (Step
    7/10) rather than asking for free-form text and regex-parsing it —
    `tool_choice` makes the model's only possible reply a call to
    `submit_analysis`, and the SDK's `input_schema` conformance is
    itself part of the safety boundary (docs/ai-analyst.md
    §"Structured output")."""

    def __init__(
        self, *, api_key: str, model: str, max_output_tokens: int, timeout_seconds: float
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._max_output_tokens = max_output_tokens

    async def analyze(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        try:
            # The tool schema/choice are built from plain dicts in
            # prompts.py (Step 2: no `anthropic` SDK types outside this
            # module) rather than the SDK's own TypedDicts, so this call
            # doesn't structurally match any of the SDK's precise
            # overloads — a real SDK-boundary mismatch, not a type bug
            # in this codebase.
            response = await self._client.messages.create(  # type: ignore[call-overload]
                model=self._model,
                max_tokens=self._max_output_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[RESPONSE_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": RESPONSE_TOOL_NAME},
            )
        except anthropic.APITimeoutError as exc:
            raise AIProviderTimeoutError("Claude request timed out") from exc
        except anthropic.AuthenticationError as exc:
            # Never include the key or the SDK's own message verbatim —
            # it can echo request headers in some error paths.
            raise AIProviderUnavailableError("Claude authentication failed") from exc
        except anthropic.RateLimitError as exc:
            raise AIProviderUnavailableError("Claude rate limit exceeded") from exc
        except anthropic.APIConnectionError as exc:
            raise AIProviderUnavailableError("Could not connect to Claude") from exc
        except anthropic.APIStatusError as exc:
            raise AIProviderUnavailableError(
                f"Claude returned an error status: {exc.status_code}"
            ) from exc
        except anthropic.APIError as exc:
            raise AIProviderUnavailableError(
                f"Claude provider error: {type(exc).__name__}"
            ) from exc

        tool_use_block = next(
            (block for block in response.content if block.type == "tool_use"), None
        )
        if tool_use_block is None:
            raise AIProviderUnavailableError("Claude did not return a submit_analysis tool call")

        usage = response.usage
        return ProviderResponse(
            raw_output=tool_use_block.input,
            model=response.model,
            stop_reason=response.stop_reason,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
        )
