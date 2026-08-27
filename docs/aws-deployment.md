# MarketPilot AI — AWS Deployment Runbook

Phase 9.5 (initial deployment), hardened in Phase 9.6 (go-live operational verification — see §10). Operational companion to [docs/infrastructure.md](infrastructure.md) (architecture reference) — this document is "how to actually do things": bootstrap, deploy, roll back, set secrets, and answer the on-call questions in §8.

## 0. Current status (as of Phase 9.6)

| Item | Status |
|---|---|
| AWS infrastructure | **Live**, zero Terraform drift as of this phase's audit |
| Production URL | `http://marketpilot-prod-alb-1177715901.us-east-1.elb.amazonaws.com` (HTTP only) |
| Domain / HTTPS | **Blocked** — no domain available yet (§4/§10) |
| GitHub repository / CI-CD execution | **Blocked** — no GitHub remote configured, `gh` CLI not installed in this environment (§10) |
| Claude / AI Analyst | **Wiring verified, not activated** — no real API key available; `GET /ai/status` correctly reports `configured: false` (§6, §10) |
| Terraform drift | **None** — `terraform plan` reports "No changes" as of the Phase 9.6 audit |

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
