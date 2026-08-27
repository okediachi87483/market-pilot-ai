# Terraform and provider version pins — see docs/infrastructure.md.
# Provider versions are pinned to a minor series (~>) so a fresh
# `terraform init` cannot silently jump a major version with breaking
# resource-schema changes.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
