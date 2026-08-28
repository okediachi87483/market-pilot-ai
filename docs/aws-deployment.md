# MarketPilot AI — AWS Deployment Runbook

Phase 9.5 (initial deployment), hardened in Phase 9.6 (go-live operational verification — see §10). Operational companion to [docs/infrastructure.md](infrastructure.md) (architecture reference) — this document is "how to actually do things": bootstrap, deploy, roll back, set secrets, and answer the on-call questions in §8.

## 0. Current status (as of Phase 9.7)

| Item | Status |
|---|---|
| AWS infrastructure | **Live**, zero Terraform drift (re-confirmed Phase 9.7) |
| Production URL | `http://marketpilot-prod-alb-1177715901.us-east-1.elb.amazonaws.com` (HTTP only) |
| Domain / HTTPS | **Blocked** — no domain available yet (§4/§10/§11) |
| GitHub repository | **Blocked** — no remote configured, `gh` CLI not installed, and the one SSH keypair present in this environment fails `ssh -T git@github.com` (Permission denied) — not usable (§11) |
| CI/CD execution | **Blocked** — same reason; `ci.yml`/`deploy.yml` audited and correct, never actually run |
| GitHub OIDC role | **Not created** — trust policy scoped to an exact repo+branch (never `repo:*`), stays uncreated until the repository identity is known (§11) |
| Claude / AI Analyst | **Wiring verified, not activated** — no real API key available; `GET /ai/status` correctly reports `configured: false` (§6, §10, §11) |
| Terraform drift | **None** — re-verified live, including after a reverted Redis TLS probe (§11) |
| Redis transit encryption | **Off** — AWS-side change is low-risk (in-place, non-destructive per the pinned provider — verified this phase), but the application has no TLS-capable Redis client yet; a real two-sided migration, not attempted (§11) |

## 1. Prerequisites

- Terraform >= 1.9, AWS CLI v2, Docker.
- AWS credentials for the target account, with permission to create the resources in `infrastructure/terraform/` (or, once bootstrapped, only the scoped `github-deploy` role for CI).
- Nothing else — no Kubernetes, no separate secrets vault, no VPN. The stack is self-contained.

## 2. First-time bootstrap

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars   # edit as needed — see comments in the file
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan                      # READ this before applying
terraform apply tfplan
```

`terraform apply` provisions the VPC, ALB, ECS cluster/services, RDS, ElastiCache, ECR, Secrets Manager, and CloudWatch alarms. The `api`/`web` ECS services come up initially unable to pull a real image (`api_image_tag`/`web_image_tag` default to `"bootstrap"`, which does not exist in ECR yet) — this is expected; push real images next (§3) and the services self-heal without any further Terraform changes.

## 3. Pushing the first images

```bash
AWS_REGION=$(terraform output -raw alb_dns_name >/dev/null; aws configure get region)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

SHA=$(git rev-parse --short HEAD)
docker build -t "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/marketpilot-api:$SHA" apps/api
docker push "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/marketpilot-api:$SHA"

docker build --build-arg NEXT_PUBLIC_API_URL="" \
  -t "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/marketpilot-web:$SHA" apps/web
docker push "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/marketpilot-web:$SHA"
```

Then either re-run `terraform apply -var="api_image_tag=$SHA" -var="web_image_tag=$SHA"`, or — the same path CI uses — register new task-definition revisions pointing at the pushed images and update the services directly (§4's steps 3–5), which is the pattern to use for every deploy after the first.

## 4. Deploy flow (every deploy after the first)

Automated in `.github/workflows/deploy.yml` on push to the protected `production` branch; the manual sequence it runs is:

```
1. Full test suite (backend pytest/ruff/mypy, frontend vitest/eslint/tsc/build)
2. docker build both images, tagged with the git SHA (never `latest`)
3. Push both images to ECR (scan-on-push runs automatically)
4. Register new task-definition revisions (api + migrate + web) pointing at the new images
5. Run the migrate task definition as a ONE-OFF `aws ecs run-task`; wait for it to stop; verify exit code 0
6. Only after the migration succeeds: `aws ecs update-service` for api and web
7. `aws ecs wait services-stable`
8. Smoke test: GET /health, /health/live, /health/ready, /api/v1/, /api/v1/command-center, /dashboard
```

Step 5 is the deliberate answer to "don't run migrations from every task startup" — exactly one migration attempt per deploy, gating the service update, never N concurrent `alembic upgrade head` calls racing each other.

## 5. Rollback

```
current image  = the git SHA just deployed (visible in the ECS console, or `terraform output` after a Terraform-driven deploy)
previous image = the git SHA deployed immediately before it — still in ECR (10-image lifecycle retention, ecr.tf)
```

**Application rollback** — redeploy the previous task-definition revision:

```bash
aws ecs update-service --cluster marketpilot-prod --service api \
  --task-definition marketpilot-prod-api:<previous-revision-number>
aws ecs update-service --cluster marketpilot-prod --service web \
  --task-definition marketpilot-prod-web:<previous-revision-number>
aws ecs wait services-stable --cluster marketpilot-prod --services api web
```

This is fast and safe because ECS task definitions are versioned automatically — every `register-task-definition` call creates a new numbered revision, and old revisions are never deleted.

**Database rollback is NOT automatic and is not claimed to be.** Alembic migrations in this codebase are forward-only by convention (matching Phases 3–9's own migration history — see `docs/database.md` §4, "do not rewrite committed migrations"). If a deploy's migration made a destructive or non-backward-compatible schema change, rolling back the *application* to a previous image while the *schema* has already moved forward is unsafe — the older code may not understand the new schema. For any migration that is not purely additive (a new nullable column, a new table, a new index), the safe sequence is: write and test an explicit down-migration or a compensating forward migration *before* the risky migration ships, never assume `alembic downgrade` is a safe emergency button in production.

## 6. Setting the AI provider key

Terraform creates the `AI_PROVIDER_API_KEY` secret **empty** (a single space, to satisfy Secrets Manager's non-empty constraint) and never reads a real value back into state (`lifecycle.ignore_changes` in `secrets.tf`) — the real Claude key is set out-of-band, once, by an operator:

```bash
aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw ai_api_key_secret_arn)" \
  --secret-string "sk-ant-..."
```

Then force a new deployment so running tasks pick up the new secret value (ECS injects secrets only at container start):

```bash
aws ecs update-service --cluster marketpilot-prod --service api --force-new-deployment
```

An empty/whitespace key is a fully supported state — `Settings.ai_configured` (hardened in this phase to `.strip()` the value first) reports `false`, `GET /ai/status` reports `configured: false`, and every deterministic pipeline stage (market data, signals, risk, paper trading) keeps working — the Phase 8 fail-closed design, unaffected by AWS.

## 6a. Redis TLS rollout

Phase 9.8 added application-side support for `rediss://` (`Settings.redis_tls_enabled`, default `false` — see `apps/api/app/core/config.py`), but the platform still runs with transit encryption **off** end to end. Flipping it is a coupled, two-sided change — the AWS flag and the application's connection scheme must change together, or Redis connectivity breaks outright. Do not flip `redis_transit_encryption_enabled` alone.

The exact sequence, once a human has decided to do this:

1. Confirm the currently-deployed API image actually contains the `redis_tls_enabled` support (i.e. this phase's commit or later is what's running in ECS — check via `aws ecs describe-task-definition` image tag, or simply redeploy first).
2. `terraform plan` with `redis_transit_encryption_enabled = true` set in `terraform.tfvars` — confirm it reports an **in-place update** to `aws_elasticache_replication_group.main` (verified non-destructive in Phase 9.7/9.8 with the pinned provider: `0 to add, 1 to change, 0 to destroy`). If it ever reports a replacement instead (e.g. after a provider upgrade), stop and re-evaluate — do not apply blind.
3. `terraform apply` — this changes the live ElastiCache cluster's transit-encryption setting. The same apply also flips the ECS task definition's `REDIS_TLS_ENABLED` environment variable (both are driven by the one Terraform variable, `infrastructure/terraform/ecs.tf`), but ECS does not restart running tasks on a task-definition-only change.
4. `aws ecs update-service --cluster marketpilot-prod --service api --force-new-deployment` (and `web`, if it ever talks to Redis directly) so running tasks actually pick up `REDIS_TLS_ENABLED=true` and reconnect over `rediss://`.
5. Verify `GET /health/ready` stays `200` (Redis is one of its checks) and tail the API's CloudWatch log group for connection errors for a few minutes after the deploy.
6. If anything fails: revert by setting `redis_transit_encryption_enabled = false` again, `apply`, `force-new-deployment` — the app's plaintext `redis://` path is preserved exactly as it was, so this is a clean rollback, not a data-loss risk (Redis holds no authoritative data).

Not performed in Phase 9.8: no GitHub CI/CD path exists yet to deploy the application-side change through the normal pipeline (§10/§11), and manually pushing an image + forcing a production ECS deployment outside that pipeline is exactly the kind of hard-to-reverse, shared-system action this project's own rules require a human go-ahead for — so the Terraform variable stays at its default (`false`), zero drift is preserved, and this section documents the rollout for whenever a human approves it.

## 7. Domain setup

See [docs/infrastructure.md](infrastructure.md) §9 for the full Terraform-variable walkthrough. Short version: set `domain_name` (+ `create_hosted_zone` as appropriate), `apply`, then point your registrar at the output name servers if Terraform created the zone. Without a domain, the platform is fully functional over plain HTTP on the ALB's own DNS name — HTTPS is additive, not a hard requirement to deploy.

## 8. Operational runbook — answering the standard questions

| Question | Where to look |
|---|---|
| Is the API healthy? | ALB target group `marketpilot-prod-api-tg` health status, or `curl $ORIGIN/health/ready` |
| Is the web app healthy? | ALB target group `marketpilot-prod-web-tg` health status, or `curl $ORIGIN/dashboard` |
| Are ECS tasks running? | `aws ecs describe-services --cluster marketpilot-prod --services api web` — compare `runningCount` to `desiredCount` |
| Can ECS reach Postgres? | `/health/ready`'s `dependencies.postgres` field |
| Can ECS reach Redis? | `/health/ready`'s `dependencies.redis` field |
| Are ALB targets healthy? | `aws elbv2 describe-target-health --target-group-arn <arn>` |
| Are requests returning 5xx? | CloudWatch alarm `marketpilot-prod-target-5xx`, or the `HTTPCode_Target_5XX_Count` metric directly |
| Is the AI provider configured? | `curl $ORIGIN/api/v1/ai/status` — `configured`/`available`, never a key |
| Is the app receiving market data? | Application logs (CloudWatch Logs group `/ecs/marketpilot-api`) — every ingestion cycle logs `provider=... requested=... accepted=...` |

CloudWatch alarms (`cloudwatch.tf`) cover: target 5xx rate, unhealthy targets (api and web separately), API CPU/memory, RDS CPU, RDS free storage. No SNS topic is wired to them yet — they're visible in the CloudWatch console immediately; add an SNS action once there's a real notification channel (email/Slack/PagerDuty) for this project.

## 9. Teardown

```bash
cd infrastructure/terraform
terraform destroy
```

`db_skip_final_snapshot = true` (the tfvars.example default) means destroying the stack does **not** leave an RDS snapshot behind — set it `false` first if you want one. Nothing outside `infrastructure/terraform`'s own state is touched; your account's pre-existing `project-vpc`, `fitprogress-*`, and default-VPC resources are never referenced by this stack.

## 10. Phase 9.6 — go-live hardening audit

A follow-on pass to move from "infrastructure deployed" to "operationally verified," without touching application behavior. Three of the phase's five intended actions hit a genuine environmental blocker and were correctly stopped at that boundary rather than faked — see below. Everything that *could* be verified without those three inputs was re-verified live against the running production stack.

**Blocked, exactly as encountered — nothing fabricated:**

- **GitHub connection blocked: the GitHub CLI (`gh`) is not installed in this environment, and no GitHub remote is configured for this repository (`git remote -v` is empty).** Without `gh` there is no way to authenticate and create/attach a repository from here, and inventing a repository URL is explicitly disallowed. The `github_repository` Terraform variable therefore remains unset — the OIDC provider and deploy role are still not created — and `deploy.yml` has never actually run. Both workflow files were re-read and audited line-by-line against the Step 2 checklist (OIDC-only auth, no hardcoded keys, migration gates the service update, `services-stable` wait, post-deploy smoke test, `workflow_call` reuse of `ci.yml`) and no genuine defect was found; nothing was rewritten.
- **HTTPS blocked because no production domain is currently available.** `aws route53 list-hosted-zones` and `aws acm list-certificates` both returned empty for this account; `.env`/environment inspection found no domain hint. `domain_name` remains unset in `terraform.tfvars` (which itself still doesn't exist — every apply so far has used only the checked-in defaults). The ALB continues serving plain HTTP on its own DNS name.
- **Claude activation blocked: no real Anthropic API key is available anywhere in this environment** (checked the local `.env` — `AI_PROVIDER_API_KEY=` is empty — and the shell environment). Per the phase's own rule, no placeholder was substituted and none was claimed live. What *was* verified: the ECS `api` task definition injects `AI_PROVIDER_API_KEY` via `secrets`/`valueFrom` (the Secrets Manager ARN), never as a plaintext `environment` value (confirmed directly from `aws ecs describe-task-definition`); `GET /api/v1/ai/status` on the live ALB correctly reports `{"configured": false, "available": false}`. The wiring `Secrets Manager → ECS secret injection → Settings.ai_provider_api_key → AIAnalystService` is provably correct; only the real key is missing. Setting one is exactly the `aws secretsmanager put-secret-value` + `--force-new-deployment` sequence in §6 — no code or infrastructure change needed.

**Re-verified live (this phase), not merely re-stated from Phase 9.5:**

- `terraform fmt -check` / `validate` / `plan` — plan reports **"No changes. Your infrastructure matches the configuration"** (zero drift since the Phase 9.5 apply).
- Security groups: RDS and Redis ingress rules carry `IpRanges: []` — SG-referenced only, no CIDR access exists at all, confirmed directly from `describe-security-groups`, not inferred from Terraform source.
- `RDS PubliclyAccessible: false`; both ECS services have `assignPublicIp: DISABLED`; the private-data route table's only route is `local` (no NAT, no IGW) — structurally unreachable from the internet in either direction, not just policy-blocked.
- ECS execution role: exactly `AmazonECSTaskExecutionRolePolicy` + one inline policy scoped to the two secret ARNs it actually reads — no wildcard `secretsmanager:*`, no other permissions. `marketpilot-prod-github-deploy` confirmed not to exist (matches the still-unset `github_repository` variable).
- CloudWatch: all 7 alarms in **OK** state; a live log-tail scan for `password|secret|api_key|sk-ant` across 20 minutes of API logs returned nothing.
- Full production pipeline, executed live against the real ALB (not a rehearsal): evaluated `NVDA` at `15m` → real `BUY`/`CANDIDATE` signal → `POST /risk/evaluate` → `APPROVED`, size `37.1222807929` computed by the Risk Engine (not supplied by AI, not supplied by the caller) → `POST /paper/execute` → `FILLED` at `134.69` → portfolio `equity`/`cash` updated correctly, `open_position_count: 1`. `GET /ai/status` still `configured: false` throughout — the AI Analyst's absence never touched any step of this. This is the same guarantee proven structurally in the Phase 9.5 audit, now also proven live in the actual production environment.

No application code, risk logic, or paper-trading logic was touched in this phase — there was no genuine production defect to fix (§2's workflow audit and §"Full pipeline" above are the closest this phase came to a code-level check, and both passed clean).

## 11. Phase 9.7 — production connectivity, release automation, final deployment readiness

Scope: close the remaining CI/CD gap the workflow audit could still find, re-confirm the three environmental blockers with fresh evidence (not merely re-state Phase 9.6's), and correct one piece of prior documentation that turned out to be more conservative than the actual AWS/provider behavior. No trading logic, risk logic, or database schema was touched — Phase 9.7 is explicitly not Phase 10.

**GitHub — re-confirmed blocked, with stronger evidence than Phase 9.6:**

- `gh --version` / `gh auth status` — command not found (checked via both Bash and PowerShell `Get-Command gh`). No GitHub CLI available in this environment.
- `git remote -v` — empty, as in Phase 9.6.
- New this phase: the one SSH keypair present in this environment (`~/.ssh/github_actions_ec2`) was tested with a safe, read-only `ssh -T git@github.com`. It returned **`Permission denied (publickey)`** — this key is not registered against any GitHub account reachable from here. This rules out the one plausible alternative to `gh` before reporting the blocker, rather than stopping at "no CLI installed."
- Conclusion: **`GITHUB_REMOTE_MISSING`** and **`GITHUB_AUTH_REQUIRED`** both still apply. No repository URL, token, or credential was invented. The `github_repository` Terraform variable remains unset; the OIDC provider/deploy role stay uncreated (see `infrastructure/terraform/iam.tf` — every OIDC/deploy-role resource is gated `count = var.github_repository != "" ? 1 : 0`, confirmed by inspection this phase, unchanged).

**CI/CD — one genuine gap found and closed; no other defect:**

- `.github/workflows/ci.yml` and `deploy.yml` were re-read line-by-line. `deploy.yml` was already correct: OIDC-only (`permissions: id-token: write`, only `${{ vars.* }}` references, no `secrets.AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` anywhere), migration run as a one-off `aws ecs run-task` + `wait tasks-stopped` + exit-code check gating the service update, `aws ecs wait services-stable`, then a post-deploy smoke test (`/health`, `/health/live`, `/health/ready`, `/api/v1/`, `/api/v1/command-center?symbol=AAPL`, `/dashboard`) — no change made.
- `ci.yml` was missing a step its own intended pipeline names: a Docker build validation. Previously a broken `apps/api/Dockerfile` or `apps/web/Dockerfile` would only be discovered by `deploy.yml`, which only runs on the protected `production` branch — too late to catch on a PR. Added a `docker-build` job (no ECR login, no push, no AWS access — pure local `docker build`) that builds both images with the same build args production uses (`--build-arg NEXT_PUBLIC_API_URL=""` for web). Verified locally: both builds succeed (`docker build -t marketpilot-api:ci apps/api` and the web equivalent, exit 0). YAML validity of both files confirmed via `yaml.safe_load()`.
- Because there is no GitHub remote/auth, this workflow still has **never actually executed** on GitHub's infrastructure — audited and locally validated only. **`GITHUB_REPOSITORY_IDENTITY_REQUIRED`** applies to actually running it: even with auth, a repository must exist and be named before `deploy.yml`'s protected-branch trigger or the OIDC trust policy's `repo:<owner>/<repo>:ref:refs/heads/production` condition mean anything.

**Domain / HTTPS — re-confirmed blocked, unchanged from Phase 9.6:**

- No domain, Route 53 hosted zone, or ACM certificate is available in this account or environment. **`DOMAIN_REQUIRED_FOR_HTTPS`** applies. The ALB continues serving plain HTTP only; nothing was invented or defaulted to a placeholder domain.

**Claude / AI Analyst — re-confirmed blocked, re-verified live this phase:**

- No real Anthropic API key is present anywhere in this environment (`.env`, shell environment both checked). **`ANTHROPIC_API_KEY_REQUIRED`** applies.
- Re-verified live against the production ALB this phase (not merely re-stated): `GET /api/v1/ai/status` → `{"configured":false,"available":false,"provider":"anthropic","model":"claude-sonnet-5"}`; the same `configured: false` surfaces correctly inside `GET /api/v1/command-center?symbol=AAPL`'s `system_health.ai` block, alongside `api`/`database`/`redis`/`market_data` all reporting `ok`. The wiring is provably correct; only the key is missing.

**Redis transit encryption — corrected this phase, not merely re-stated:**

- Phase 9.5/9.6 documentation assumed enabling `transit_encryption_enabled` on the live ElastiCache replication group would be a destructive replacement. This phase tested that assumption directly with a local-only, never-applied probe: temporarily edited `infrastructure/terraform/redis.tf` to `transit_encryption_enabled = true`, ran `terraform plan`, and observed `aws_elasticache_replication_group.main` reported as an **in-place update** — `Plan: 0 to add, 1 to change, 0 to destroy` — not a replacement, with the pinned AWS provider (`~> 6.0`). The edit was immediately reverted; a follow-up `terraform plan` confirmed **"No changes. Your infrastructure matches the configuration"** and `git diff --stat`/`git status --short` on the file were both empty — zero residual change from the probe.
- This corrects the infrastructure-side risk assessment, but does **not** clear the blocker: `app/db/redis.py` (`Redis.from_url(settings.redis_url, ...)`) and `Settings.redis_url` (`apps/api/app/core/config.py`) construct only plain `redis://` URLs — no `rediss://`, no TLS/cert handling anywhere in the client. Flipping the AWS-side flag without a coordinated application-side change (a `rediss://`-capable client, plus AWS's own phased `transit_encryption_mode` rollout — `preferred` before `required` — to avoid a hard connectivity break) would be a real, two-sided migration. **`REDIS_TLS_MIGRATION_REQUIRED`** applies; not attempted blind, per the phase's own rule against unnecessary infrastructure changes.
- `docs/infrastructure.md` §"Known limitations" updated to record this correction.

**Dependency security — re-verified against the actual built images, not source-level assumption:**

- `apps/web`: `package.json` declares a top-level `postcss` (for Tailwind via `@tailwindcss/postcss`), and `postcss.config.mjs` exists, but `grep -rln "postcss" app/ components/ lib/` is empty — application code never invokes it directly. Inspected the actual built runtime image (`docker run --rm marketpilot-web:ci sh -c "find / -iname 'postcss*' ..."`): postcss binaries/loaders are present under `node_modules/next/...` inside the standalone image (Next.js's `output: "standalone"` bundles a trimmed `node_modules` into the runtime, not just the build stage). Conclusion: present in the image, but unreachable at request time — the standalone server does zero request-time CSS/postcss work; all processing happens once at `npm run build`.
- `apps/api`: inspected the built runtime image for known-vulnerable-in-source packages. `pytest`, `ruff`, `mypy` confirmed **absent** (the Dockerfile's non-dev `pip install --prefix=/install .` correctly excludes them). `starlette` confirmed **present** and importable — genuinely a runtime, production-container-affecting dependency (FastAPI's transitive dependency), not a dev-only false positive.
- No blind `npm audit fix --force` or major-version bump was performed — the phase's rule against blind dependency changes was followed; this workstream was re-verification of exposure, not remediation, since no actionable, currently-unpatched runtime CVE was found requiring an immediate bump.

**Production smoke tests — executed fresh this phase against the live ALB** (`http://marketpilot-prod-alb-1177715901.us-east-1.elb.amazonaws.com`):

| Check | Result |
|---|---|
| `GET /health`, `/health/live`, `/health/ready` | 200 |
| `GET /api/v1/` | 200 |
| `GET /dashboard`, `/markets`, `/signals`, `/risk`, `/paper`, `/ai-analyst` | 200 |
| `GET /api/v1/command-center?symbol=AAPL` | 200 — full aggregation returned (`system_health`: api/database/redis/market_data all `ok`, ai `configured:false` as expected; `market` block populated for AAPL from the mock provider) |
| `GET /api/v1/ai/status` | `{"configured":false,"available":false,...}` — correct given no key |

**Terraform drift — re-verified this phase, including after the Redis probe above:** `terraform plan` → **"No changes. Your infrastructure matches the configuration."**

**Summary of blockers carried forward, all with fresh Phase 9.7 evidence:** `GITHUB_REMOTE_MISSING`, `GITHUB_AUTH_REQUIRED`, `GITHUB_REPOSITORY_IDENTITY_REQUIRED`, `DOMAIN_REQUIRED_FOR_HTTPS`, `ANTHROPIC_API_KEY_REQUIRED`, `REDIS_TLS_MIGRATION_REQUIRED`. None of these were worked around, faked, or defaulted past — each requires a specific human action outside this environment (see the Final Report's recommendation).
