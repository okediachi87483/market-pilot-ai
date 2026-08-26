# ADR-007: Paper Trading First, No Real Execution

## Context

MarketPilot analyzes markets and proposes trades using AI-assisted reasoning over live-ish data. Connecting that to a real brokerage or real funds carries financial, legal, and safety risk that has no place in an MVP whose purpose is to validate the analysis-and-risk pipeline itself.

## Decision

The MVP is **paper trading only**. `paper-trading` is the sole execution path, implemented against a `BrokerAdapter`-shaped interface it defines internally; there is no code in this architecture that calls a real brokerage API, and `portfolios.mode` is constrained to the single value `'paper'` at the schema level ([database.md](../database.md)). "Profit Protection" ([profit-protection.md](../profit-protection.md)) is explicitly a monitoring/alerting system, never a withdrawal system — it has no code path to move money because there is no real money in this system to move.

## Alternatives considered

- **Build real-brokerage integration behind a feature flag, off by default.** Rejected: a feature flag is a runtime toggle, not an architectural boundary — the risk of it being flipped on prematurely, misconfigured, or bypassed is a risk this system should not carry at all in its first version. Not building the capability is a stronger guarantee than building it and disabling it.
- **Support both paper and live from day one, sharing the same `paper-trading` package with a mode switch.** Rejected: this couples the design of the paper-trading simulation (fill modeling, fee simulation) to constraints a real broker integration would impose (partial fills, order rejection, latency, real settlement), before there's a reason to pay that design cost. The `BrokerAdapter` interface exists precisely so a real implementation can be *added* later without this package's existing consumers (risk engine, portfolio) changing — see the interface note in [architecture.md](../architecture.md) §2 principle 6.

## Consequences

- Positive: the entire system can be developed, demoed, and iterated on with zero financial or regulatory exposure — a materially safer default for an AI-assisted trading product's first version.
- Positive: the `BrokerAdapter` boundary means adding real execution later is additive (a new adapter implementation) rather than a rewrite of `risk-engine`, `portfolio`, or anything upstream of `paper-trading`.
- Negative: paper fills are simulated (a slippage/fee model, not real market microstructure), so paper performance will not perfectly predict real performance if real execution is ever added — this is disclosed to the user wherever performance is shown ([ui-design-system.md](../ui-design-system.md) hedged-language requirement) rather than presented as a guarantee.
