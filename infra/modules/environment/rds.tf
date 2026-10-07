# -----------------------------------------------------------------------------
# RDS PostgreSQL 16 for this environment, in the private subnets. The master
# password is managed by RDS in its own Secrets Manager secret and never enters
# Terraform state. The app connects as pmo_app, which the db bootstrap creates
# (with the vector extension) and writes into the app secret.
# -----------------------------------------------------------------------------

resource "aws_db_subnet_group" "this" {
  name        = local.name
  description = "Private subnets for ${local.name}"
  subnet_ids  = var.private_subnet_ids
}

resource "aws_db_instance" "this" {
  identifier = local.name

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name                     = var.db_name
  username                    = var.db_master_username
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = false
  port                   = 5432

  backup_retention_period    = var.db_backup_retention_days
  backup_window              = "03:00-04:00"
  maintenance_window         = "mon:04:00-mon:05:00"
  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true

  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name}-final"

  performance_insights_enabled = false

  tags = {
    Name = local.name
  }

  lifecycle {
    prevent_destroy = true
  }
}
