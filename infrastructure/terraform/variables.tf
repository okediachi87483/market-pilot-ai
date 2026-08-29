# All environment-specific values are variables — nothing
# region/account/size-specific is hardcoded in resource blocks.
# See terraform.tfvars.example for a documented starting point.

# --- global ----------------------------------------------------------------

variable "aws_region" {
  description = "AWS region for every resource in this stack."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project slug used in resource names and tags."
  type        = string
  default     = "marketpilot"
}

variable "environment" {
  description = "Environment slug used in resource names and tags (e.g. prod, staging)."
  type        = string
  default     = "prod"
}

# --- networking ------------------------------------------------------------

variable "vpc_cidr" {
  description = <<-EOT
    CIDR block for the VPC. Deliberately NOT 10.0.0.0/16 by default —
    this account already contains an unrelated VPC using that range,
    and distinct ranges keep any future peering/troubleshooting sane.
  EOT
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across (ALB requires >= 2)."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2
    error_message = "az_count must be at least 2 — an ALB requires subnets in two AZs."
  }
}

# --- ECS sizing (Step 8: conservative defaults, all configurable) ----------

variable "api_cpu" {
  description = "Fargate CPU units for the API task (256 = 0.25 vCPU)."
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "Fargate memory (MiB) for the API task."
  type        = number
  default     = 512
}

variable "web_cpu" {
  description = "Fargate CPU units for the Web task."
  type        = number
  default     = 256
}

variable "web_memory" {
  description = "Fargate memory (MiB) for the Web task."
  type        = number
  default     = 512
}

variable "api_desired_count" {
  description = "Desired number of API tasks."
  type        = number
  default     = 1
}

variable "web_desired_count" {
  description = "Desired number of Web tasks."
  type        = number
  default     = 1
}

# --- images ---------------------------------------------------------------

variable "api_image_tag" {
  description = <<-EOT
    Image tag the API service runs. Deployments pass an immutable git-SHA
    tag (never a floating `latest`) so the exact deployed version is
    always identifiable — see docs/aws-deployment.md §"Deploy flow".
  EOT
  type        = string
  default     = "bootstrap"
}

variable "web_image_tag" {
  description = "Image tag the Web service runs (immutable git-SHA tags in practice)."
  type        = string
  default     = "bootstrap"
}

# --- database --------------------------------------------------------------

variable "db_engine_version" {
  description = "RDS PostgreSQL engine version — major version 16 matches the postgres:16 image the app develops and migrates against. Pinned to a specific minor (not just \"16\") so a `terraform apply` never silently jumps a minor version; verify availability with `aws rds describe-db-engine-versions --engine postgres` before changing it — RDS drops old minors from new-instance availability over time."
  type        = string
  default     = "16.15"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GiB."
  type        = number
  default     = 20
}

variable "db_backup_retention_days" {
  description = "Automated backup retention in days."
  type        = number
  default     = 7
}

variable "db_deletion_protection" {
  description = <<-EOT
    RDS deletion protection. Default false so a paper-trading/portfolio
    stack stays cheaply destroyable; set true (see tfvars.example) the
    moment the database holds state you would miss.
  EOT
  type        = bool
  default     = false
}

variable "db_skip_final_snapshot" {
  description = "Skip the final snapshot on destroy. Set false for production-grade teardown safety."
  type        = bool
  default     = true
}

variable "db_name" {
  description = "Initial database name (matches the application's POSTGRES_DB)."
  type        = string
  default     = "marketpilot"
}

variable "db_username" {
  description = "Master username (matches the application's POSTGRES_USER)."
  type        = string
  default     = "marketpilot"
}

# --- redis -----------------------------------------------------------------

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "redis_transit_encryption_enabled" {
  description = <<-EOT
    Enables ElastiCache in-transit encryption AND switches the
    application to rediss:// in one apply — the two sides are coupled
    deliberately, since flipping only one would break connectivity.
    Default false preserves the current plaintext redis:// model.
    Phase 9.8 proved the AWS-side flip is a non-destructive in-place
    update (see docs/aws-deployment.md §"Redis TLS"); this variable is
    the switch, not yet flipped to true in any checked-in tfvars.
  EOT
  type        = bool
  default     = false
}

# --- application configuration --------------------------------------------

variable "ai_provider" {
  description = "AI provider name passed to the application (AI_PROVIDER)."
  type        = string
  default     = "anthropic"
}

variable "ai_model" {
  description = "AI model passed to the application (AI_MODEL)."
  type        = string
  default     = "claude-sonnet-5"
}

variable "log_level" {
  description = "Application log level (LOG_LEVEL)."
  type        = string
  default     = "INFO"
}

variable "log_retention_days" {
  description = "CloudWatch log retention for both services."
  type        = number
  default     = 30
}

# --- domain / HTTPS (Step 19: optional — the stack deploys without one) ----

variable "domain_name" {
  description = <<-EOT
    Public domain for the platform (e.g. marketpilot.example.com).
    Leave empty to deploy without Route 53/ACM — the ALB then serves
    plain HTTP on its own DNS name, and every HTTPS/Route 53 resource
    in this stack is simply not created. Setting it later creates the
    ACM certificate (DNS-validated), the HTTPS listener, the HTTP→HTTPS
    redirect, and the alias record, with no other changes.
  EOT
  type        = string
  default     = ""
}

variable "create_hosted_zone" {
  description = "Create the Route 53 hosted zone for domain_name (false = a zone for it already exists in this account and is looked up instead)."
  type        = bool
  default     = false
}

# --- CI/CD (Step 16: OIDC, no long-lived keys) -----------------------------

variable "github_repository" {
  description = <<-EOT
    GitHub repository allowed to assume the deploy role via OIDC, as
    "owner/repo". Leave empty to skip creating the OIDC provider and
    deploy role entirely (e.g. before the repository has a GitHub
    remote). Documentation/identification only — the actual trust
    condition uses github_oidc_subject (see there for why).
  EOT
  type        = string
  default     = ""
}

variable "github_oidc_subject" {
  description = <<-EOT
    The exact `token.actions.githubusercontent.com:sub` claim value the
    deploy role's trust policy matches (StringEquals). Must be read
    from this GitHub instance directly — GET
    /repos/{owner}/{repo}/actions/oidc/customization/sub — rather than
    assumed as `repo:<owner>/<repo>:ref:refs/heads/production`: this
    instance's current default format embeds immutable owner/repo IDs
    (`repo:<owner>@<ownerId>/<repo>@<repoId>:ref:...`). Leave empty
    alongside github_repository until both are known.
  EOT
  type        = string
  default     = ""
}
