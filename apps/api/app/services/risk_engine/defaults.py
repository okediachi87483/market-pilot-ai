"""The one authoritative set of default risk-policy values (Step 3: "Do
NOT hard-code risk values throughout business logic. There should be one
authoritative risk-policy configuration."). Consumed exactly once, by the
Alembic migration that seeds the initial active `RiskPolicy` row — every
other reader of a policy's numbers reads the database row (or a
`RiskPolicySnapshot` built from it), never this module directly.

Every value is deliberately conservative for a fresh paper-trading
account. Full rationale for each: docs/risk-engine.md §"Policy defaults".
"""

from decimal import Decimal

DEFAULT_POLICY_NAME = "default"

# A single position's cost basis may not exceed 5% of equity — no single
# trade can meaningfully damage the account on its own.
DEFAULT_MAX_POSITION_SIZE_PCT = Decimal("5.00")

# Total open exposure may not exceed 50% of equity — at least half the
# account stays uncommitted at all times.
DEFAULT_MAX_PORTFOLIO_EXPOSURE_PCT = Decimal("50.00")

# No new positions once the current trading day's realized P/L is worse
# than -3% of equity — a hard stop for a bad day.
DEFAULT_MAX_DAILY_LOSS_PCT = Decimal("3.00")

# No new positions once equity has fallen more than 15% from its
# high-water mark — a circuit breaker for a bad stretch, not just a bad
# day.
DEFAULT_MAX_DRAWDOWN_PCT = Decimal("15.00")

# Every approved BUY gets a stop 2% below entry — engine-computed,
# never taken from the signal or any future AI suggestion (Step 9).
DEFAULT_STOP_LOSS_PCT = Decimal("2.00")

# Every approved BUY gets a take-profit 4% above entry — a 2:1
# reward:risk ratio against the default stop, a standard conservative
# baseline (Step 10).
DEFAULT_TAKE_PROFIT_PCT = Decimal("4.00")

# At most 5 open positions at once — bounds how many independent bets
# can be live simultaneously regardless of how small each is.
DEFAULT_MAX_CONCURRENT_POSITIONS = 5

# One hour of no new entries after a losing trade closes — a brief,
# deliberate pause rather than a same-day ban.
DEFAULT_COOLDOWN_AFTER_LOSS_MINUTES = 60

# How much of equity the account is willing to lose on a single trade if
# its stop is hit — this is what actually drives position sizing (Step
# 7); `max_position_size_pct` above is the separate hard ceiling that
# constrains the result. 1% is the standard conservative retail-risk-
# management baseline ("never risk more than 1-2% of the account on one
# trade"). Not one of Step 3's eight listed fields — added because Step 7
# explicitly requires a "maximum risk per trade" input distinct from the
# hard position-size cap; see docs/risk-engine.md §"Position sizing".
DEFAULT_RISK_PER_TRADE_PCT = Decimal("1.00")
