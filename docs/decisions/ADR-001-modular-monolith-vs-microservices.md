# ADR-001: Modular Monolith vs. Microservices

## Context

MarketPilot AI has thirteen conceptually distinct responsibilities (ingestion, normalization, indicators, signals, AI analysis, risk, paper trading, portfolio, alerting, backtesting, audit, API, frontend). A naive reading of "clean separation of concerns" suggests one service per responsibility. The MVP has one operator, no proven load profile, and a hard requirement (the AI must never bypass the risk engine) that is easiest to guarantee when the call path between them is a direct, synchronous, in-process function call rather than a network hop that can be skipped, retried into a duplicate state, or raced.

## Decision

Build a **modular monolith**: one deployable FastAPI backend process, composed from independently-owned internal packages (`packages/market_data`, `packages/signal_engine`, `packages/risk_engine`, etc.), each with its own models, service layer, and tests, communicating only through each package's public `service.py`. One Next.js frontend. No inter-service network calls, no message broker, no service mesh in the MVP.

## Alternatives considered

- **Microservices per responsibility.** Rejected for the MVP: it multiplies operational surface (13 deployables, network auth between them, distributed tracing to debug what a stack trace would show for free) without a load or team-scaling problem that justifies it yet. It also makes the AI-cannot-bypass-risk invariant *harder* to guarantee, not easier — a network boundary between `ai-engine` and `risk-engine` is one more place a retry, a race, or a missed validation could let something through that a direct function call cannot.
- **Single undifferentiated codebase (no package boundaries).** Rejected: this is what "modular" in "modular monolith" is explicitly avoiding. Without enforced package boundaries, the market-data-to-dashboard pipeline tends to accrete cross-cutting imports until nothing is independently testable or reasoned about — the packages exist specifically to prevent that.

## Consequences

- Positive: one thing to deploy, one database transaction can span "approve and create an order," no distributed-systems failure modes (partial network failure, message loss, eventual-consistency bugs) to design around in the MVP.
- Positive: each package is independently unit-testable and the boundary is enforced by Python import structure, not just convention — a lint rule can catch a package reaching into another's internals.
- Negative: cannot scale or deploy one package independently of the others yet (e.g. `ai-engine` under heavy LLM latency can't get its own replica count without scaling the whole API process). Accepted as the right tradeoff for current scale — see [architecture.md](../architecture.md) §9 for the extraction path if this changes.
- Negative: a bug in one package can, in principle, crash the whole process, where a microservice failure would be isolated. Mitigated by the pipeline's fail-closed design ([architecture.md](../architecture.md) §7) — no single stage's failure is allowed to corrupt state, whether isolated in its own process or not.
