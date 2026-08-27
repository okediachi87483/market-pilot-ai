# MarketPilot AI — Security Architecture

MarketPilot handles no real money and no real brokerage credentials in this architecture, but it does handle user data, AI provider credentials, and a system whose outputs (signals, AI analysis, risk decisions) must be trustworthy. Security is treated as a first-class requirement from Phase 1, not deferred.

## 1. Secrets management

- No secret is ever committed. `.env.example` documents every required variable name with a placeholder or dummy value, never a real one; `.env` is git-ignored.
- Local development: environment variables loaded from `.env` via `docker-compose.yml`'s `env_file`.
- Production: a managed secret store (AWS Secrets Manager or SSM Parameter Store, provisioned via Terraform — not applied without explicit approval per the workflow rules) injects secrets as environment variables at container start; secrets are never baked into a Docker image layer.
- Required secrets, minimum set: `DATABASE_URL`, `REDIS_URL`, `JWT_SIGNING_KEY` (once auth is fully implemented). None have defaults in code — a missing required secret fails startup loudly, not silently with an insecure fallback.
- **Deviation, Phase 8**: `AI_PROVIDER_API_KEY` is treated differently, deliberately — it is *optional*, not required. An empty key does not fail startup; `Settings.ai_configured` is `False`, `GET /ai/status` reports `configured: false`, and every AI Analyst endpoint responds `503` rather than crashing the process. This matches Step 4's explicit requirement that the platform run fully (market data, signals, risk, paper trading) with no AI provider configured at all — see [ai-analyst.md](ai-analyst.md) §4.

## 2. Environment configuration

`packages/shared/config.py` is the single settings loader (Pydantic `BaseSettings`), read once at process start. No package reads `os.environ` directly outside of `shared` — this keeps every configurable value documented in one typed place and makes "what does this deployment need to run" answerable by reading one file.

## 3. Authentication strategy

MVP ships single-user, with the auth *architecture* fully scaffolded but permissive locally: a `users` table exists, `password_hash` is a real bcrypt/argon2 hash column from day one (never plaintext, even though only one user exists), and every non-`/health` endpoint is wired through an auth dependency (`apps/api/app/deps.py`) that resolves the current user — even before a real login flow exists, so tightening auth later is a matter of implementing the dependency's token verification, not retrofitting it through every router. JWT bearer tokens are the intended mechanism (short-lived access token + refresh token), issued after credential verification.

## 4. Authorization strategy

Resource ownership, not roles, is the MVP's authorization model — every user-scoped resource (`watchlists`, `portfolios`, `positions`, `orders`, `trades`, `alerts`, `risk_rules`, `strategies`, `backtests`) carries or is reachable from a `user_id`, and every read/write in [api.md](api.md) is scoped to `WHERE user_id = current_user.id` (or via portfolio ownership) at the query layer, not filtered after the fact in application code. A role system (admin/analyst/viewer) is not built in the MVP — noted as a clean extension point on the same ownership model when multi-user or team access becomes a requirement.

## 5. API security

- All endpoints except `/health` require authentication (§3).
- Input validation is Pydantic-schema-enforced at the API boundary — no handler trusts a request body beyond what its schema declares (see [api.md](api.md) §1).
- CORS is restricted to the deployed frontend origin(s); wildcard origins are never used outside local development.
- `POST /trades` requires `Idempotency-Key` — beyond correctness ([database.md](database.md) §1), this also mitigates duplicate-submission abuse from retried/replayed requests.

## 6. Rate limiting

Redis-backed token bucket, keyed per user (authenticated) or per IP (unauthenticated `/health`). Two tiers: a general API tier (generous, protects against accidental client-side retry storms) and a stricter tier on `ai-engine`'s outbound calls (protects AI provider spend and respects provider rate limits — see [observability.md](observability.md) for the metric that watches this). Policy is permissive by default in local development, enforced in any shared deployment. Architecture is prepared per the platform-wide requirement even though it's not the MVP's primary risk surface with a single user.

## 7. Audit logging

Every state-changing action across every package writes to `audit_logs` in the same transaction as the change it records — detailed in [database.md](database.md) §1/§3 and [data-flow.md](data-flow.md) §8. Audit rows are immutable: no application code path updates or deletes them, and before production this is additionally enforced at the database role/grant level (the application's DB role has no `UPDATE`/`DELETE` grant on `audit_logs`, only `INSERT`/`SELECT`).

## 8. Sensitive-data handling

- `password_hash` is never included in any API response schema — not omitted by convention, but structurally absent from the Pydantic response model, so it cannot be accidentally serialized.
- AI provider calls ([ai-analyst.md](ai-analyst.md) §5) receive only a bounded market/technical/signal/risk-decision context — never credentials, never other users' data, never `risk_policies` write access. The as-built context has no portfolio-summary field (unlike the Phase 1 sketch this line originally described); the risk section it does include is the *outcome* of a `RiskEvaluation` (decision + reasons), for interpretation only, never a value the AI could feed back into a risk decision.
- Logs are structured (see [observability.md](observability.md)) and scrubbed of secret-shaped values (a logging filter redacts anything matching configured secret key names) before being written or shipped.

## 9. Dependency security

- Backend: `pip-audit` (or `uv`'s equivalent) run in CI against `apps/api` and every `packages/*`; frontend: `npm audit` / Dependabot for `apps/web`. Both wired into GitHub Actions (see the CI/CD phase) so a new critical vulnerability fails the build rather than being discovered later.
- Dependencies are pinned (lockfiles committed for both Python and Node), so builds are reproducible and a vulnerability report maps to an exact installed version.

## 10. Container security

- Backend and frontend images run as a non-root user.
- Multi-stage Docker builds so build-time tooling (compilers, dev dependencies) never ships in the runtime image.
- Base images are pinned to specific digests where practical, not floating `latest` tags, in any environment beyond local development.
- No secret is ever passed as a Docker build arg (build args can leak into image history); all secrets are runtime environment variables only (§1).
