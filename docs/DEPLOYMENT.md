# Deployment

PMO Intelligence runs in its own AWS account, **ITC Sandbox PD Intelligence (`260172548683`)**, in **eu-west-2**. Nothing on AWS is shared with Interview Intelligence. The only link outside the account is one NS record in the `itcapp.ai` zone that delegates `pmo-intelligence-staging.itcapp.ai` to PMO's hosted zone.

> Status: Sprint 0, Phase 4 in progress. Built so far: the Terraform state bucket (`infra/bootstrap/`). The main stack (`infra/`), the database bootstrap and the first staging deploy follow.

## Access
Sign in with AWS IAM Identity Center (SSO) through the `pmo-intelligence` profile:

```ini
# ~/.aws/config
[profile pmo-intelligence]
sso_session = pmo-intelligence
sso_account_id = 260172548683
sso_role_name = AdministratorAccess
region = eu-west-2
output = json

[sso-session pmo-intelligence]
sso_start_url = https://identitycenter.amazonaws.com/ssoins-7535dbab867dda76
sso_region = eu-west-2
sso_registration_scopes = sso:account:access
```

```bash
aws sso login --profile pmo-intelligence      # opens the browser; repeat when the session expires
export AWS_PROFILE=pmo-intelligence
aws sts get-caller-identity                   # Account must be 260172548683
```

Every Terraform stack pins its provider to account `260172548683` (`allowed_account_ids`), so a run under any other profile fails before it changes anything.

## Tooling
- Terraform 1.10 or later (native S3 state locking); AWS provider `~> 6.0`.
- Each stack commits its `.terraform.lock.hcl`, with hashes for Linux and Windows. After a provider upgrade, refresh both platforms:
  ```bash
  terraform providers lock -platform=linux_amd64 -platform=windows_amd64
  ```
- State, `.terraform/`, real `*.tfvars` and saved plans are git-ignored.

## Bootstrap order
### 1. State bucket (`infra/bootstrap/`)
Creates `pmo-intelligence-tfstate-260172548683`, which holds the state of every PMO stack:
- versioning on, with overwritten state versions expiring after 90 days
- SSE-S3 encryption
- all public access blocked, bucket-owner-enforced ownership
- a bucket policy that denies any request not made over TLS
- `prevent_destroy`, so Terraform refuses to delete it

The stack creates the bucket it later stores its own state in, so the first run is two steps. They were done on 2026-10-07; a fresh checkout only needs `terraform init`.

```bash
cd infra/bootstrap

# Step 1, first time only: apply with local state (backend.tf not yet present)
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# Step 2, first time only: add backend.tf, then move the state into the bucket
terraform init -migrate-state
terraform plan                                 # must show "No changes"
```

The state lives at `s3://pmo-intelligence-tfstate-260172548683/bootstrap/terraform.tfstate`, and locking is native S3 (`use_lockfile = true`, no DynamoDB table).

**Backend block for the other stacks** (each with its own `key`):

```hcl
terraform {
  backend "s3" {
    bucket       = "pmo-intelligence-tfstate-260172548683"
    key          = "<stack>/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
```

### 2. Main stack (`infra/`)
To be written in Sprint 0 Phase 4: network, database, ECS, load balancers, DNS and certificates, ECR, secrets, IAM and the GitHub OIDC provider.

## Rollback
- **State**: every state write is a new object version. To restore one, copy an earlier version of `<stack>/terraform.tfstate` over the current one (`aws s3api list-object-versions`, then `aws s3api copy-object` with `--copy-source <bucket>/<key>?versionId=<id>`). Versions older than 90 days are gone.
