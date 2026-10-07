# Deployment

PMO Intelligence runs in its own AWS account, **ITC Sandbox PD Intelligence (`260172548683`)**, in **eu-west-2**. Nothing on AWS is shared with Interview Intelligence. The only link outside the account is one NS record in the `itcapp.ai` zone that delegates `pmo-intelligence-staging.itcapp.ai` to PMO's hosted zone.

> Status: Sprint 0, Phase 4 in progress. Applied on 2026-10-07: the state bucket (`infra/bootstrap/`), the shared stack (`infra/shared/`, 23 resources) and staging (`infra/environments/staging/`, 52 resources including the hosted zone). The NS delegation is in place, and `https://pmo-intelligence-staging.itcapp.ai` serves a valid certificate. It answers 503 until the database bootstrap and the first image deploy. Still to do: the database bootstrap, the GitHub variables, the app secret values and the first staging deploy.

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

### 2. Shared stack (`infra/shared/`, state key `shared/`)
One copy for every environment:

| Resource | Notes |
|----------|-------|
| VPC `10.40.0.0/16` | 2 public and 2 private /20 subnets across two AZs; internet gateway; the default security group stripped of rules |
| Route tables | Public: default route to the internet gateway. Private: no internet route (RDS only) |
| S3 gateway endpoint | On both route tables |
| ECR `pmo-intelligence-backend`, `pmo-intelligence-frontend` | Scan on push; untagged images expire after 7 days; the last 10 `sha-`/`staging-`/`latest` images are kept |
| ECS cluster `pmo-intelligence` | Each environment adds its services |
| GitHub OIDC provider and role `pmo-intelligence-github-deploy` | Only runs on `develop` of `Abhishekkv99/pmo-intelligence` can assume it. It can push to the two repositories and update services in the cluster |
| IAM policy `pmo-intelligence-deny-deletion` | Not attached by Terraform; attach it to IAM users or groups that must never delete PMO resources |

```bash
cd infra/shared
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

### 3. Staging (`infra/environments/staging/`, state key `staging/`)
Uses `infra/modules/environment/` and reads the shared stack's outputs from its state. It creates:
- the hosted zone `pmo-intelligence-staging.itcapp.ai`, its certificate and alias record, and the SES domain identity with its DKIM records
- the ALB: HTTPS, `/api/*` to the backend, plain HTTP redirected
- security groups: ALB, backend, frontend, RDS (backend only)
- RDS `pmo-intelligence-staging`: PostgreSQL 16, `db.t4g.micro`, private, master password managed by RDS
- the app secret `pmo-intelligence/staging/app`
- log groups, the media bucket, IAM roles, task definitions and services

The certificate can only validate once `itcapp.ai` delegates the hostname to the new zone, so the first apply is in two steps:

```bash
cd infra/environments/staging
cp terraform.tfvars.example terraform.tfvars    # set bootstrap_admin_emails
terraform init

# Step 1: the hosted zone alone, then read its name servers
terraform apply -target=module.environment.aws_route53_zone.this
terraform output hosted_zone_name_servers
```

Whoever manages the `itcapp.ai` zone adds one record:

| Name | Type | Value |
|------|------|-------|
| `pmo-intelligence-staging.itcapp.ai` | NS | the four name servers from the output |

Check it resolves (`nslookup -type=NS pmo-intelligence-staging.itcapp.ai`), then:

```bash
# Step 2: everything else (waits for the certificate to be issued)
terraform plan -out=tfplan
terraform apply tfplan
terraform output github_variables
```

**After the first apply**:
1. **GitHub variables.** Set the six repository variables from `github_variables` (Settings > Secrets and variables > Actions > Variables). From then on, a push to `develop` that passes CI deploys to staging.
2. **App secret.** Replace the `CHANGE_ME` values in `pmo-intelligence/staging/app` (Azure OpenAI, AssemblyAI, Entra) with `aws secretsmanager put-secret-value`. Values never go in chat or in git; Terraform ignores later changes to the secret's value. `DATABASE_URL` is written by the database bootstrap (`scripts/db_bootstrap.py`, still to be written in Phase 4).
3. **Images.** The services run the `staging-latest` tag. Until CI has pushed one, ECS keeps retrying the task.

**Protection**: the RDS instance (deletion protection, final snapshot), the media bucket, the app secret and the hosted zone carry `prevent_destroy`. Recreating the zone would change its name servers and break the delegation. Everything else can be destroyed and recreated.

## Rollback
- **State**: every state write is a new object version. To restore one, copy an earlier version of `<stack>/terraform.tfstate` over the current one (`aws s3api list-object-versions`, then `aws s3api copy-object` with `--copy-source <bucket>/<key>?versionId=<id>`). Versions older than 90 days are gone.
