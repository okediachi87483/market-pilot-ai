# MarketPilot AI — Infrastructure

Phase 9.5. AWS deployment of the existing Phase 1–9 application — this document is the infrastructure reference; [docs/aws-deployment.md](aws-deployment.md) is the operational runbook (deploy flow, rollback, day-2 operations). Nothing in Phases 1–9's architecture changed to accommodate AWS: the same containers, the same Alembic migrations, the same `/health`/`/health/live`/`/health/ready` endpoints, the same `Settings` configuration surface.

## 1. Architecture

```
                         INTERNET
                            │
                            ▼
                  Route 53 (optional — §9)
                            │
                            ▼
                 Application Load Balancer  (public subnets)
                            │
              ┌─────────────┼──────────────┐
              │ /api/*, /health*            │ everything else
              ▼                             ▼
     ECS Fargate — api                 ECS Fargate — web
     (private app subnets)             (private app subnets)
              │
   ┌──────────┴──────────┐
   ▼                      ▼
RDS PostgreSQL       ElastiCache Redis
(private data subnets, no internet route either direction)

CloudWatch Logs + Alarms ← both services
GitHub Actions → OIDC → ECR → ECS (§14)
```

One ALB, one origin, path-based routing (§4) — not two load balancers or two domains. This is still the modular monolith Phase 1 committed to (`docs/architecture.md` §2): two containers, no service mesh, no Kubernetes, no message queue.

## 2. Terraform structure

`infrastructure/terraform/` — one file per concern, matching the codebase's own "package-per-bounded-context" convention:

| File | Owns |
|---|---|
| `versions.tf` / `providers.tf` | Terraform + AWS/random provider pins, default tags |
| `variables.tf` / `locals.tf` | Every environment-specific value (region, sizing, image tags, domain) as a variable — nothing hardcoded in a resource block |
| `networking.tf` | VPC, subnets (public / private-app / private-data), one NAT gateway, route tables |
| `security.tf` | Four security groups (ALB / ECS / RDS / Redis), all cross-tier rules by SG reference, never a raw CIDR into a data tier |
| `ecr.tf` | Two repositories, immutable tags, scan-on-push, a 10-image lifecycle policy |
| `secrets.tf` | `random_password` for the DB, two Secrets Manager secrets (DB password, AI key) |
| `iam.tf` | ECS task execution role (scoped to exactly the two secrets it reads) + the GitHub OIDC deploy role |
| `rds.tf` | PostgreSQL 16, private, encrypted, automated backups |
| `redis.tf` | ElastiCache Redis, private, encrypted at rest |
| `alb.tf` | Load balancer, two target groups, HTTP/HTTPS listeners, path routing |
| `acm.tf` / `route53.tf` | Certificate + DNS — created only when `domain_name` is set (§9) |
| `ecs.tf` | Cluster, three task definitions (api, web, migrate), two services, log groups |
| `cloudwatch.tf` | Alarms — deliberately few (§8) |
| `outputs.tf` | Everything an operator or the deploy pipeline needs to read back |
| `terraform.tfvars.example` | Documented starting point — copy to `terraform.tfvars` (gitignored) |

State is local by default (`terraform.tfstate`, gitignored — never commit it, since it contains the RDS/Redis endpoints and, transiently, the generated DB password). Moving to a remote encrypted backend (S3 + DynamoDB lock table) is a genuine improvement for a team but was not added unprompted here — a backend change is exactly the kind of infrastructure decision that shouldn't be made silently on someone else's behalf; add an `S3` backend block to `versions.tf` when more than one operator needs to run `terraform apply`.

## 3. Networking

| Tier | Subnets | Internet route | Holds |
|---|---|---|---|
| Public | 2 (one per AZ) | Internet Gateway | ALB, the one NAT Gateway |
| Private-app | 2 | NAT Gateway (outbound only) | ECS Fargate tasks (api, web) |
| Private-data | 2 | none | RDS, ElastiCache |

`enable_dns_support`/`enable_dns_hostnames` are both on (required for RDS/ElastiCache endpoint resolution and ECS service discovery). ECS tasks need *outbound* internet — to pull images from ECR, ship logs to CloudWatch, read secrets from Secrets Manager, and (only when the AI Analyst is configured) call `api.anthropic.com` — but never *inbound*; the private-app route table's only route is the NAT gateway. The private-data route table has no default route at all: RDS and Redis cannot reach the internet in either direction, structurally, not just by security-group policy.

**One NAT gateway, not one per AZ** — the deliberate cost/availability tradeoff for this platform's scale; see §8.

## 4. Security groups

```
internet ──:80/:443──▶ ALB
ALB      ──:8000──────▶ ECS (api target)
ALB      ──:3000──────▶ ECS (web target)
ECS      ──:5432──────▶ RDS
ECS      ──:6379──────▶ Redis
```

No security group allows `0.0.0.0/0` on any port except the ALB's own public listener ports. Every cross-tier rule references a security group ID, never a CIDR block — a subnet renumbering can never silently change who can reach the database.

**Single-origin routing**: the ALB routes `/api/*`, `/health`, `/health/*`, `/docs`, `/openapi.json` to the API target group; everything else goes to the Web target group. Both services are served from the same domain/ALB DNS name, so the production frontend build passes `NEXT_PUBLIC_API_URL=""` (`apps/web/Dockerfile`'s new `ARG`) — every API call becomes a same-origin relative fetch (`/api/v1/...`), which needs no CORS grant beyond same-origin, and doesn't require a rebuild if the domain changes later. `CORS_ORIGINS` (`app/core/config.py`) is still set — to `local.site_origin` — as defense-in-depth for any direct cross-origin call, but same-origin routing means production traffic doesn't depend on it working perfectly.

## 5. Compute — ECS Fargate

Two long-running services (`api`, `web`) plus one **task definition that is never a service** — `migrate` (§7). All three share the same execution role and log to their own CloudWatch log group. Sizing is entirely variable-driven (`api_cpu`/`api_memory`/`web_cpu`/`web_memory`/`*_desired_count` in `variables.tf`), defaulting to the smallest practical Fargate footprint (0.25 vCPU / 512 MiB, one task each) — raise them when load actually demands it, not preemptively.

No autoscaling is configured. At `desired_count = 1` per service there is nothing to scale between, and adding a scaling policy now would be unearned complexity — see docs/instruction context. `desired_count`, `api_cpu`/`api_memory`, `web_cpu`/`web_memory` are all plain Terraform variables, so raising task count or size later is a one-line change, and Application Auto Scaling (target-tracking on ECS `CPUUtilization`) is the natural next step once real traffic data exists to set a sensible threshold.

Container health checks use **`/health/live`** (api) and a `fetch('/dashboard')` probe (web, matching the existing Dockerfile `HEALTHCHECK`) — pure liveness, "should this task be restarted." The **ALB** target-group health checks use **`/health/ready`** (api, checks Postgres + Redis) and `/dashboard` (web) — "should this task receive traffic." Neither check depends on the AI provider: `/health/ready` only checks Postgres and Redis (`app/api/health.py`), so an unconfigured or unreachable Claude API never makes a task unhealthy — the Phase 8 fail-closed design is preserved exactly at the infrastructure layer.

## 6. Data tier

- **RDS PostgreSQL** — engine 16 (matching `postgres:16-alpine` in `docker-compose.yml`), `db.t4g.micro`, 20 GiB gp3 encrypted storage, 7-day automated backups, private-data subnets, no public accessibility, security group scoped to the ECS tier. No custom parameter group — the application needs no non-default engine parameter. `deletion_protection`/`skip_final_snapshot` default to the cheap/disposable-environment values (`false`/`true`) — flip both before this holds data you'd miss (`terraform.tfvars.example` calls this out explicitly).
- **ElastiCache Redis** — single node, `cache.t4g.micro`, encrypted at rest, private-data subnets, ECS-only security group. Transit encryption is **off**, deliberately: `app/db/redis.py`'s connection model is `redis://host:port/db` with no TLS scheme and no AUTH token, and this phase's mandate is to deploy the existing application, not rewrite its Redis client. The compensating control is structural, not just policy — Redis has no internet route in either direction and accepts connections from the ECS security group only. Since `docs/architecture.md` already commits to "Redis is disposable, never authoritative," this is a documented, bounded tradeoff, not an oversight (§11, Known limitations).

Alembic migrations remain the schema authority exactly as Phases 3–9 built them — no schema changed to accommodate AWS.

## 7. Migration strategy

The API image's entrypoint (`apps/api/docker-entrypoint.sh`) now branches on `RUN_MIGRATIONS_ON_STARTUP` (default `true`, preserving today's single-container local/docker-compose behavior unchanged) and, when given arguments, execs them instead of starting the server. Production sets `RUN_MIGRATIONS_ON_STARTUP=false` on the `api` service and uses the separate `aws_ecs_task_definition.migrate` (same image, `command: ["alembic", "upgrade", "head"]`) as a **one-off task**, run once, to completion, before the service is ever updated:

```
build image → push (git-SHA tag) → run migrate task → wait for exit 0
    → register new api/web task definitions → update services → wait stable
```

This is what closes the exact race the phase's own instructions warn about: N rolling API tasks each independently running `alembic upgrade head` on startup. See [docs/aws-deployment.md](aws-deployment.md) §"Deploy flow" for the full, automated sequence.

## 8. Cost

Approximate monthly cost at the default sizing (`us-east-1`, on-demand pricing — verify against the current AWS Pricing Calculator before relying on this number):

| Resource | ~Monthly |
|---|---|
| NAT Gateway (1, hourly + data processing) | ~$33 |
| Application Load Balancer | ~$16 + LCU usage |
| RDS `db.t4g.micro` (single-AZ) + 20 GiB gp3 | ~$15–20 |
| ElastiCache `cache.t4g.micro` (single node) | ~$12 |
| ECS Fargate, 2 tasks × 0.25 vCPU/512 MiB, ~730h | ~$15 |
| ECR storage, CloudWatch Logs/alarms, Secrets Manager (2 secrets) | ~$3–5 |
| **Total** | **~$95–105/month** |

**Deliberately avoided** (would raise this materially with no benefit at this scale): a NAT gateway per AZ (~2× the NAT cost for HA the platform doesn't need at desired_count=1), RDS Multi-AZ, ElastiCache replicas/cluster mode, autoscaling headroom, Container Insights (`containerInsights = "disabled"` — CloudWatch's free-tier metrics + application logs already answer every operational question in §12), and a second ALB or a per-service domain. If a genuinely cheaper architecture were adequate, it would replace the NAT gateway with VPC endpoints (S3/ECR/CloudWatch/Secrets Manager gateway+interface endpoints, ~$7/mo each) instead of the NAT's ~$33 flat cost plus data processing — not done here because the endpoint count (5+) approaches the NAT's cost at this traffic level and adds real configuration surface for a marginal saving; revisit if data-processing charges from the NAT become the dominant line item.

## 9. Domain / HTTPS

`domain_name` (empty by default) gates every Route 53/ACM resource in the stack — with it unset, the ALB serves plain HTTP on its own AWS-assigned DNS name (`alb_dns_name` output) and no certificate, hosted zone, or DNS record is created at all. Setting it:

1. Set `domain_name = "your.domain"` in `terraform.tfvars` (and `create_hosted_zone = true` if no Route 53 zone for it exists yet, `false` if one does).
2. `terraform apply` — creates the ACM certificate (DNS-validated automatically through the zone), the HTTPS listener, the HTTP→HTTPS redirect, and the `A`-alias record.
3. **The one manual step Terraform cannot do**: if `create_hosted_zone = true`, point your domain registrar's NS records at the zone's name servers (`terraform output hosted_zone_name_servers`). DNS propagation can take up to 48 hours, though it's typically much faster.

## 10. Environment configuration

Every variable in `app/core/config.py::Settings` is preserved under its existing name — `AI_PROVIDER`, `AI_MODEL`, `AI_PROVIDER_API_KEY`, `POSTGRES_*`, `REDIS_*`, `CORS_ORIGINS`, `LOG_LEVEL`, `APP_ENV`. Nothing was renamed, and no second/duplicate configuration mechanism was introduced. Production values are set two ways:

- **Plain values** (host/port/names/log level/CORS origin) — task-definition `environment` entries in `ecs.tf`, computed from other Terraform resources (e.g. `POSTGRES_HOST` = the real RDS endpoint) so they can never drift from the actual infrastructure.
- **Secrets** (`POSTGRES_PASSWORD`, `AI_PROVIDER_API_KEY`) — task-definition `secrets` entries (`valueFrom` a Secrets Manager ARN); the ECS agent injects the real value at container start, and the value is never visible in the task definition, the Terraform plan output, or any log (§11).

`.env.example` is unchanged in spirit — placeholders only, documents every variable including the one new deployment-only variable `RUN_MIGRATIONS_ON_STARTUP` (read by the shell entrypoint, not the Python app).

## 11. Known limitations

- Redis has no transit encryption (§6) — a deliberate, bounded tradeoff (Redis is cache/pub-sub only, never authoritative, per `docs/architecture.md`).
- RDS and ElastiCache are single-node/single-AZ — no automatic failover. Acceptable for a paper-trading platform whose system of record (Postgres) is backed up daily with 7-day retention; revisit `multi_az`/`automatic_failover_enabled` before this serves real financial data.
- No autoscaling (§5) — `desired_count` is a manual/Terraform-variable lever.
- Terraform state is local (§2) — fine for one operator, not for a team; migrate to an S3+DynamoDB backend before a second person needs to run `apply`.
- No WAF in front of the ALB — not added because nothing in this phase's threat model (a paper-trading demo with no real money movement) currently justifies it; revisit if the platform is ever exposed as a public product.
- The starlette/pip/pytest/postcss dependency advisories documented in the Phase 9.5 audit report remain open — they require major-version application dependency upgrades, out of scope for an infrastructure phase.
- **No domain/HTTPS yet** — no domain was available as of Phase 9.6; the ALB serves plain HTTP on its own DNS name. `domain_name`/`create_hosted_zone` (§9) are ready the moment one exists — no other change needed.
- **CI/CD is implemented but has never actually run** — no GitHub remote is configured for this repository and the GitHub CLI isn't installed in this environment (Phase 9.6), so the OIDC deploy role (`github_repository` variable) was never created and `deploy.yml` has never executed. `docs/aws-deployment.md` §10 has the exact blocker and the one-variable fix once a repository exists.
- **The AI Analyst is verified-but-inactive** — Secrets Manager → ECS secret injection → `Settings.ai_provider_api_key` → `AIAnalystService` was confirmed correct end-to-end (Phase 9.6), but no real Claude API key exists in this environment to actually activate it. `GET /ai/status` correctly reports `configured: false`, and the rest of the platform is provably unaffected (verified with a live signal → risk → paper-trade round trip on the production ALB while AI remained unconfigured).
