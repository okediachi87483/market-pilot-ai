# ADR-004: FastAPI for the Backend

## Context

The backend needs strong request/response validation (financial data, an AI-facing schema that must be strictly enforced — [ai-architecture.md](../ai-architecture.md) §2), auto-generated API documentation, async support (for I/O-bound work: DB queries, the AI provider call, market data fetches), and to be written in Python — the natural choice given the AI/data-analysis workload (technical indicator libraries, the AI provider SDK) that would otherwise require a second language's ecosystem for that half of the system.

## Decision

Use **FastAPI** with **Pydantic v2** for all request/response schemas and **SQLAlchemy 2.0 (async)** for persistence.

## Alternatives considered

- **Django / Django REST Framework.** Rejected: Django's batteries (admin panel, ORM conventions, template engine) are mostly unused weight for an API-only backend with a separate Next.js frontend; DRF's serializer system duplicates what Pydantic already does more simply, and Django's ORM is sync-first where this system's I/O profile (external AI calls, market data fetches) benefits from async throughout.
- **Flask.** Rejected: no built-in validation or OpenAPI generation — both would need to be assembled from add-ons to reach parity with what FastAPI provides by default, for no offsetting benefit here.
- **Node.js/Express or NestJS**, unifying the whole stack in TypeScript. Seriously considered for the single-language benefit. Rejected because Python's ecosystem for technical analysis (pandas, numpy-adjacent indicator libraries), and being the language most AI provider SDKs and examples are written for, outweighs the cross-language cost — and the frontend/backend boundary is already a clean REST contract (kept in sync via generated types, [api.md](../api.md) §4), so "two languages" doesn't mean "two ways of thinking about the same data."

## Consequences

- Positive: Pydantic schemas double as both API validation and the structured-AI-output validation ([ai-architecture.md](../ai-architecture.md) §2) — one validation mental model for both "did the client send valid data" and "did the AI produce valid data," which matters given how safety-critical the latter is.
- Positive: OpenAPI schema generation is automatic and feeds the typed frontend client ([api.md](../api.md) §4) with no separate schema-authoring step to keep in sync by hand.
- Negative: Python's async ecosystem is less mature than Node's for some integrations; mitigated by FastAPI/SQLAlchemy 2.0's async support being solid for this system's actual I/O patterns (DB, HTTP calls to the AI provider and market data provider).
