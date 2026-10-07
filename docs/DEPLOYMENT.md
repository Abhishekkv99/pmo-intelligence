# Deployment

PMO Intelligence runs in its own AWS account, **ITC Sandbox PD Intelligence (`260172548683`)**, in **eu-west-2**. Nothing on AWS is shared with Interview Intelligence. The only link outside the account is one NS record in the `itcapp.ai` zone that delegates `pmo-intelligence-staging.itcapp.ai` to PMO's hosted zone.

> Status: Sprint 0, Phase 4 in progress. Applied on 2026-10-07: the state bucket (`infra/bootstrap/`), the shared stack (`infra/shared/`, 23 resources) and staging (`infra/environments/staging/`, 52 resources including the hosted zone). The NS delegation is in place, and `https://pmo-intelligence-staging.itcapp.ai` serves a valid certificate. The GitHub variables are set; the database bootstrap has run (`pmo_app`); the backend (deployed by CI) and the frontend (first image pushed by hand, later ones by CI) are healthy: `/api/v1/health` answers 200. Still to do: the app secret's Azure OpenAI, AssemblyAI and Entra values, and the credential-expiry reminders.

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
| GitHub OIDC provider and role `pmo-intelligence-github-deploy` | Only runs on `develop` of `Abhishekkv99/pmo-intelligence` can assume it. The trust condition uses the repository's immutable OIDC subject `repo:Abhishekkv99@28754691/pmo-intelligence@1407046286:ref:refs/heads/develop` (read with `gh api repos/<owner>/<repo>/actions/oidc/customization/sub`). It can push to the two repositories and update services in the cluster |
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
2. **App secret.** Replace the `CHANGE_ME` values in `pmo-intelligence/staging/app` (Azure OpenAI, AssemblyAI, Entra) with `aws secretsmanager put-secret-value`. Values never go in chat or in git; Terraform ignores later changes to the secret's value. `DATABASE_URL` is written by the database bootstrap (section 4).
3. **Images.** The services run the `staging-latest` tag. Until one exists, ECS keeps retrying the task. CI deploys only the side that changed since the previous commit, so the first image of an unchanged side is pushed by hand. On Windows, `docker login` to ECR fails with the credential store ("The stub received bad data"), so use a temporary `DOCKER_CONFIG` whose `config.json` holds an `auths` entry for the registry, base64 of `AWS:<aws ecr get-login-password>`.

**Protection**: the RDS instance (deletion protection, final snapshot), the media bucket, the app secret and the hosted zone carry `prevent_destroy`. Recreating the zone would change its name servers and break the delegation. Everything else can be destroyed and recreated.

### 4. Database bootstrap (`make db-bootstrap ENV=staging`)
RDS is private, with no bastion or ECS Exec, so the bootstrap runs as a one-off ECS task inside the VPC. The task definition is `pmo-intelligence-<env>-db-bootstrap`: the backend image running `python -m app.cli.db_bootstrap`, with the backend security group, which RDS admits. It connects as the RDS master user and:
1. creates the `vector` extension;
2. creates the `pmo_app` login with a random password (an existing login keeps its password);
3. makes `pmo_app` the owner of the database and its `public` schema, so the migration init container can run DDL with the same URL;
4. checks the new login connects, then writes `DATABASE_URL` into `pmo-intelligence/<env>/app`, keeping every other key.

```bash
export AWS_PROFILE=pmo-intelligence
make db-bootstrap ENV=staging                             # first run, or any time to re-check
make db-bootstrap ENV=staging ARGS=--rotate-password      # new password; redeploy the backend afterwards
```

`scripts/db-bootstrap.sh` reads the cluster, task definition, subnets and security group from the environment's Terraform outputs. It starts the task, waits for it to stop, prints its log and exits with the task's exit code.

- **Needs the backend image** (`staging-latest`) in ECR, because the task runs that image.
- **Permissions**: only the bootstrap's own roles can read the RDS master secret (execution role) and write the app secret (task role). The app's roles can do neither.
- **No password is ever printed.** If `pmo_app` exists but the secret has no `DATABASE_URL` (its password is unknown), the task exits 1 and asks for `--rotate-password`.
- **After it succeeds**, redeploy the backend (`aws ecs update-service --cluster pmo-intelligence --service pmo-intelligence-staging-backend --force-new-deployment`), so its migration init container runs with the new URL.

### 5. Azure OpenAI (`infra/azure/`, state key `azure/`)
PMO's models run in its own Azure resource group and Azure OpenAI resource, in subscription `3a72be92-287b-4f1e-840a-5e3e71100139`. Nothing is shared with Interview Intelligence's `rg-interview-intelligence`.

| Resource | Notes |
|----------|-------|
| Resource group `rg-pmo-intelligence-swc` (Sweden Central) | The cost-tracking scope; tagged `project=pmo-intelligence` |
| Azure OpenAI `oai-pmo-intelligence-swc` (S0) | Endpoint `https://oai-pmo-intelligence-swc.openai.azure.com/`; API-key auth (the ECS tasks call it over the internet) |
| Deployment `gpt-5.4-mini-staging` | `gpt-5.4-mini` 2026-03-17, **Data Zone Standard**, 50K TPM, no automatic version upgrades |
| Deployment `text-embedding-3-small-staging` | `text-embedding-3-small` v1 (1536 dimensions), Data Zone Standard, 50K TPM |

- **Data Zone Standard** keeps prompt processing inside the EU data zone. The prompts carry workers' transcripts (UK GDPR). In UK South `gpt-5.4-mini` is only available as Global Standard, which processes anywhere.
- **Environments** are separate deployments on the one resource, `<model>-<env>`, with capacity per environment in `var.environments`. They share the resource's keys. Prod adds a `prod` entry at product Phase 5.
- **Quota** is per subscription, region, model and deployment type (200K TPM for `gpt-5.4-mini` Data Zone in Sweden Central on 2026-10-08), so other Data Zone deployments of the same model in this subscription and region share it.

```bash
az login                                   # provider auth
export AWS_PROFILE=pmo-intelligence        # the state lives in the S3 state bucket
cd infra/azure
terraform init
terraform plan -out=tfplan
terraform apply tfplan
terraform output                           # endpoint and deployment names for the app secret
az cognitiveservices account keys list -g rg-pmo-intelligence-swc -n oai-pmo-intelligence-swc   # API key (never in git or chat)
```

The app secret takes `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` (`gpt-5.4-mini-staging`) and `AZURE_EMBEDDING_DEPLOYMENT` (`text-embedding-3-small-staging`). AssemblyAI is not on Azure; PMO uses its own AssemblyAI API key, so transcription cost is separate as well.

## Rollback
- **State**: every state write is a new object version. To restore one, copy an earlier version of `<stack>/terraform.tfstate` over the current one (`aws s3api list-object-versions`, then `aws s3api copy-object` with `--copy-source <bucket>/<key>?versionId=<id>`). Versions older than 90 days are gone.
