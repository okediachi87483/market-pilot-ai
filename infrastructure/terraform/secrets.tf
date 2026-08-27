# Production secrets live in Secrets Manager (Step 12) and are injected
# into containers via ECS's `secrets` mechanism (valueFrom), never
# embedded in task-definition environment values.
#
#   POSTGRES_PASSWORD    — generated here (random_password), never typed
#                          by a human, never committed anywhere.
#   AI_PROVIDER_API_KEY  — created EMPTY. The real Claude key is set
#                          out-of-band by an operator (see
#                          docs/aws-deployment.md §"Setting the AI key")
#                          and Terraform never reads it back:
#                          ignore_changes below means the value an
#                          operator sets is never clobbered by a later
#                          apply, and the real key never enters
#                          Terraform state. An empty key is a fully
#                          supported application state — Phase 8's AI
#                          Analyst reports "not configured" and every
#                          deterministic function keeps working.
#
# Note (documented, not hidden): the *database* password does exist in
# Terraform state, which is local and gitignored. docs/infrastructure.md
# §"State" covers moving state to an encrypted S3 backend.

resource "random_password" "db" {
  length  = 32
  special = false # asyncpg URL-embeds the password; avoid URL-breaking chars
}

resource "aws_secretsmanager_secret" "db_password" {
  name        = "${local.name_prefix}/postgres-password"
  description = "MarketPilot RDS master password (application POSTGRES_PASSWORD)"

  recovery_window_in_days = 0 # allow clean re-creation on destroy/apply cycles
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}

resource "aws_secretsmanager_secret" "ai_api_key" {
  name        = "${local.name_prefix}/ai-provider-api-key"
  description = "Claude API key (application AI_PROVIDER_API_KEY) - set out-of-band, empty means AI Analyst disabled"

  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "ai_api_key" {
  secret_id     = aws_secretsmanager_secret.ai_api_key.id
  secret_string = " " # placeholder; Settings.ai_configured treats blank as unconfigured

  lifecycle {
    ignore_changes = [secret_string]
  }
}
