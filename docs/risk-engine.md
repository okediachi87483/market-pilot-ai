# MarketPilot AI — Risk Engine

Phase 6. The hard safety boundary between the Signal Engine and (Phase 7's) paper trading. A `Signal` in status `CANDIDATE` can never become a paper trade without passing through here — the Risk Engine is the only component allowed to move a signal to `RISK_APPROVED` or `RISK_REJECTED`, and it does so deterministically. **No AI, no broker access, no order placement, no real money anywhere in this layer.**

## 1. Architecture

```
SIGNAL ENGINE (Phase 5)
        │
        ▼
Signal (status: CANDIDATE)
        │
        ▼
RiskEvaluationRequest          — app/services/signal_engine/risk_boundary.py
        │
        ▼
RiskEngine.evaluate()          — app/services/risk_engine/engine.py
   ├─ sizing.py                — stop-loss, take-profit, position size
   └─ checks.py                — the 11-check pipeline
        │
        ▼
RiskEvaluationOutcome (APPROVED | REJECTED, full check trail)
        │
        ▼
RiskService                    — app/services/risk_engine/service.py
   ├─ persists RiskEvaluation (Postgres, the audit trail)
   └─ transitions Signal.status -> RISK_APPROVED / RISK_REJECTED
        │
        ▼
API (docs/api.md) → Risk Center UI
        │
        ▼
(future) Phase 7: paper trading consumes RISK_APPROVED signals   [not built yet]
```

`app/services/risk_engine/` is independent of FastAPI and the database (Step 2), mirroring `signal_engine`'s split: `types.py`, `defaults.py`, `sizing.py`, `checks.py`, and `engine.py` take plain dataclasses in and return a plain dataclass out — no I/O, no randomness. `RiskService` and `portfolio_state.py` are the only pieces that know about the database, `MarketDataService`, or ORM models.

## 2. Risk policy (Step 3)

One configurable policy, versioned and stored in `risk_policies` (Step 4). Every value below is a documented, conservative default for a fresh paper-trading account — see `app/services/risk_engine/defaults.py` for the single authoritative source:

| Field | Default | Rationale |
|---|---|---|
| `max_position_size_pct` | 5.00% | A single position's cost basis can't exceed 5% of equity — no one trade can meaningfully damage the account. |
| `max_portfolio_exposure_pct` | 50.00% | Total open exposure can't exceed 50% of equity — at least half the account stays uncommitted. |
| `max_daily_loss_pct` | 3.00% | No new positions once today's realized P/L is worse than -3% of equity. |
| `max_drawdown_pct` | 15.00% | No new positions once equity has fallen >15% from its high-water mark. |
| `stop_loss_pct` | 2.00% | Every approved BUY gets a stop 2% below entry — engine-computed, never taken from the signal. |
| `take_profit_pct` | 4.00% | Every approved BUY gets a target 4% above entry — a 2:1 reward:risk ratio against the default stop. |
| `risk_per_trade_pct` | 1.00% | How much equity the account is willing to lose if a single trade's stop is hit — the standard "never risk more than 1-2%" baseline. Drives position sizing (§6); not one of Step 3's eight listed fields, added because Step 7 explicitly needs a risk-per-trade input distinct from the hard `max_position_size_pct` ceiling. |
| `max_concurrent_positions` | 5 | Hard cap on simultaneously open positions. |
| `cooldown_after_loss_minutes` | 60 | One hour of no new entries after a losing trade closes. |

**Versioning (Step 4/24)**: `RiskPolicy` rows are immutable once created. `PUT /risk/rules` never `UPDATE`s an existing row's numbers — it inserts a new row with `version = current.version + 1`, deactivates the previous row (`is_active = false`), and activates the new one, inside one transaction (a partial unique index on `is_active` enforces exactly one active policy at all times, even under a race). This is what makes `RiskEvaluation.policy_version` (§10) a permanent, meaningful pointer to the exact numbers a past decision used, without a separate snapshot column. A fresh database always has exactly one active policy, seeded by the initial migration from `defaults.py` — `RiskService.get_active_policy()` never has to handle "no policy configured."

## 3. Database (Step 4/24)

**`risk_policies`**: `id`, `name`, `version`, `enabled` (pause the whole engine without deleting config), `is_active` (which version is current), the nine fields above, `created_at`/`updated_at`. `CHECK` constraints bound every percentage `(0, 100]` (`stop_loss_pct` strictly `< 100`, `take_profit_pct` up to 1000), `max_concurrent_positions >= 1`, `cooldown_after_loss_minutes >= 0`. `UNIQUE(name, version)`; a partial unique index on `is_active WHERE is_active` (Step 4's "clear concept of the currently active policy").

**`risk_evaluations`**: `id`, `signal_id` (FK), `policy_id` + `policy_version`, `decision` (`APPROVED`/`REJECTED`), `reasons` (JSONB list — every failed, non-skipped check's detail), `checks` (JSONB list of all 11 `{name, passed, detail, skipped}` rows), `calculated_position_size`/`entry_price`/`stop_loss_price`/`take_profit_price`/`position_value` (all `NUMERIC`, nullable — populated whenever computed, even for a rejected candidate, so a reviewer can see what *would have* been sized), `portfolio_snapshot` (JSONB — the exact `PortfolioSnapshot` used, §5), `evaluated_at`, `created_at`. Never updated after insert — append-only, like `audit_logs`. Financial columns use the same `NUMERIC(20,8)`/`NUMERIC(28,10)` precision as `market_data`/`signals` (docs/database.md §1) — never floats.

## 4. Portfolio state — the Phase 7 seam

There is no `positions`/`trades`/`orders` table yet — Phase 7 builds them. Steps 12-16 all describe checks against "authoritative backend state" (exposure, concurrent positions, daily P/L, drawdown, last losing trade). Until real trading activity exists, the only honest authoritative answer for all of those is: **a clean, fully-funded, position-free portfolio.** This isn't a faked placeholder — it *is* the real state of an account that has never traded, computed the same way it always will be: equity/cash start from a configured starting balance (`RISK_STARTING_EQUITY`, `.env.example`, default $100,000), and every other field derives from position/trade history that is, today, genuinely empty:

| Field | Current value | Why |
|---|---|---|
| `equity`, `cash` | starting balance | no trades have changed it |
| `high_water_mark` | = equity | no performance history exists yet |
| `open_position_count` | 0 | no positions table |
| `open_position_value` | 0 | same |
| `realized_pl_today` | 0 | no trades table |
| `last_losing_trade_at` | `null` | same |

`PortfolioStateProvider` (`app/services/risk_engine/portfolio_state.py`) is the seam: `RiskService` depends on its `get_snapshot()` method, not on how it's computed. Phase 7 swaps the implementation for one that aggregates real `positions`/`trades` rows — no caller changes. Every check in §5 that reads these fields (daily loss, drawdown, concurrent positions, cooldown) is fully real, tested logic (see §11) that today always evaluates against this clean state — it isn't a no-op stub, it's a correct answer to a currently-trivial question.

## 5. The check pipeline (Step 6)

Eleven checks, always evaluated and reported in this exact order (`app/services/risk_engine/checks.py`):

| # | Check | Hard gate? | Meaning |
|---|---|---|---|
| 1 | `signal_validity` | yes | Only a `BUY` signal is an actionable long entry in this phase (Step 9: no short-position logic). `SELL`/`HOLD` fail here — a `SELL` is an exit/reduce suggestion, but there's no position to exit yet (Phase 7). |
| 2 | `signal_status` | no | Always reported `passed` — `RiskService` already verified the signal was `CANDIDATE` before the engine ever runs (Step 17, §9). Kept as an explicit, named row in the audit trail rather than silently omitted. |
| 3 | `risk_policy_enabled` | yes | The active policy's `enabled` flag — a pause switch for the whole engine. |
| 4 | `daily_loss_limit` | no | `realized_pl_today > -(equity * max_daily_loss_pct / 100)`. |
| 5 | `max_drawdown` | no | `(high_water_mark - equity) / high_water_mark < max_drawdown_pct / 100`. `high_water_mark <= 0` fails closed rather than divide by zero (Step 15). |
| 6 | `max_concurrent_positions` | no | `open_position_count + 1 <= max_concurrent_positions`. |
| 7 | `portfolio_exposure` | no | `open_position_value + proposed_position_value <= equity * max_portfolio_exposure_pct / 100`. |
| 8 | `position_size_limit` | no | computed quantity `> 0` and its notional value `<= equity * max_position_size_pct / 100`. |
| 9 | `stop_loss_validity` | no | `0 < stop_loss_price < entry_price`. |
| 10 | `take_profit_validity` | no | `take_profit_price > entry_price > 0`. |
| 11 | `loss_cooldown` | no | no losing trade on record, or enough time has elapsed since the last one. |

**Precedence and skip semantics**: checks 1 and 3 are the only hard gates — if either fails, every later check is marked `skipped` (reported, not silently dropped) rather than evaluated, because nothing downstream is meaningful without an actionable signal or an enabled policy. Every other check (4-11) **always runs independently once gating passes**, so a rejection shows the complete risk picture in one response rather than one failure at a time across repeated calls (Step 6's explicit preference). `decision = APPROVED` iff every check passed; `reasons` collects the detail of every failed, non-skipped check — guaranteeing a rejection always carries at least one concrete reason (Step 26).

**Computation order note**: stop-loss, take-profit, and position size are computed once, up front (pure arithmetic from the policy's percentages and the current entry price), before the check pipeline runs — checks 7/8 use the resulting quantity, and checks 9/10 independently validate the same computed prices are sane. Well-formed policy values (enforced by §7's API bounds) make 9/10 always pass in practice; they exist as defense-in-depth so a corrupted policy row can never silently produce an approved trade with an invalid stop.

## 6. Position sizing (Step 7)

```
risk_budget          = equity × risk_per_trade_pct / 100
risk_per_unit         = entry_price − stop_loss_price
raw_quantity          = risk_budget / risk_per_unit

max_qty_by_position   = (equity × max_position_size_pct / 100) / entry_price
max_qty_by_exposure   = (equity × max_portfolio_exposure_pct / 100 − open_position_value) / entry_price
max_qty_by_cash       = cash / entry_price

quantity = min(raw_quantity, max_qty_by_position, max_qty_by_exposure, max_qty_by_cash)
```

The tightest of the four constraints wins; the result is **rounded down**, never up (`app/services/risk_engine/sizing.py`), so a computed position never exceeds what the constraints actually allow. Returns `Decimal("0")` — never raises, never divides by zero (Step 8) — for any input that makes sizing meaningless: non-positive entry/stop price, a non-positive stop distance, or non-positive equity.

**Worked example** (defaults, $100,000 equity, entry $100): `risk_budget = 100000 × 1% = 1000`; stop at $98 (2% below entry) gives `risk_per_unit = 2`; `raw_quantity = 500`. But `max_qty_by_position = (100000 × 5%) / 100 = 50` — the hard position-size cap binds first, so the approved quantity is 50 shares ($5,000 notional), not 500. This is deliberate: the risk-based formula answers "how much *could* I risk," the hard caps answer "how much am I *allowed* to hold" — the second always wins when tighter.

## 7. Stop-loss and take-profit (Step 9/10)

Long-only. `stop_loss_price = entry_price × (1 − stop_loss_pct / 100)`; `take_profit_price = entry_price × (1 + take_profit_pct / 100)`. Both are always **engine-computed from the active policy** — never read from the signal's `supporting_features` or any future AI suggestion, matching the same non-negotiable boundary `docs/ai-architecture.md` describes for the eventual AI layer. `entry_price` itself comes from `MarketDataService.get_quote()` — the same authoritative, persisted market data Phase 3/4/5 already use, not a value carried on the signal.

## 8. Exposure, concurrent positions, daily loss, drawdown, cooldown (Steps 12-16)

Each is a real, independently-tested computation (§11) against `PortfolioSnapshot` (§4) and the active policy — see the check table in §5 for the exact formulas. **Given §4's current portfolio state, checks 4/6/7/11 structurally always pass today** (zero realized P/L, zero positions, no loss history) — this is an honest consequence of Phase 7 not existing yet, not a shortcut in the logic itself: every one of these checks is exercised with deliberately-constructed non-trivial `PortfolioSnapshot` values in the unit test suite (boundary conditions, over-limit, exactly-at-limit) and will engage identically on real data the moment Phase 7 populates the underlying tables.

## 9. Signal lifecycle and the one controlled transition (Step 17)

The Signal Engine (Phase 5) only ever writes `CANDIDATE`. The Risk Engine is the only component that may write `RISK_APPROVED` or `RISK_REJECTED`, and it only does so once per signal:

```
CANDIDATE ──POST /risk/evaluate/{id}──▶ RISK_APPROVED
CANDIDATE ──POST /risk/evaluate/{id}──▶ RISK_REJECTED
```

`RiskService.evaluate_signal()` fetches the signal and, if its status **isn't** `CANDIDATE` (already `RISK_APPROVED`, `RISK_REJECTED`, `EXPIRED`, or `SUPERSEDED`), raises a `409 conflict` **before** the engine ever runs or a `RiskEvaluation` row is written — re-evaluation (including `RISK_REJECTED → RISK_APPROVED`) is refused outright, not silently re-run. No re-evaluation mechanism is implemented in this phase. Only when the precondition holds does the pipeline run and the signal's status get written, in the same transaction as the `RiskEvaluation` insert.

## 10. Auditability (Step 18)

Every `RiskEvaluation` row answers "why did the Risk Engine approve or reject this trade?" without re-running anything: `policy_id` + `policy_version` pin the exact, immutable policy row used (§2); `checks` is the complete 11-row trail (passed *and* failed, in order); `reasons` is the human-readable summary of what failed; `calculated_position_size`/`entry_price`/`stop_loss_price`/`take_profit_price`/`position_value` are preserved regardless of decision; `portfolio_snapshot` is the exact state read at evaluation time; `evaluated_at` places it in time. Structured logs (`RiskService.evaluate_signal`) additionally record `signal_id`, `symbol`, `policy_version`, `decision`, the list of failed check names, and evaluation duration — never any secret or credential.

## 11. API (Step 19/20)

All under `/api/v1/risk`, full detail in `docs/api.md`:

| Endpoint | Purpose |
|---|---|
| `GET /risk` | Portfolio state + active policy limits combined — the Risk Center's "Portfolio Risk" read model. |
| `GET /risk/rules` | The active policy. |
| `PUT /risk/rules` | Replaces the active policy (creates a new version, §2). All ten fields required — no partial update, matching `docs/api.md`'s existing `PUT /risk/rules` contract for the same reason: a partial merge of safety-critical values is ambiguous. Every field is bounds-checked by the Pydantic schema *and* the database `CHECK` constraints (Step 20: negative percentages, a zero stop-loss, a zero position limit, an out-of-range drawdown/cooldown are all `422`, never reaching the database). |
| `POST /risk/evaluate/{signal_id}` | Runs the pipeline once for a `CANDIDATE` signal; `404` unknown signal, `409` signal not `CANDIDATE`. Never places, fills, or simulates a trade. |
| `GET /risk/evaluations` | List, filterable by `signal_id`, `decision`, `symbol`. |
| `GET /risk/evaluations/{id}` | Single evaluation by id — added beyond the phase's literal endpoint list for the same reason Phase 3/5 each added one or two: a natural single-item GET next to an existing list endpoint (consistent with `GET /signals/{id}`). |

## 12. Frontend

- **Risk Center** (`/risk`, `RiskCenter.tsx`) — three panels: **Portfolio Risk** (equity, exposure bar, drawdown bar, daily P/L vs. limit, concurrent positions), **Risk Policy** (all ten configured values, read-only in this phase — editing is API-only via `PUT /risk/rules`; no edit form was built, since Step 21 only specifies what the Risk Center *shows*), and **Recent Decisions** (the latest evaluations, decision + symbol + primary reason/size + timestamp). Deliberately restrained — bar meters and plain numbers, not a "danger" screen: the design goal is **control, discipline, visibility**, not alarm (Step 21).
- **Signal Center integration** (`SignalCard.tsx`/`SignalCenter.tsx`, Step 22) — a signal now visibly progresses `Candidate → Risk Review → Risk Approved`/`Risk Rejected` (`LifecycleStepper`). A `CANDIDATE` BUY/SELL/HOLD signal gets a "Run Risk Review" button (`POST /risk/evaluate/{id}`); the result renders inline — approved shows position size/entry/stop/take-profit/policy version with an explicit "no paper trade has been placed" note (Step 22: never present an approval as an executed trade); rejected shows every reason and the list of failed check names. A signal fetched via dedup that was already risk-evaluated (§9) fetches its existing decision instead of offering a stale button.
- **Dashboard `RiskPreview`** — updated from the Phase 1-era hardcoded "62% / 80%" mock bars to real exposure/drawdown from `GET /risk`, mirroring the same real-data treatment Phase 5 gave `SignalPreview`.

## 13. Language (Step 23)

"Risk Approved", "Trade Candidate", "Paper Trade Eligible" — never "Guaranteed Trade", "Safe Trade", "Winning Trade", or "Guaranteed Profit." Percentages that appear in check details (e.g. "within the 3.00% daily loss limit") are real, configured policy thresholds — not a fabricated confidence score; that distinction (Phase 5's "no fabricated probability" rule) is unaffected. Verified directly by `test_risk_response_never_uses_certainty_language` (API) and the frontend's no-"guaranteed" assertions.

## 14. Why AI is excluded (Step 32)

Every check in §5 is a fixed, documented, arithmetic condition — zero LLM calls, zero network calls beyond reading Postgres/market data, zero randomness. The future pipeline order (`docs/ai-architecture.md`) places AI *before* this layer, not inside it:

```
Signal → AI Analyst (Phase 8, not built) → Risk Engine (this phase) → Paper Trading (Phase 7)
```

An AI-suggested action will still have to pass every check in §5 unchanged — the Risk Engine has no code path that reads an AI-generated number as a trade parameter, the same boundary `docs/ai-architecture.md` §4 already documents for the eventual `ai_analyses` table.

## 15. Testing (Step 25/26/27/28)

- **`tests/test_risk_sizing.py`** — stop-loss/take-profit formulas, position sizing against each of the four constraints independently and combined, zero/negative/inverted-stop-distance handling, non-positive equity, rounding-down, determinism.
- **`tests/test_risk_checks.py`** — one or more tests per check, including exact-boundary/just-below/just-above cases for every percentage-based check (daily loss, drawdown, exposure, concurrent positions, cooldown), the hard-gate skip cascade for checks 1 and 3, and a test that multiple independent failures are all reported together (not just the first).
- **`tests/test_risk_engine.py`** — full outcome shape plus the ten Step 26 invariants: never approves an invalid/zero position size; an approved BUY always has a valid stop-loss and take-profit; an approved trade never exceeds max exposure or max position size; a rejection always has ≥1 reason; policy version is preserved on both outcomes; identical input produces identical output; decision is always exactly `APPROVED` or `REJECTED`.
- **`tests/test_risk_service.py`** — DB-integration: approve/reject/transition, re-evaluation refused with `409` and the signal left untouched, full audit-trail persistence, filtering, and policy versioning (update creates a new version, deactivates the old one, preserves history) — see the module's own docstring for how this test restores the original active policy afterward, since (unlike Phase 5's per-symbol signal cooldown) the active policy is a single process-wide singleton every other test also depends on.
- **`tests/test_api_risk.py`** — all five endpoints, parametrized `422` cases for every unsafe `PUT /risk/rules` field (negative/zero/out-of-range), `404`/`409` handling, and the certainty-language check.
- **Frontend** (`riskCenter.test.tsx`, `riskPreview.test.tsx`, additions to `signalCenter.test.tsx`) — loading/error/empty states, the approved/rejected result rendering, the "Run Risk Review" flow, and fetching an already-decided signal's existing evaluation instead of re-offering the button.

## 16. Limitations

- Portfolio state is a clean simulated default until Phase 7 (§4/§8) — every check is real and tested, but four of the eleven currently always pass given no trading history exists yet.
- One policy at a time, no per-user configuration (matches the single-implicit-user posture of every prior phase).
- No re-evaluation mechanism — a rejected signal stays rejected; a corrected signal must come from a fresh `POST /signals/evaluate/{symbol}` cycle, not a retry of the same signal id.
- The Risk Center's policy panel is read-only; changing limits is API-only (`PUT /risk/rules`) in this phase.
- No scheduler — risk evaluation is on-demand (`POST /risk/evaluate/{signal_id}`), matching Phase 4/5's same on-demand posture.
