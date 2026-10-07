# Added after the first apply created the bucket; `terraform init -migrate-state`
# then moved this stack's local state here.
terraform {
  backend "s3" {
    bucket       = "pmo-intelligence-tfstate-260172548683"
    key          = "bootstrap/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
