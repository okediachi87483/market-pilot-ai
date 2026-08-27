# Route 53 (Step 19) — only when a domain is configured.
#
# Two modes:
#   create_hosted_zone = true   → this stack creates the zone; the
#     domain registrar must then be pointed at the zone's NS records
#     (output `hosted_zone_name_servers`).
#   create_hosted_zone = false  → a zone for domain_name already exists
#     in this account and is looked up.
#
# DNS delegation is the one step Terraform cannot do for you — see
# docs/aws-deployment.md §"Domain setup".

resource "aws_route53_zone" "main" {
  count = local.https_enabled && var.create_hosted_zone ? 1 : 0

  name = var.domain_name
}

data "aws_route53_zone" "existing" {
  count = local.https_enabled && !var.create_hosted_zone ? 1 : 0

  name         = var.domain_name
  private_zone = false
}

locals {
  hosted_zone_id = (
    local.https_enabled
    ? (var.create_hosted_zone ? aws_route53_zone.main[0].zone_id : data.aws_route53_zone.existing[0].zone_id)
    : null
  )
}

resource "aws_route53_record" "site" {
  count = local.https_enabled ? 1 : 0

  zone_id = local.hosted_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
