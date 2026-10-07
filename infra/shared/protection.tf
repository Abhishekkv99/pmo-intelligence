# -----------------------------------------------------------------------------
# Deny-deletion policy (from II's protection.tf). Not attached to anything by
# Terraform: attach it to an IAM user or group that should never delete PMO
# resources. IAM Identity Center roles cannot carry it; for them the same
# statements would go into a permission set.
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "deny_deletion" {
  statement {
    sid    = "DenyTaggedResourceDeletion"
    effect = "Deny"
    actions = [
      "ec2:DeleteSecurityGroup",
      "ecs:DeleteCluster",
      "ecs:DeleteService",
      "elasticloadbalancing:DeleteListener",
      "elasticloadbalancing:DeleteLoadBalancer",
      "elasticloadbalancing:DeleteTargetGroup",
      "rds:DeleteDBInstance",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Project"
      values   = [var.project_name]
    }
  }

  statement {
    sid       = "DenyBucketDeletion"
    effect    = "Deny"
    actions   = ["s3:DeleteBucket", "s3:DeleteBucketPolicy"]
    resources = ["arn:aws:s3:::${var.project_name}-*"]
  }

  statement {
    sid       = "DenyRepositoryDeletion"
    effect    = "Deny"
    actions   = ["ecr:DeleteRepository", "ecr:BatchDeleteImage"]
    resources = [for repo in aws_ecr_repository.app : repo.arn]
  }

  statement {
    sid       = "DenySecretDeletion"
    effect    = "Deny"
    actions   = ["secretsmanager:DeleteSecret"]
    resources = ["arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/*"]
  }

  statement {
    sid       = "DenyLogGroupDeletion"
    effect    = "Deny"
    actions   = ["logs:DeleteLogGroup"]
    resources = ["arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/ecs/${var.project_name}*"]
  }
}

resource "aws_iam_policy" "deny_deletion" {
  name        = "${var.project_name}-deny-deletion"
  description = "Denies deleting ${var.project_name} infrastructure; attach to IAM users or groups"
  policy      = data.aws_iam_policy_document.deny_deletion.json
}
