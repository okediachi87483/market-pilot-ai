# RDS PostgreSQL (Step 10) — private data subnets, no public access,
# encrypted storage, automated backups, ECS-only security group. The
# application's Alembic migrations remain the schema authority (run as
# a one-off ECS task — see docs/aws-deployment.md §"Migrations"); no
# parameter group is created because the application needs no
# non-default engine parameters.

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db"
  subnet_ids = aws_subnet.private_data[*].id

  tags = { Name = "${local.name_prefix}-db-subnets" }
}

resource "aws_db_instance" "main" {
  identifier = "${local.name_prefix}-postgres"

  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result
  port     = 5432

  allocated_storage = var.db_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = false # deliberate cost choice — docs/infrastructure.md §"Cost"

  backup_retention_period = var.db_backup_retention_days
  deletion_protection     = var.db_deletion_protection
  skip_final_snapshot     = var.db_skip_final_snapshot
  final_snapshot_identifier = (
    var.db_skip_final_snapshot ? null : "${local.name_prefix}-final"
  )

  auto_minor_version_upgrade = true
  apply_immediately          = true

  tags = { Name = "${local.name_prefix}-postgres" }
}
