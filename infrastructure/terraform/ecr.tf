# Two repositories, one per image (Step 7). Tags are IMMUTABLE — a
# pushed tag can never be silently overwritten, so an ECS task
# definition's image reference always identifies exactly one build.
# Deploys therefore use unique git-SHA tags, never a floating `latest`
# (see .github/workflows/deploy.yml and docs/aws-deployment.md).

locals {
  ecr_repositories = ["${var.project}-api", "${var.project}-web"]

  # Keep the 10 most recent images per repo; expire anything older so
  # the registry doesn't grow unbounded.
  ecr_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_ecr_repository" "repos" {
  for_each = toset(local.ecr_repositories)

  name                 = each.value
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = { Name = each.value }
}

resource "aws_ecr_lifecycle_policy" "repos" {
  for_each = aws_ecr_repository.repos

  repository = each.value.name
  policy     = local.ecr_lifecycle_policy
}
