# Staging: develop deploys here (CI pushes the staging-latest image tag)

data "terraform_remote_state" "shared" {
  backend = "s3"

  config = {
    bucket = "pmo-intelligence-tfstate-260172548683"
    key    = "shared/terraform.tfstate"
    region = "eu-west-2"
  }
}

locals {
  shared = data.terraform_remote_state.shared.outputs
}

module "environment" {
  source = "../../modules/environment"

  project_name   = var.project_name
  environment    = "staging"
  short_name     = "pmo-staging"
  hostname       = "pmo-intelligence-staging.itcapp.ai"
  aws_region     = var.aws_region
  aws_account_id = var.aws_account_id

  vpc_id              = local.shared.vpc_id
  public_subnet_ids   = local.shared.public_subnet_ids
  private_subnet_ids  = local.shared.private_subnet_ids
  ecs_cluster_arn     = local.shared.ecs_cluster_arn
  ecr_repository_urls = local.shared.ecr_repository_urls

  image_tag              = "staging-latest"
  processing_concurrency = 1
  # Catalog only; the bucket policy on the recordings bucket grants this
  # environment's task role (docs/DEPLOYMENT.md).
  recordings_scan_enabled = true
  bootstrap_admin_emails  = var.bootstrap_admin_emails

  db_instance_class = "db.t4g.micro"
}
