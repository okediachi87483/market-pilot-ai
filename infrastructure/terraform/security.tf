# Security groups — least privilege, one per tier (docs/infrastructure.md
# §"Security groups"):
#
#   internet → ALB       :80 (+ :443 when a domain/cert exists)
#   ALB      → ECS       :8000 (api) / :3000 (web) — by SG reference
#   ECS      → RDS       :5432 — by SG reference
#   ECS      → Redis     :6379 — by SG reference
#
# No 0.0.0.0/0 ingress exists anywhere except the ALB's public web
# ports. All cross-tier rules reference security groups, never CIDRs,
# so they stay correct if subnets are ever renumbered.

resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb"
  description = "Public entry point - internet to ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from anywhere (redirects to HTTPS when a certificate exists)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = local.https_enabled ? [1] : []
    content {
      description = "HTTPS from anywhere"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  egress {
    description = "To ECS targets"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-alb-sg" }
}

resource "aws_security_group" "ecs" {
  name        = "${local.name_prefix}-ecs"
  description = "ECS tasks - inbound from ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "API port from ALB"
    from_port       = local.api_port
    to_port         = local.api_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Web port from ALB"
    from_port       = local.web_port
    to_port         = local.web_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Outbound: ECR/CloudWatch/Secrets Manager/Anthropic API (via NAT), RDS, Redis"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-ecs-sg" }
}

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds"
  description = "RDS PostgreSQL - inbound from ECS only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from ECS tasks"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  # No egress rules: the database never initiates connections.

  tags = { Name = "${local.name_prefix}-rds-sg" }
}

resource "aws_security_group" "redis" {
  name        = "${local.name_prefix}-redis"
  description = "ElastiCache Redis - inbound from ECS only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from ECS tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  tags = { Name = "${local.name_prefix}-redis-sg" }
}
