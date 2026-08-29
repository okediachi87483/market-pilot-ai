# IAM — least privilege (Step 16).
#
#   Task execution role — what the ECS *agent* uses to pull images,
#     write logs, and fetch the two injected secrets. Scoped to exactly
#     those two secret ARNs, not secretsmanager:*.
#   Task role — deliberately NOT created: the application makes no AWS
#     API calls (Postgres/Redis/Anthropic are plain network calls), so
#     a task role would be an empty grant waiting to accumulate scope.
#   GitHub Actions deploy role — OIDC-federated (no long-lived access
#     keys), created only when `github_repository` is set, and scoped to
#     ECR push, task-definition registration, service update, and the
#     migration one-off task.

# --- ECS task execution role ------------------------------------------------

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${local.name_prefix}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_execution_secrets" {
  statement {
    sid     = "ReadInjectedSecrets"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.db_password.arn,
      aws_secretsmanager_secret.ai_api_key.arn,
    ]
  }
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name   = "${local.name_prefix}-ecs-execution-secrets"
  role   = aws_iam_role.ecs_execution.id
  policy = data.aws_iam_policy_document.ecs_execution_secrets.json
}

# --- GitHub Actions OIDC deploy role (conditional) --------------------------
#
# The OIDC provider for token.actions.githubusercontent.com is looked
# up, never created: AWS permits only one such provider per URL per
# account, and this account already has one (pre-dating this project —
# likely provisioned for a different repository/project sharing the
# account). Referencing it via a data source is safe regardless of who
# created it: any IAM role in this account may trust any OIDC provider
# in this same account, and provider identity is fully determined by
# its URL/thumbprints (both independently verified to be the genuine
# GitHub Actions issuer), not by which Terraform state "owns" it.
# Creating a second provider for the same URL is not just redundant —
# AWS rejects it outright (one provider per URL per account).

data "aws_iam_openid_connect_provider" "github" {
  count = var.github_repository != "" ? 1 : 0

  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "github_assume" {
  count = var.github_repository != "" ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Only this repository — and only its production branch — may assume
    # the deploy role (matches deploy.yml's trigger branch).
    #
    # StringEquals against the exact sub claim, not a name-based
    # StringLike pattern: this GitHub instance's current default OIDC
    # subject format embeds immutable owner/repo IDs
    # (repo:<owner>@<ownerId>/<repo>@<repoId>:ref:...), confirmed via a
    # real failed AssumeRoleWithWebIdentity call inspected in
    # CloudTrail — a plain `repo:${var.github_repository}:ref:...`
    # pattern never matches it. var.github_oidc_subject carries that
    # exact, evidence-verified value (not a wildcard) — still scoped to
    # exactly this repository and branch, arguably more precise since
    # the IDs are immutable across a repo rename.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [var.github_oidc_subject]
    }
  }
}

data "aws_iam_policy_document" "github_deploy" {
  count = var.github_repository != "" ? 1 : 0

  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # GetAuthorizationToken does not support resource scoping
  }

  statement {
    sid = "EcrPushPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = [for repo in aws_ecr_repository.repos : repo.arn]
  }

  statement {
    sid = "EcsDeploy"
    actions = [
      "ecs:DescribeServices",
      "ecs:DescribeTaskDefinition",
      "ecs:DescribeTasks",
      "ecs:ListTasks",
      "ecs:RegisterTaskDefinition",
      "ecs:UpdateService",
      "ecs:RunTask",
    ]
    # RegisterTaskDefinition/DescribeTaskDefinition do not support
    # resource-level scoping; the rest are constrained to this cluster
    # by the condition below where applicable.
    resources = ["*"]
    condition {
      test     = "ArnEqualsIfExists"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.main.arn]
    }
  }

  statement {
    sid       = "PassExecutionRole"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.ecs_execution.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  count = var.github_repository != "" ? 1 : 0

  name               = "${local.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume[0].json
}

resource "aws_iam_role_policy" "github_deploy" {
  count = var.github_repository != "" ? 1 : 0

  name   = "${local.name_prefix}-github-deploy"
  role   = aws_iam_role.github_deploy[0].id
  policy = data.aws_iam_policy_document.github_deploy[0].json
}
