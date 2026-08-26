# ADR-002: PostgreSQL as the System of Record

## Context

MarketPilot's data is overwhelmingly relational (users own watchlists own items; portfolios own positions own trades; orders reference signals reference indicators) and includes monetary values that must never lose precision, plus a requirement for an immutable audit trail. The database needs to be the single durable source of truth for everything — see [architecture.md](../architecture.md) principle 5.

## Decision

Use **PostgreSQL 16** as the only durable data store, with SQLAlchemy 2.0 (async) as the ORM/query layer and Alembic for migrations. Full schema: [database.md](../database.md).

## Alternatives considered

- **MongoDB / document store.** Rejected: MarketPilot's data is relational by nature (foreign keys, joins across signals/indicators/analyses/orders are the normal query pattern, not the exception), and a document model would either denormalize financial data dangerously (multiple copies of a price that can drift) or reinvent joins in application code. No requirement here (schema flexibility, horizontal write scaling) justifies giving up relational integrity guarantees.
- **MySQL.** Rejected: PostgreSQL's `NUMERIC` type, richer JSONB support (used for `indicators.metadata`, `signals.supporting_indicator_ids`, `audit_logs.before/after`), and stronger constraint/check support fit this schema better; no requirement favors MySQL specifically.
- **SQLite for local dev, Postgres for production.** Rejected: divergent dev/prod databases is a classic source of "works locally, breaks in production" bugs, especially around `NUMERIC` precision and JSONB behavior, both load-bearing here. Docker Compose makes running real Postgres locally free.

## Consequences

- Positive: exact-decimal `NUMERIC` types make the no-floating-point-money rule ([database.md](../database.md) §1) straightforward to enforce at the schema level, not just by convention in Python.
- Positive: one database to operate, back up, and reason about consistency for — no cross-store consistency problem between "the real data" and "the fast data" (that's what Redis is for, and Redis is explicitly never authoritative — [data-flow.md](../data-flow.md) §2).
- Negative: all write load goes through one primary in the MVP. Accepted; read replicas are the first scaling lever if this becomes a bottleneck ([architecture.md](../architecture.md) §9), well before any data is migrated elsewhere.
