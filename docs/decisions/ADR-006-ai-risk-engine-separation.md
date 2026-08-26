# ADR-006: Hard Separation Between the AI Engine and the Risk Engine

## Context

MarketPilot's single non-negotiable product requirement is that AI output can never directly cause a trade or override risk limits. This has to be true architecturally, not just as a coding convention someone could accidentally violate under deadline pressure — see [ai-architecture.md](../ai-architecture.md) §4.

## Decision

`ai-engine` and `risk-engine` are separate packages with a one-way, narrow interface between them: `risk-engine` reads a validated `AIAnalysis.suggested_action` (one of five enum values: long/short/hold/close/none) as the *direction* of a proposed trade; it independently computes position size, stop-loss, and take-profit from `risk_rules` and current portfolio state. No numeric field the AI produces (`entry_zone_*`, `stop_loss`, `take_profit_*`, `confidence`) is ever read as an input to a risk calculation. `ai-engine` has no write access to `risk_rules`, `orders`, `positions`, or `portfolios` — its only table is `ai_analyses`.

## Alternatives considered

- **Let the AI propose a fully-specified order (size, stop, target) and have the risk engine only approve/reject it.** Rejected: this makes the risk engine's safety property contingent on the AI's numbers being reasonable, which is exactly the failure mode a prompt injection, hallucination, or adversarial input could exploit — a "moderate confidence, 500% of portfolio" suggestion would need the risk engine to catch it as a special case rather than the architecture making it structurally impossible. Computing size independently removes the class of bug entirely rather than defending against it.
- **A single combined `ai_risk` package**, reasoning that they're both "decision" logic. Rejected: co-locating them makes the boundary a matter of internal discipline (which function calls which) instead of a package boundary a linter and a code reviewer can both verify from the import graph alone.
- **Feature-flag or config toggle to let the AI's suggested size through "when confidence is high."** Never seriously considered — this is precisely the shortcut the product requirement exists to rule out, and it would reintroduce the exact risk this ADR is written to close off.

## Consequences

- Positive: the safety property is verifiable by inspection — "does `risk_engine` import anything from `ai_engine` beyond the `AIAnalysis` enum field" is a question with a checkable answer, not a matter of trusting every future contributor's judgment.
- Positive: the risk engine's behavior is identical whether a proposed trade came from the AI, a deterministic signal with no AI involvement, or a user typing an order directly into `POST /trades` — one risk path, not "the AI path" and "the manual path" that could drift apart.
- Negative: the AI's suggested entry/stop/target zones, while shown to the user for context ([ui-design-system.md](../ui-design-system.md), the AI Analyst screen), may not match what the risk engine would actually apply if the trade is approved — the UI must make this distinction clear (AI's suggestion vs. engine-applied values) rather than implying they're the same number, which is a UX requirement this ADR imposes on Phase 2 implementation.
