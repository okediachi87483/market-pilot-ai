locals {
  name_prefix = "${var.project}-${var.environment}"

  # ALB origin used for CORS and (via the deploy script's build arg
  # decision) the frontend's API origin. With a domain the site is
  # https://<domain>; without one it is plain http on the ALB DNS name.
  https_enabled = var.domain_name != ""
  site_origin = (
    local.https_enabled ? "https://${var.domain_name}" : "http://${aws_lb.main.dns_name}"
  )

  # Container ports — fixed by the existing Dockerfiles (EXPOSE 8000 /
  # EXPOSE 3000), not configurable here because the images aren't.
  api_port = 8000
  web_port = 3000
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}
