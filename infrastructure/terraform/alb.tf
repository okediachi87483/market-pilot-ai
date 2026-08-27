# Application Load Balancer (Step 9) — the single public entry point.
#
# One ALB serves BOTH services by path:
#
#   /api/*    → API target group   (FastAPI, port 8000)
#   /health*  → API target group   (external liveness/readiness probes)
#   /docs, /openapi.json → API target group (FastAPI's own docs)
#   default   → Web target group   (Next.js, port 3000)
#
# Because web and API share one origin, the production frontend is
# built with NEXT_PUBLIC_API_URL="" (same-origin relative fetches) — no
# wildcard CORS, no rebuild when the domain changes, one certificate.
# See docs/infrastructure.md §"Single-origin routing".
#
# Health-check semantics (Step 22):
#   ALB → API target:  /health/ready — full readiness (Postgres + Redis
#                      reachable). A task that can't reach its
#                      dependencies receives no traffic.
#   ALB → Web target:  /dashboard — the real page the product serves.
#   ECS container checks (ecs.tf) use /health/live — pure liveness,
#   "should this container be restarted", per docs/observability.md §4.
# Neither depends on the AI provider: /health/ready checks Postgres and
# Redis only, so an unavailable Claude never makes the platform
# unhealthy (the Phase 8 fail-closed design).

resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  tags = { Name = "${local.name_prefix}-alb" }
}

resource "aws_lb_target_group" "api" {
  name        = "${local.name_prefix}-api-tg"
  port        = local.api_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  # Small deregistration delay — the API serves short JSON requests; 30s
  # comfortably drains in-flight requests without slowing deployments.
  deregistration_delay = 30

  health_check {
    path                = "/health/ready"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = { Name = "${local.name_prefix}-api-tg" }
}

resource "aws_lb_target_group" "web" {
  name        = "${local.name_prefix}-web-tg"
  port        = local.web_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  deregistration_delay = 30

  health_check {
    path                = "/dashboard"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = { Name = "${local.name_prefix}-web-tg" }
}

# --- listeners --------------------------------------------------------------

# Without a domain: HTTP :80 forwards (the only possible entry point —
# HTTPS requires a certificate, which requires a domain).
# With a domain: HTTP :80 redirects to HTTPS, and the :443 listener
# (below) carries the real traffic.

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = local.https_enabled ? [] : [1]
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.web.arn
    }
  }

  dynamic "default_action" {
    for_each = local.https_enabled ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count = local.https_enabled ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.main[0].certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

# --- path routing to the API (attached to whichever listener serves traffic)

locals {
  serving_listener_arn = (
    local.https_enabled ? aws_lb_listener.https[0].arn : aws_lb_listener.http.arn
  )
  api_path_patterns = ["/api/*", "/health", "/health/*", "/docs", "/openapi.json"]
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = local.serving_listener_arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = local.api_path_patterns
    }
  }
}
