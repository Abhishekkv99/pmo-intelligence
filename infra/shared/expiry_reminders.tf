# -----------------------------------------------------------------------------
# Credential expiry reminders. Each credential in var.credential_expiries gets
# one-time EventBridge Scheduler schedules ahead of its expiry date (09:00
# Europe/London) that email the SNS topic's subscribers. Renewing a credential
# means updating its date here and applying. Reminders already in the past are
# skipped.
# -----------------------------------------------------------------------------

locals {
  reminders = {
    for pair in setproduct(keys(var.credential_expiries), var.reminder_days_before) :
    "${pair[0]}-${pair[1]}d" => {
      credential = pair[0]
      expires_on = var.credential_expiries[pair[0]]
      days       = pair[1]
      # RFC 3339 instant, used for the past check and to build the at() time
      at = timeadd("${var.credential_expiries[pair[0]]}T09:00:00Z", "-${pair[1] * 24}h")
    }
  }

  upcoming_reminders = {
    for k, r in local.reminders : k => r if timecmp(r.at, plantimestamp()) > 0
  }
}

resource "aws_sns_topic" "credential_expiry" {
  name = "${var.project_name}-credential-expiry"
}

# The address must confirm the subscription from the email AWS sends
resource "aws_sns_topic_subscription" "credential_expiry_email" {
  topic_arn = aws_sns_topic.credential_expiry.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }
}

resource "aws_iam_role" "credential_expiry_scheduler" {
  name               = "${var.project_name}-credential-expiry-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
}

data "aws_iam_policy_document" "credential_expiry_publish" {
  statement {
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.credential_expiry.arn]
  }
}

resource "aws_iam_role_policy" "credential_expiry_publish" {
  name   = "${var.project_name}-credential-expiry-publish"
  role   = aws_iam_role.credential_expiry_scheduler.id
  policy = data.aws_iam_policy_document.credential_expiry_publish.json
}

resource "aws_scheduler_schedule_group" "credential_expiry" {
  name = "${var.project_name}-credential-expiry"
}

resource "aws_scheduler_schedule" "credential_expiry" {
  for_each = local.upcoming_reminders

  name                         = each.key
  group_name                   = aws_scheduler_schedule_group.credential_expiry.name
  schedule_expression          = "at(${formatdate("YYYY-MM-DD'T'hh:mm:ss", each.value.at)})"
  schedule_expression_timezone = "Europe/London"

  flexible_time_window {
    mode = "OFF"
  }

  # Universal target: SNS Publish with a subject line
  target {
    arn      = "arn:aws:scheduler:::aws-sdk:sns:publish"
    role_arn = aws_iam_role.credential_expiry_scheduler.arn

    input = jsonencode({
      TopicArn = aws_sns_topic.credential_expiry.arn
      Subject  = "PMO Intelligence: ${each.value.credential} expires in ${each.value.days} days"
      Message  = <<-EOT
        The credential "${each.value.credential}" for PMO Intelligence expires on ${each.value.expires_on} (${each.value.days} days from today).

        Renew it before then, update its value where the app reads it, and set the new expiry date in credential_expiries (infra/shared/variables.tf), then apply infra/shared. See docs/DEPLOYMENT.md, "Credential expiry reminders".
      EOT
    })
  }
}
