output "alb_dns_name" {
  description = "Public DNS name of the ALB — the site's address when no domain is configured."
  value       = aws_lb.main.dns_name
}

output "site_origin" {
  description = "The exact origin the platform is served from (drives CORS and the frontend build)."
  value       = local.site_origin
}

output "ecr_api_repository_url" {
  value = aws_ecr_repository.repos["${var.project}-api"].repository_url
}

output "ecr_web_repository_url" {
  value = aws_ecr_repository.repos["${var.project}-web"].repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "migrate_task_definition_family" {
  description = "Task-definition family for the one-off Alembic migration task."
  value       = aws_ecs_task_definition.migrate.family
}

output "private_app_subnet_ids" {
  description = "Subnets the migration one-off task must run in."
  value       = aws_subnet.private_app[*].id
}

output "ecs_security_group_id" {
  description = "Security group the migration one-off task must use."
  value       = aws_security_group.ecs.id
}

output "rds_endpoint" {
  description = "RDS endpoint (private — reachable only from ECS)."
  value       = aws_db_instance.main.address
}

output "redis_endpoint" {
  description = "ElastiCache primary endpoint (private — reachable only from ECS)."
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "ai_api_key_secret_arn" {
  description = "Secrets Manager ARN where an operator sets the real Claude API key."
  value       = aws_secretsmanager_secret.ai_api_key.arn
}

output "github_deploy_role_arn" {
  description = "IAM role GitHub Actions assumes via OIDC (empty when github_repository is unset)."
  value       = var.github_repository != "" ? aws_iam_role.github_deploy[0].arn : ""
}

output "hosted_zone_name_servers" {
  description = "NS records to configure at the registrar when create_hosted_zone = true."
  value       = local.https_enabled && var.create_hosted_zone ? aws_route53_zone.main[0].name_servers : []
}
