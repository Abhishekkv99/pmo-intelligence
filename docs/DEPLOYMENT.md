# Deployment

PMO Intelligence runs in its own AWS account, **ITC Sandbox PD Intelligence (`260172548683`)**, in **eu-west-2**. Nothing on AWS is shared with Interview Intelligence. The only link outside the account is one NS record in the `itcapp.ai` zone that delegates `pmo-intelligence-staging.itcapp.ai` to PMO's hosted zone.

> Status: Sprint 2 Phase 1 (2026-10-09): the backend target group's deregistration delay is 60 s (was AWS's default 300 s; applied in place, staging still 61 managed resources by `terraform state list`), so a backend deploy hands processing over in about 2½ minutes ("Redeploying without a change"). Sprint 1 complete (2026-10-09): migrations 002–005 applied on staging by the CI deploys (005, signals, issues and actions, by CI run 37910393869; the session page by CI run 37930365598; resource counts re-read with `terraform state list` 2026-10-09: 7, 34 and 61, unchanged; the session pipeline uses the `SESSION_*` defaults, so no setting was added to the task definition); the manual redeploy is in `ci.yml` ("Redeploying without a change"); the backend reads the PMO recordings folder (section 9: bucket policy on the main account's bucket, task-role statements and env vars by Terraform, applied 2026-10-09; staging still 61 managed resources, the task definition being replaced). Sprint 0 (complete 2026-10-08) applied: the state bucket (`infra/bootstrap/`, 7 resources), the shared stack (`infra/shared/`, 34: network, ECR, ECS cluster, GitHub OIDC role, deny-deletion policy, credential expiry reminders), staging (`infra/environments/staging/`, 61: the environment module with the database bootstrap and admin-cli task definitions) and PMO's Azure OpenAI (`infra/azure/`, 5). Counts are managed resources in each stack's state on 2026-10-08. The NS delegation is in place and `https://pmo-intelligence-staging.itcapp.ai` serves a valid certificate. The staging secret holds every value (database URL from the bootstrap, Azure OpenAI, AssemblyAI, the Entra SSO app); sign-in works for members of the tenant with a role (section 8). Production is applied at product Phase 5.

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
2. **App secret.** Replace the `CHANGE_ME` values in `pmo-intelligence/staging/app` with `aws secretsmanager put-secret-value`. Values never go in chat or in git; Terraform ignores later changes to the secret's value. The keys (`app_secret_keys` in `infra/modules/environment/secrets.tf`):

   | Key | Set by | Value |
   |-----|--------|-------|
   | `DATABASE_URL` | Database bootstrap (section 4) | The `pmo_app` connection URL |
   | `SECRET_KEY` | Terraform (random, 64 characters) | Signs access tokens |
   | `ASSEMBLYAI_API_KEY` | By hand | PMO's own AssemblyAI key |
   | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` | By hand | From `infra/azure/` (section 5) |
   | `AZURE_OPENAI_DEPLOYMENT`, `AZURE_EMBEDDING_DEPLOYMENT` | By hand | `<model>-<env>` deployment names (section 5) |
   | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` | By hand | The Entra SSO app registration |
   | `AZURE_ALLOWED_TENANT_IDS` | By hand, optional | Comma-separated tenant ids allowed to sign in besides the home tenant (`AZURE_TENANT_ID`, always allowed); empty by default |

   To change one key and keep the others, read the secret, change that key in the JSON, and write the whole object back. A running task reads the secret only at start, so redeploy the backend afterwards.
3. **Images.** The services run the `staging-latest` tag. Until one exists, ECS keeps retrying the task. CI deploys only the side that changed since the previous commit, so push the first image of an unchanged side with a manual run: `gh workflow run ci.yml --ref develop -f target=both` (see "Redeploying without a change"). Before Sprint 1 the first images were built by hand. If an image ever has to be built by hand again, follow the infrastructure and tooling rules: on Windows a temporary `DOCKER_CONFIG` for the ECR login, `MSYS_NO_PATHCONV=1` with CI's build argument (`--build-arg NEXT_PUBLIC_API_URL=/api/v1`, `--platform linux/amd64`), and a check of the bundle before pushing (`docker run --rm --entrypoint sh <image> -c "grep -rhoE '.{20}api/v1' .next/static/chunks"`). Without the build argument fix, Git Bash turns `/api/v1` into `C:/Program Files/Git/api/v1` (staging sign-in failed this way until 2026-10-08).

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

**Resource group policy.** The subscription policy "Restrict RG Creation to Managed Service Patterns" denies creating *or updating* any resource group whose name is not a managed-service pattern (`databricks-rg-*`, `MC_*`, and so on). The policy applies to Owners too.
- Terraform gives `rg-pmo-intelligence-swc` its own permanent exemption, scoped to that one group, so later applies can update it.
- The first creation needs a short subscription-wide exemption, used **only with the policy owner's agreement**, removed straight after:

```bash
# Waiver for this one creation, expiring in two hours
az policy exemption create --name pmo-intelligence-rg-create-once   --scope /subscriptions/3a72be92-287b-4f1e-840a-5e3e71100139   --policy-assignment /subscriptions/3a72be92-287b-4f1e-840a-5e3e71100139/providers/Microsoft.Authorization/policyAssignments/110d1e5c334d45929d8e2412   --exemption-category Waiver   --expires-on "$(date -u -d '+2 hours' +%Y-%m-%dT%H:%M:%SZ)"   --display-name "PMO Intelligence: create the project resource group (one-off)"

terraform apply tfplan   # creates the group, its own exemption, the Azure OpenAI resource and deployments

az policy exemption delete --name pmo-intelligence-rg-create-once --scope /subscriptions/3a72be92-287b-4f1e-840a-5e3e71100139
```

Azure writes need an MFA-backed `az login`. If a write answers `RequestDisallowedByAzure ... without authenticating through MFA`, sign in again with the claims challenge from the 401 (`az login --use-device-code --claims-challenge <value> ...`).

The app secret takes `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` (`gpt-5.4-mini-staging`) and `AZURE_EMBEDDING_DEPLOYMENT` (`text-embedding-3-small-staging`). AssemblyAI is not on Azure; PMO uses its own AssemblyAI API key, so transcription cost is separate as well.

### 6. Credential expiry reminders (`infra/shared/expiry_reminders.tf`)
Credentials that expire are listed in `credential_expiries` in `infra/shared/variables.tf`, as name → expiry date. For each one, EventBridge Scheduler sends an email through the SNS topic `pmo-intelligence-credential-expiry` **30, 14 and 3 days before**, at 09:00 Europe/London. Reminders whose time has already passed are skipped.

| Credential | Expires | Source |
|------------|---------|--------|
| `teams-graph-certificate` | 2027-10-06 | Teams Graph app certificate, thumbprint `F46877044D95A517407208FF2D2FE9F382684BD3` (`docs/integrations/TEAMS-GRAPH-SETUP.md`) |
| `entra-sso-client-secret-staging` | 2027-10-08 | Client secret `staging` of the Entra SSO app "PMO Intelligence" (section 7) |

- **Recipient**: `alert_email` (`Abhishek.Verma@InformationTechConsultants.com`). AWS sends a confirmation email after the first apply, and reminders arrive only once the link in it is clicked.
- **Add or renew a credential**: put its name and new date in `credential_expiries`, then `terraform plan` and `apply` in `infra/shared/`. The old schedules are replaced.
- Credentials with no expiry need no entry: the Azure OpenAI and AssemblyAI keys, the RDS master password (rotated by RDS), the ACM certificate (renewed by ACM), and deploys (OIDC, no stored key).

### 7. Entra SSO app (`scripts/entra/Register-SsoApp.ps1`)
One app registration, **PMO Intelligence** (client id `ac99fe5f-a3bb-4299-afdc-0da9bdeab113`), serves every environment, in the Information Tech Consultants tenant (`2b32b1fa-7899-482e-a6de-be99c0ff5516`).

| Setting | Value |
|---------|-------|
| Audience | Single tenant (`AzureADMyOrg`); `AZURE_ALLOWED_TENANT_IDS` stays empty, so the backend uses the tenant id as the authority |
| Redirect URIs (Web) | `http://localhost:3000/auth/callback/microsoft`, `http://localhost:3100/auth/callback/microsoft`, `https://pmo-intelligence-staging.itcapp.ai/auth/callback/microsoft`; prod's is added at product Phase 5 |
| Platform | **Web, not SPA**: the browser does PKCE, but the backend redeems the code with the client secret, and Entra refuses a server-side redemption for an SPA redirect |
| Scopes | Delegated Microsoft Graph `openid`, `email`, `profile`, `offline_access` on the registration. Since Sprint 1 sign-in requests only `openid email profile`: no Microsoft refresh token is issued or stored. `offline_access` stays on the registration, unused, so existing consents are untouched |
| Optional claim | `acct` in the ID token: `0` for a member of the tenant, `1` for a guest. The backend refuses any token without `acct` = 0, so the claim must be on the app **before** a backend that checks it is deployed, or nobody can sign in |
| Assignment required | **Off.** Entra lets any account in the tenant through, consenting for itself to the four scopes (the tenant's user consent policy, `microsoft-user-default-recommended`, allows them); the backend then admits only members with a role (section 8). Turning assignment on (`-RequireAssignment`) makes Entra demand **admin consent** for the app regardless of the user consent policy, so nobody signs in until a tenant administrator grants it ("Need admin approval", seen on 2026-10-08) |
| Client secrets | One per environment, named after it (`staging`, expires 2027-10-08), 12 months each |

```powershell
az login                                   # as yourself; the tenant lets users register apps
aws sso login --profile pmo-intelligence
powershell -ExecutionPolicy Bypass -File scripts\entra\Register-SsoApp.ps1      # staging (defaults)
```

The script is safe to re-run: it finds the app by exact name, adds redirect URIs without removing any, sets assignment required from `-RequireAssignment` (off unless given), and skips the secret when the environment already has one. When it creates a secret, it writes `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` and `AZURE_TENANT_ID` into `pmo-intelligence/<env>/app`, keeping the other keys. The value is never printed.

- **After a new secret**: add `entra-sso-client-secret-<env>` with the printed expiry to `credential_expiries` (section 6) and apply `infra/shared/`; redeploy the backend.
- **Rotate**: `-RotateSecret` adds a new secret and writes it, keeping the old one so running tasks still sign in. Redeploy the backend, then delete the old secret with the `az ad app credential delete` command the script prints.
- **Prod (product Phase 5)**: `-Environment prod -RedirectUris https://pmo-intelligence.itcapp.ai/auth/callback/microsoft`.
- **Bootstrap admins**: `bootstrap_admin_emails` in each environment's git-ignored `terraform.tfvars` (copy `terraform.tfvars.example`); staging has `Abhishek.Verma@InformationTechConsultants.com`. Changing it replaces the backend task definition and redeploys.

### 8. Granting roles (Admin page, or `make user-role`)
Only an active member of the tenant whose user row holds a role can sign in. Guests are always refused. A PMO manager or admin grants, changes and removes roles on the Admin page, "Users and roles" tab. `make user-role` stays as the fallback for when nobody who can open that page can sign in (for example the first user of a new environment, beside the bootstrap list): a one-off ECS task, `<env>-admin-cli`, the backend image with the app's `DATABASE_URL`, run in the backend's subnets and security group.

```bash
export AWS_PROFILE=pmo-intelligence
make user-role ENV=staging EMAIL=jane.doe@informationtechconsultants.com ROLE=sme   # grant or change
make user-role ENV=staging EMAIL=jane.doe@informationtechconsultants.com ROLE=none  # remove
make user-role ENV=staging ARGS=--list                                              # every user and role
```

- **Roles**: `pmo_manager`, `sme`, `tech_lead`, `ps`, `admin` (`backend/app/models/enums.py`).
- **A new person**: granting a role to an address that has never signed in creates the user by email. Their first Microsoft sign-in finds the row by email, links their Entra account and takes their name from the token. Use the address their token carries (their sign-in name, normally `first.last@informationtechconsultants.com`).
- **Removing a role** ends every session the user has at once (their refresh tokens are revoked), and any page they have open stops working within 15 minutes. The row stays, without a role, so the role can be granted again.
- **The last active PMO manager keeps the role**: the page and `make user-role` both refuse to remove or change it (the task exits 2 with the reason). Make someone else a PMO manager first.
- **Bootstrap admins** (`bootstrap_admin_emails` in `terraform.tfvars`) are `pmo_manager` regardless: removing their role here lasts only until their next sign-in or the next deploy. Take them off the list as well.
- **Who was refused**: every refused sign-in is a WARNING in the backend log group, `Sign-in refused: ...`, with the account it was for.
- `scripts/user-role.sh` reads the cluster, task definition, subnets and security group from the environment's Terraform outputs, accepts only a plain email address and a known role, waits for the task, prints its own log stream and exits with the task's exit code.
- **Needs the backend image** with `app/cli/user_role.py` (`staging-latest`).

### 9. PMO recordings folder (bucket policy, then Terraform)
The backend reads the PMO call recordings from `s3://nextcloud-talk-recordings-itc/recordings/pmo/`, a bucket in the **main ITC account (`430006376054`)**. Access across accounts needs both sides:

1. **Bucket policy** (main account). Applied 2026-10-09 with the user's approval. Allow only: list the bucket under the prefix, and read objects under it, for PMO's staging task role and nothing else. The bucket's object ownership is `BucketOwnerEnforced`, so the policy covers every object; the objects use SSE-S3, so no KMS grant is needed. A policy of Allow statements does not narrow the main account's own access.

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "PmoStagingListRecordings",
         "Effect": "Allow",
         "Principal": { "AWS": "arn:aws:iam::260172548683:role/pmo-intelligence-staging-ecs-task" },
         "Action": "s3:ListBucket",
         "Resource": "arn:aws:s3:::nextcloud-talk-recordings-itc",
         "Condition": { "StringLike": { "s3:prefix": "recordings/pmo/*" } }
       },
       {
         "Sid": "PmoStagingReadRecordings",
         "Effect": "Allow",
         "Principal": { "AWS": "arn:aws:iam::260172548683:role/pmo-intelligence-staging-ecs-task" },
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::nextcloud-talk-recordings-itc/recordings/pmo/*"
       }
     ]
   }
   ```

   ```bash
   # Main-account login (the default profile). Check first: put-bucket-policy
   # REPLACES any existing policy, so go on only if this says none exists.
   MSYS_NO_PATHCONV=1 aws s3api get-bucket-policy --bucket nextcloud-talk-recordings-itc
   MSYS_NO_PATHCONV=1 aws s3api put-bucket-policy --bucket nextcloud-talk-recordings-itc --policy file://recordings-bucket-policy.json
   MSYS_NO_PATHCONV=1 aws s3api get-bucket-policy --bucket nextcloud-talk-recordings-itc --query Policy --output text
   ```

   **Never delete or overwrite anything in the main account.** If a policy already exists when this is next needed (production adds its own role), merge the new statements into the existing document by hand and have the account owner apply it; removing the policy is the account owner's decision alone.
2. **Terraform** (PMO account, `infra/modules/environment/iam.tf` and `ecs.tf`). The task role gets the matching `ListRecordingsFolder` and `ReadRecordings` statements (variables `recordings_source_bucket`, `recordings_source_prefix`), and the backend gets `RECORDINGS_SOURCE_BUCKET`, `RECORDINGS_SOURCE_PREFIX` and `RECORDINGS_SCAN_ENABLED` (`recordings_scan_enabled`, true for staging). Applied 2026-10-09: the backend task definition replaced, the service and the task policy updated in place.

Apply the bucket policy first: the redeploy runs a scan at startup, which fails with AccessDenied until the policy exists (the next pass, 15 minutes later, would then succeed).

**Check**: the backend log shows `Recordings scan <id>: N folders (...), M recordings (...)` within a few minutes of the new task taking over processing. The first staging scan (2026-10-09) found 49 of 310 folders with calls on or after `RECORDINGS_EARLIEST_DATE` (2026-07-24) and cataloged 208 recordings; none matched, as the staging register was still empty.

## Redeploying without a change
To rebuild and redeploy one side of staging from the head of `develop` (for example after a secret value changed, or to replace a bad image), run the CI workflow by hand:

```bash
gh workflow run ci.yml --ref develop -f target=frontend    # target: backend, frontend or both
```

It runs that side's checks and e2e, then deploys as a push does. Redeploying the backend restarts processing. Prefer this to building and pushing an image by hand.

**What a backend deploy does to processing**: ECS starts the new task, waits for it to pass the load balancer's health check, then drains the old task's connections for the target group's deregistration delay (60 s) before signalling it. Until the old task stops, it keeps processing ownership and the new task logs "Waiting for processing ownership". The old task then logs "Processing queue stopped" and "Released processing ownership", and the new one "Took processing ownership after Ns": expect about 2½ minutes (150 s on the deploy of fd2cd77, 2026-10-09; 370–390 s with the old 300 s drain). A job running on the old task when it stops is failed by the new owner's takeover sweep, for retry. An upload still in progress when the drain ends is cut and has to be sent again.

## Rollback
- **A bad app deploy**: every deploy pushes `sha-<full commit sha>` next to `staging-latest`, and the services always run `staging-latest`. Point the tag back at a good image, then fix `develop`:
  ```bash
  export AWS_PROFILE=pmo-intelligence AWS_REGION=eu-west-2
  repo=pmo-intelligence-backend                      # or pmo-intelligence-frontend
  good=sha-<commit of the last good deploy>
  manifest="$(aws ecr batch-get-image --repository-name "$repo" --image-ids imageTag="$good" \
    --query 'images[0].imageManifest' --output text)"
  aws ecr put-image --repository-name "$repo" --image-tag staging-latest --image-manifest "$manifest"
  aws ecs update-service --cluster pmo-intelligence --service pmo-intelligence-staging-backend --force-new-deployment   # or -frontend
  ```
  Then `git revert` the bad commit on `develop` and push, so the next CI deploy does not bring it back.
- **Migrations do not roll back with the image.** The backend's `migration` container runs `alembic upgrade head` before the app starts. An older image does not know a revision added after it, so its migration container fails and the backend never starts. If the bad deploy added a migration, first run `alembic downgrade <last good revision>` with the *newer* image: a one-off task from the backend task definition, overriding the `migration` container's command, in the same subnets and security group the database bootstrap uses (section 4). Once the `migration` container has exited 0, stop the task (`aws ecs stop-task`), because the `backend` container then starts and would keep running outside the service. Then retag.
- **State**: every state write is a new object version. To restore one, copy an earlier version of `<stack>/terraform.tfstate` over the current one (`aws s3api list-object-versions`, then `aws s3api copy-object` with `--copy-source <bucket>/<key>?versionId=<id>`). Versions older than 90 days are gone.
