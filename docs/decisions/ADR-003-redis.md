# ADR-003: Redis for Caching and Pub/Sub

## Context

Some reads (portfolio summary, latest price) are hit often enough by dashboard polling that recomputing them from Postgres on every request is wasteful, and the dashboard wants near-real-time updates (new signal, new alert, price tick) without every client polling on a tight interval. Neither need justifies compromising Postgres's role as the only durable store.

## Decision

Use **Redis 7** for two purposes only: short-TTL caching of expensive read aggregates, and pub/sub fan-out for near-real-time UI push. Full detail: [data-flow.md](../data-flow.md) §2. Nothing is ever true only in Redis — anything cached there is always reconstructable from Postgres, and a `FLUSHALL` degrades performance, never correctness.

## Alternatives considered

- **No cache layer; read Postgres directly every time.** Rejected: portfolio summary computation (aggregating positions/trades) is nontrivial enough, and dashboard polling frequent enough, that this would add avoidable load for no benefit — but this was seriously considered for the MVP given the low likely request volume, and remains the fallback behavior when Redis is unavailable (see [architecture.md](../architecture.md) §7), so choosing Redis costs nothing in robustness.
- **Postgres `LISTEN/NOTIFY` instead of Redis pub/sub.** Considered for the push mechanism specifically, since it would mean one fewer moving part. Rejected because Redis pub/sub is already needed for caching, and combining both concerns in one already-present dependency is simpler than adding a second mechanism for one of the two needs.
- **A dedicated cache like Memcached.** Rejected: Redis's pub/sub covers a second need Memcached doesn't, and the operational cost of running Redis vs. Memcached is identical — no reason to run two systems for one system's worth of capability.

## Consequences

- Positive: cheap to reason about failure — Redis down means slower reads and no live push, never wrong data, because nothing authoritative lives there.
- Positive: one dependency serves two needs (cache + pub/sub), keeping the infrastructure list short for local development (`docker-compose.yml` needs one more container, not two).
- Negative: adds one more moving part to operate and monitor beyond Postgres alone. Accepted — the alternative (no cache, no push) would produce a visibly slower, less "live-feeling" dashboard, which matters for a product whose whole premise is a real-time-feeling market command center.
