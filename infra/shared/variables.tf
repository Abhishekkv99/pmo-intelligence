variable "aws_region" {
  description = "AWS region for every shared resource"
  type        = string
  default     = "eu-west-2"
}

variable "aws_account_id" {
  description = "The only AWS account this stack may run against (ITC Sandbox PD Intelligence)"
  type        = string
  default     = "260172548683"
}

variable "project_name" {
  description = "Project name, used in resource names and tags"
  type        = string
  default     = "pmo-intelligence"
}

variable "github_repo" {
  description = "GitHub repository (owner/name) whose workflows may assume the deploy role"
  type        = string
  default     = "Abhishekkv99/pmo-intelligence"
}

# The repository issues GitHub's immutable OIDC subject, which names the owner
# and repository by id as well as by name, so a deleted and recreated repo or
# account with the same name cannot assume the role. Read it with:
#   gh api repos/<owner>/<repo>/actions/oidc/customization/sub  (sub_claim_prefix)
variable "github_oidc_subject_prefix" {
  description = "Prefix of the OIDC sub claim GitHub issues for the repository (immutable form)"
  type        = string
  default     = "repo:Abhishekkv99@28754691/pmo-intelligence@1407046286"
}

variable "github_deploy_branches" {
  description = "Branches whose workflow runs may assume the deploy role (develop deploys staging; main is added with production)"
  type        = list(string)
  default     = ["develop"]
}

# -----------------------------------------------------------------------------
# Network
# -----------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for PMO's VPC; clear of the default VPC and II's 10.0.0.0/16"
  type        = string
  default     = "10.40.0.0/16"
}

variable "az_count" {
  description = "Availability zones to spread subnets across (an ALB needs two)"
  type        = number
  default     = 2
}

# -----------------------------------------------------------------------------
# ECR
# -----------------------------------------------------------------------------

variable "ecr_untagged_expiry_days" {
  description = "Days before an untagged image expires"
  type        = number
  default     = 7
}

variable "ecr_tagged_images_kept" {
  description = "Tagged images (sha-, staging-, latest) kept per repository"
  type        = number
  default     = 10
}

# -----------------------------------------------------------------------------
# Credential expiry reminders
# -----------------------------------------------------------------------------

variable "alert_email" {
  description = "Address that receives credential expiry reminders (confirms the SNS subscription once)"
  type        = string
  default     = "Abhishek.Verma@InformationTechConsultants.com"
}

variable "credential_expiries" {
  description = "Credentials with an expiry date (YYYY-MM-DD); each gets reminders before it"
  type        = map(string)
  default = {
    # Teams Graph app certificate, thumbprint F46877044D95A517407208FF2D2FE9F382684BD3
    teams-graph-certificate = "2027-10-06"
    # Entra SSO app "PMO Intelligence" (ac99fe5f-a3bb-4299-afdc-0da9bdeab113), client secret "staging"
    entra-sso-client-secret-staging = "2027-10-08"
  }

  validation {
    condition     = alltrue([for d in values(var.credential_expiries) : can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", d))])
    error_message = "Expiry dates must be YYYY-MM-DD."
  }
}

variable "reminder_days_before" {
  description = "Days before each expiry date that a reminder is sent"
  type        = list(number)
  default     = [30, 14, 3]
}
