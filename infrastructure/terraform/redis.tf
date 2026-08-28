# ElastiCache Redis (Step 11) — single node, private data subnets,
# ECS-only security group, encryption at rest.
#
# Transit encryption is controlled by var.redis_transit_encryption_enabled
# (default false, preserving the original plaintext redis:// model).
# The application gained rediss:// support in Phase 9.8
# (Settings.redis_tls_enabled / Settings.redis_url) but this variable
# has not been flipped to true in any checked-in tfvars — doing so is a
# live, two-sided production change (AWS flag + REDIS_TLS_ENABLED env
# var + a new ECS deployment) requiring explicit human approval, not
# something this phase applied unattended. Compensating controls
# regardless of this setting: the node lives in subnets with no
# internet route in either direction, and its security group accepts
# port 6379 from the ECS security group only. Redis holds no
# authoritative data (docs/architecture.md §2.5: "Postgres is the
# system of record; Redis is disposable"). See
# docs/aws-deployment.md §"Redis TLS" for the exact rollout sequence
# and docs/infrastructure.md §"Known limitations".

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-redis"
  subnet_ids = aws_subnet.private_data[*].id
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${local.name_prefix}-redis"
  description          = "MarketPilot Redis - cache and pub/sub, never authoritative"

  engine         = "redis"
  engine_version = "7.1"
  node_type      = var.redis_node_type
  port           = 6379

  num_cache_clusters         = 1
  automatic_failover_enabled = false # single node — cost choice, Redis is disposable
  multi_az_enabled           = false

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = var.redis_transit_encryption_enabled # see header

  snapshot_retention_limit = 0 # nothing in Redis is worth snapshotting (cache only)

  apply_immediately = true

  tags = { Name = "${local.name_prefix}-redis" }
}
