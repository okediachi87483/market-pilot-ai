# MarketPilot AI — Paper Trading Engine

Phase 7. **This system is paper trading only.** There is no real brokerage integration, no real order submission, no real account, no real-money movement, and no withdrawals or deposits anywhere in this codebase — see [ADR-007](decisions/ADR-007-paper-trading-first.md). The Paper Trading Engine consumes only `RISK_APPROVED` signals; a `CANDIDATE` or `RISK_REJECTED` signal can never become a paper order.

## 1. Architecture

```
RISK ENGINE (Phase 6)
        │
        ▼
Signal (status: RISK_APPROVED) + RiskEvaluation (calculated_position_size, ...)
        │
        ▼
PaperTradingService.execute_signal()   — app/services/paper_trading/service.py
        │
        ├─ ExecutionAdapter.fill()     — app/services/paper_trading/execution.py
        │     (simulates a MARKET fill against live market data)
        │
        └─ PaperTradingEngine          — app/services/paper_trading/engine.py
              (pure: applies the fill to the existing position, if any)
        │
        ▼
PaperOrder + PaperFill + PaperPosition + PaperAccount.cash   (one transaction)
        │
        ▼
compute_portfolio_state()              — app/services/paper_trading/portfolio.py
        │
        ├──▶ risk_engine.PortfolioStateProvider   (Phase 6's checks now react to this)
        └──▶ API (docs/api.md) → Paper Trading Center UI
```

`app/services/paper_trading/{types,pricing,engine}.py` are independent of FastAPI, SQLAlchemy, Redis, the frontend, AI, and any broker API (Step 2) — plain dataclasses in, plain dataclasses out, mirroring `signal_engine`/`risk_engine`'s own core/edge split. `execution.py` and `service.py` are the only pieces that touch the database or `MarketDataService`.

## 2. Database schema (Step 3)

Four tables, `app/models/paper_trading.py`:

| Table | Purpose |
|---|---|
| `paper_accounts` | The one simulated cash ledger (§6) — exactly one row, seeded from `RISK_STARTING_EQUITY` by the initial migration. |
| `paper_orders` | One row per execution attempt — `signal_id` (nullable, `UNIQUE`), `asset_id`, `side`, `order_type`, `quantity`, `requested_price`, `status`, `filled_quantity`, `average_fill_price`, `rejection_reason`, `created_at`/`submitted_at`/`filled_at`/`cancelled_at`. |
| `paper_fills` | One row per simulated execution — `order_id`, `asset_id`, `side`, `quantity`, `fill_price`, `fee`, `realized_pnl` (nullable — only a closing/reducing SELL sets it), `timestamp`. |
| `paper_positions` | One row per asset ever held — `asset_id`, `quantity`, `avg_entry_price`, `realized_pnl` (cumulative), `status`, `opened_at`/`updated_at`/`closed_at`. |

**Deliberately not stored**: `current_price`, `unrealized_pnl`, `market_value` — Step 3 suggested these as position fields, but they depend on a live price that changes continuously; persisting them would go stale between writes. Computed on every read instead (§9), the same choice already made for technical-analysis indicators (`docs/technical-analysis.md` §10) and Phase 6's portfolio snapshot. All monetary/quantity columns use the project's standard `NUMERIC(20,8)`/`NUMERIC(28,10)` precision (`docs/database.md` §1) — never floats.

**Constraints that matter**: `paper_orders.signal_id` is `UNIQUE` (the idempotency key, §14) but nullable — Postgres treats every `NULL` as distinct, so any number of non-signal-driven close orders can coexist. `paper_positions` has a partial unique index on `asset_id WHERE status = 'OPEN'` (Step 9: "do not create duplicate active positions for the same asset"), the same pattern `risk_policies.is_active` already uses. `cash >= 0`, `quantity >= 0`, `filled_quantity <= quantity` are all enforced as database `CHECK` constraints, not just application logic — proven directly in `tests/test_paper_data_consistency.py`.

## 3. Order lifecycle (Step 4)

```
PENDING ──▶ FILLED
PENDING ──▶ REJECTED
```

`PENDING` is the only non-terminal state. No code path ever moves a `FILLED`/`REJECTED`/`CANCELLED` order to another status — `PaperTradingService` computes the entire outcome (including whether cash is sufficient) before ever setting a terminal status, so `FILLED → PENDING` and `CANCELLED → FILLED` are structurally impossible, not just discouraged. `CANCELLED` is defined in the schema (`ORDER_STATUSES`) but nothing writes it yet — reserved for a future explicit-cancel feature, the same "defined but not yet reachable" pattern Phase 5 used for `Signal.EXPIRED`.

## 4. Order types (Step 5)

`MARKET` only. No limit, stop-limit, trailing-stop, options, futures, or margin — none of that is required by the current architecture, and Step 5 explicitly asks to keep this phase focused. `order_type` is still a real column (`CHECK (order_type = 'MARKET')`), so adding a second type later is a schema-compatible extension, not a rewrite.

## 5. Fill model (Step 6)

`fill_price` is always the current market price — for both BUY and SELL, from the same `MarketDataService.get_quote()` every other part of the platform reads (Phase 3). **No slippage model is implemented.** The architecture allows a deterministic one; none was added, since nothing in this phase requires it and an unrequested model would be unearned complexity. Documented as a limitation (§17) rather than silently approximated.

## 6. Fee model (Step 7)

```
fee = notional × fee_rate          (notional = quantity × fill_price)
```

`fee_rate` is `PAPER_TRADING_FEE_RATE` (`.env.example`, default `0.001` = 10 basis points) — read once from `Settings`, never hard-coded in business logic (`app/services/paper_trading/pricing.py::compute_fee`). Fees always reduce **realized** P/L (subtracted in `compute_realized_pnl`, §8) and always move **cash** (§6): a BUY's fee is paid out of cash at the fill; a SELL's fee is deducted from the proceeds credited to cash. Fees never adjust `fill_price` itself (`docs/database.md` §1's principle: the fill price is always the true execution price, fees are always visible and auditable separately) and never touch **unrealized** P/L (§8) — an open position hasn't incurred an exit fee yet.

## 7. Cash accounting (Step 8)

`paper_accounts.cash` is the one directly-mutated balance, seeded from `RISK_STARTING_EQUITY` (already introduced in Phase 6) by the initial migration — no money is ever created out of thin air; every unit of cash the account has traces back to that one seed value plus/minus real fills.

```
BUY:  cash -= (fill_price × quantity + fee)
SELL: cash += (fill_price × quantity − fee)
```

Both happen in the same database transaction as the order/fill/position writes (§13) — cash can never drift out of sync with the trade history that justified it. `cash >= 0` is a database `CHECK` constraint, and `PaperTradingService.execute_signal` verifies sufficient cash *before* filling — if `required_cash > cash`, the order is written as `REJECTED` with a `rejection_reason`, and nothing else changes (no fill, no position update, no cash movement). This mostly never triggers in practice, since the Risk Engine's own position sizing (`docs/risk-engine.md` §6) already constrains the approved quantity to what cash allows — it exists as real, tested defense-in-depth (`test_execute_signal_with_absurd_quantity_is_rejected_for_insufficient_cash`), not dead code.

## 8. Position accounting (Step 9/10/11)

**Opening / adding (BUY, `PaperTradingEngine.apply_buy_fill`)**: no existing position → `quantity = filled quantity`, `avg_entry_price = fill_price`. An existing position → both are recomputed as a weighted average:

```
avg_entry_price = (existing_qty × existing_avg + add_qty × fill_price) / (existing_qty + add_qty)
```

A BUY never realizes P/L (`realized_pnl_delta` is always `0`).

**Reducing / closing (SELL, `PaperTradingEngine.apply_sell_fill`)**:

```
realized_pnl = (fill_price − avg_entry_price) × quantity − fee
```

The average entry price is *not* recomputed on a sell — only a BUY ever changes it. A partial close (`quantity < position.quantity`) leaves the position `OPEN` with the same average entry; quantity reaching exactly zero marks it `CLOSED` and stamps `closed_at`. Both partial and full closes are exercised directly against the pure engine (`tests/test_paper_engine.py`), independent of whatever quantities the API currently exposes (§12 only offers a full close).

**No short selling (Step 11)**: `apply_sell_fill` raises `InsufficientPositionError` — never silently produces a negative quantity — when there is no position, or the requested quantity exceeds what's held. In the current architecture this can't actually be reached through the signal-driven path: the Risk Engine (Phase 6) only ever approves `BUY` signals, so every `POST /paper/execute/{signal_id}` order is a BUY. The only path that ever calls `apply_sell_fill` today is `POST /paper/positions/{symbol}/close` (§12), a direct action that always sells exactly the position's own current quantity — so the "no position" error path is real, tested code (`test_close_position_with_no_open_position_raises_not_found` at the service layer, surfaced as `404` at the API layer since there's nothing to act on), not a speculative guard against a case that structurally cannot occur yet.

## 9. P&L formulas (Step 12)

```
unrealized_pnl = (current_price − avg_entry_price) × quantity      # no fee term
```

No fee term, deliberately — an open position hasn't incurred an exit fee (that only happens at the moment of an actual sale, §7). `current_price` comes from the same live `MarketDataService.get_quote()` call used everywhere else. Realized P/L (§8) does include the fee; this asymmetry is intentional, not an oversight.

## 10. Portfolio state (Step 13/14) — one authoritative computation

`app/services/paper_trading/portfolio.py::compute_portfolio_state()` is the single place that walks every open position, fetches each one's current price, and derives the full picture — used by *both* the paper-trading API and (via `risk_engine.PortfolioStateProvider`, §11) the Risk Engine, so there is never a second, independently-drifting implementation of "what does the portfolio look like right now":

```
market_value = Σ (position.quantity × current_price)   over open positions
equity       = cash + market_value
```

Never `starting_equity + arbitrary_pnl` — equity is always reconciled from the actual `cash` column plus the actual current market value of actual open positions (verified directly: `test_portfolio_equity_reconciles_with_cash_plus_market_value`). Also derived: `realized_pnl_total` (sum of every `paper_fills.realized_pnl`), `total_pnl` (`realized_pnl_total + unrealized_pnl`), `open_position_count`.

## 11. Drawdown (Step 15)

```
drawdown_pct = (peak_equity − equity) / peak_equity × 100
```

`paper_accounts.peak_equity` is the persisted high-water mark, ratcheted upward inside `compute_portfolio_state()` itself — on *every* computation (a risk evaluation, a portfolio read, not only a trade), since price movement on an open position can set a new equity high without any order ever being placed. `peak_equity > 0` is a database `CHECK` constraint; `PortfolioStateProvider`'s downstream check (`docs/risk-engine.md` §5) additionally fails closed if it ever saw a non-positive value, so a division by zero is never reachable from either layer.

## 12. Daily P&L (Step 16)

Trading day = UTC calendar day (`datetime.now(UTC)` truncated to midnight) — no other convention is specified anywhere in this architecture, so Phase 6's own precedent (UTC internally) carries forward unchanged. `daily_pnl` sums **realized** P/L only, from `paper_fills` rows whose `realized_pnl` is not null and whose `timestamp` falls within today's UTC boundary — unrealized P/L is excluded, matching the semantics `docs/risk-engine.md`'s daily-loss check already committed to in Phase 6 (`realized_pl_today`). Fees are already netted into each fill's `realized_pnl` (§8), so they're automatically included in the daily sum without a separate fee term.

## 13. Risk Engine integration (Step 17)

The Phase 6 `PortfolioStateProvider` placeholder — a clean, position-free default, since no paper trading existed yet — is gone. `app/services/risk_engine/portfolio_state.py` now delegates entirely to `compute_portfolio_state()` (§10) and maps the fields the check pipeline needs into the *same*, *unchanged* `risk_engine.types.PortfolioSnapshot` shape Phase 6 already defined. **No risk rule was rewritten** — `docs/risk-engine.md`'s 11-check pipeline, position-sizing formula, and every threshold are exactly as Phase 6 built them; only the data source changed, which is precisely the seam Phase 6 documented in advance. Concretely, checks that were structurally always-passing in Phase 6 are now real:

| Check | Phase 6 | Phase 7 |
|---|---|---|
| `max_concurrent_positions` | always 0 open | real open `PaperPosition` count |
| `portfolio_exposure` | always 0 | real Σ market value |
| `daily_loss_limit` | always 0 | real sum of today's realized `paper_fills` |
| `max_drawdown` | equity ≡ peak, always 0% | real ratcheted `peak_equity` vs. current equity |
| `loss_cooldown` | never any prior loss | real `MAX(timestamp)` over losing `paper_fills` |

Verified directly (`tests/test_paper_risk_regression.py`): open enough positions and a new candidate is rejected on `max_concurrent_positions`; shrink `max_portfolio_exposure_pct` and a candidate is rejected on `portfolio_exposure`; a realized loss today rejects on `daily_loss_limit`; a large realized loss rejects on `max_drawdown`; a recent loss rejects on `loss_cooldown`.

## 14. Execution boundary (Step 18)

```
ExecutionAdapter (Protocol, app/services/paper_trading/execution.py)
        │
        ▼
PaperExecutionAdapter          — the only implementation in this codebase
```

`PaperTradingService` depends only on the `ExecutionAdapter` protocol, never on `PaperExecutionAdapter` directly — a future `RealBrokerAdapter` (not built, not stubbed, not planned for this phase) would be a second implementation of the same interface, not a rewrite of the service, mirroring `docs/architecture.md`'s `BrokerAdapter` principle from [ADR-007](decisions/ADR-007-paper-trading-first.md).

## 15. Idempotency (Step 19)

`paper_orders.signal_id` is `UNIQUE` at the database level — the authoritative idempotency key. `PaperTradingService.execute_signal()` checks for an existing order for the signal *before* doing any other work; if one exists, it raises a `409 conflict` (never a silent no-op, never a duplicate), the exact precedent `RiskService` already set in Phase 6 for re-evaluating an already-decided signal. Verified with a literal same-signal-twice test at the service layer, the API layer, and an idempotency-focused test asserting exactly one order and exactly one fill exist afterward (`tests/test_paper_service.py::test_execute_signal_twice_raises_conflict_and_creates_only_one_order`).

## 16. Transactional integrity (Step 20)

`execute_signal` and `close_position` both follow the same shape: compute everything (fetch state, call the execution adapter, run the pure engine) *before* writing anything, then stage every write — order, fill, position insert/update, account cash — on the SQLAlchemy session and commit exactly once. A `FILLED` order can never exist without its fill, its position update, and its cash update also having landed, because they're all part of the same uncommitted unit of work; an exception anywhere before that single `commit()` leaves nothing durable (`tests/test_paper_transactions.py` proves this directly, by patching the engine to raise mid-flow and confirming a rollback leaves zero trace — no order, no fill, no cash change). The one exception is the insufficient-cash path (§7), which is itself a complete, honest transaction — a `REJECTED` order with a reason, no fill, no position change, no cash change — not a partial success.

**Concurrency (Phase 9.5 hardening)**: the sequential shape above was correct but not race-safe — two *simultaneous* requests could each read the same pre-mutation state before either committed. Three specific races were reproduced with genuinely concurrent sessions (`tests/test_paper_concurrency.py`) and closed:

1. **Duplicate execution of the same signal** — the `paper_orders.signal_id` UNIQUE constraint always prevented the duplicate *row*, but the losing request surfaced a raw `IntegrityError` (a 500) instead of the clean `409` a sequential second call gets. The `flush()` now translates that constraint violation into the same `ConflictError`.
2. **Double-close of the same position** — both closes could read the same OPEN position and both sell it (share conservation violated). `_get_open_position` now takes `SELECT ... FOR UPDATE` (scoped `of=PaperPosition`, since the `asset` relationship's outer join can't be locked) on both write paths, and `paper_accounts` is read with `get_account_for_update` (`FOR UPDATE` on the one shared cash row) so concurrent trades can't lost-update each other's cash deltas.
3. **Lock released mid-flight** — `ExecutionAdapter.fill()` goes through `MarketDataService.get_quote()`, which *commits* freshly-ingested market data; a commit ends the transaction and silently releases every row lock. Both write paths therefore call `fill()` **before** acquiring any lock; `close_position` uses a provisional unlocked read to size the fill, then re-reads the position under the lock (with `populate_existing()`, since SQLAlchemy's identity map would otherwise return the stale pre-lock object) and fails with a clean `409 retry` if the quantity changed in between (e.g. a concurrent BUY added to the position, invalidating the already-computed fee). Lock ordering is position-then-account in both paths, preventing a lock-ordering deadlock between them.

Not a distributed lock, not Redis, not a queue — plain Postgres row locks, which are sufficient for a single database instance and were already available.

## 17. Error handling (Step 21)

| Failure | Behavior |
|---|---|
| Signal doesn't exist | `404 not_found` |
| Signal isn't `RISK_APPROVED` | `409 conflict` (identifies the actual status) |
| Signal already has a paper order | `409 conflict` (idempotency, §15) |
| `RISK_APPROVED` signal with no backing `RiskEvaluation` | `500` (a data-integrity violation that should never happen — `RiskService` always writes both in one transaction) |
| Approved quantity is non-positive | `422 validation_error` (defense-in-depth; the Risk Engine's own invariants should prevent this) |
| Insufficient cash | Order written as `REJECTED` with `rejection_reason`, `200` response (§7/16 — a rejection is a successful, honest outcome, not a server error, mirroring how a `RiskEvaluation` REJECTED decision is `200` in Phase 6) |
| No open position to close | `404 not_found` |
| Selling more than held | `409 conflict` (`InsufficientPositionError`, §8) |
| Missing/unreachable market price | Propagates as whatever `MarketDataService` raises (`ProviderError`, `503`) — consistent with every other caller of that service |

Never silently continues after a failed financial-state update — every path above either fully succeeds (all writes committed together) or fully fails (nothing committed).

## 18. API (Step 22)

All under `/api/v1/paper`, full detail in `docs/api.md`:

| Endpoint | Purpose |
|---|---|
| `GET /paper/portfolio` | The full portfolio state (§10) — equity, cash, P/L, drawdown, exposure. |
| `GET /paper/positions` | List positions. Query: `status` (`OPEN`/`CLOSED`). |
| `GET /paper/orders` | List orders. Query: `symbol`, `status`, `limit`. |
| `GET /paper/orders/{id}` | Single order by UUID. |
| `GET /paper/fills` | List fills. Query: `symbol`, `order_id`, `limit`. |
| `POST /paper/execute/{signal_id}` | Executes a `RISK_APPROVED` signal as a simulated BUY order. `404`/`409` per §17. |
| `POST /paper/positions/{symbol}/close` | Closes the entire open position for `symbol` as a simulated SELL order. `404` if none is open. |

## 19. Language (Step 23)

"Paper Trade", "Simulated Order", "Simulated Fill" — never "real trade," "real order," or anything implying live execution. Verified directly by `test_paper_order_response_never_uses_certainty_language`.

## 20. Frontend

- **Paper Trading Center** (`/paper`, `PaperTradingCenter.tsx`) — Account (starting equity, cash, equity, total P/L, daily P/L, drawdown), Positions (symbol, quantity, average entry, current price, market value, unrealized P/L, status), Orders (id, symbol, side, quantity, requested/fill price, fee, status, timestamp), Recent Fills. All real data — no fabricated rows; an account with no trades yet shows a professional empty state ("No paper positions yet"), never a fake sample.
- **Signal Center integration** — the lifecycle stepper (Phase 6: `Candidate → Risk Review → Risk Approved/Rejected`) extends one more step for an approved signal: `→ Paper Execution → Filled → Position Open`, with an "Execute Paper Order" action next to the existing "Run Risk Review" one. A failed execution (e.g. insufficient cash) shows `Risk Approved → Execution Failed` with the reason — never presented as a real trade having occurred.
- **Dashboard** — the portfolio panel now shows real equity/daily P/L/total P/L/exposure/open positions from `GET /paper/portfolio`, replacing the earlier mock placeholder.

## 21. Testing (Step 29/30/31/32/33/34)

- **`tests/test_paper_pricing.py`** — fee, weighted-average entry (new/adding), realized P/L (profit/loss/breakeven, fee always reduces it), unrealized P/L (no fee term) — pure functions.
- **`tests/test_paper_engine.py`** — `apply_buy_fill`/`apply_sell_fill`: open, add (weighted average), partial close, full close, a sequence of independent partial closes, every no-shorting rejection case (no position, zero-quantity position, exceeding held quantity, exactly-at-held-quantity), determinism — pure functions.
- **`tests/test_paper_service.py`** — full order→fill→position→cash flow with before/after deltas (never a hardcoded absolute balance, since the account is a shared singleton across the whole suite), fee-matches-configured-rate, weighted-average verified against each fill's own recorded price, idempotency (exactly one order/fill for a repeated signal), every rejection case (`CANDIDATE`, `RISK_REJECTED`, unknown signal, missing `RiskEvaluation`, absurd-quantity insufficient-cash), full close with realized P/L verified against the position's actual pre-close average entry (not assumed to equal this test's own single fill, since other tests share the same symbols).
- **`tests/test_paper_data_consistency.py`** — proves the database `CHECK` constraints and partial-unique index actually reject what they're meant to (negative cash, negative position quantity, over-fill, a second open position for the same asset), plus a filled-order-always-has-a-fill and an equity-reconciles invariant.
- **`tests/test_paper_transactions.py`** — a failure mid-`execute_signal`/mid-`close_position` (patched to raise after the order is staged but before commit) leaves zero trace after rollback — no order, no fill, no cash change.
- **`tests/test_paper_risk_regression.py`** — the five Phase 6 checks now reacting to real state (§13), each isolating its own threshold via the same capture-and-restore discipline `test_risk_service.py` established for the shared active policy, plus a matching restore for the shared `paper_accounts.cash`/synthetic test fills (a leftover synthetic loss would otherwise permanently poison the cooldown check for every later run — documented directly in that file after being caught mid-development).
- **`tests/test_api_paper.py`** — all seven endpoints, `200`/`404`/`409`/`422`, and the certainty-language check.
- **Frontend** — Paper Trading Center rendering (account/positions/orders/fills, loading/empty/error states), the Signal Center's paper-execution step, and the dashboard's real portfolio panel.

## 22. Limitations

- No slippage model (§5) — every fill is exactly the current market price.
- `MARKET` orders only (§4) — no limit/stop orders.
- No short selling (§8) — long-only, matching the Risk Engine's own long-only scope.
- Closing a position is always a full close via the API (§18); partial closes are real, tested engine behavior (§8) not yet exposed as an endpoint.
- One simulated account, no per-user portfolios — matches the single-implicit-user posture of every prior phase.
- No scheduler — execution is on-demand (`POST /paper/execute/{signal_id}`), the same on-demand posture Phase 4/5/6 already established.
