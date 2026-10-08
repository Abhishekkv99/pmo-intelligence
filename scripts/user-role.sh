#!/usr/bin/env bash
# Grant, change or remove a user's role in a deployed environment, or list the
# users, as a one-off ECS task (RDS is private, so it runs inside the VPC).
#
#   AWS_PROFILE=pmo-intelligence scripts/user-role.sh staging --email a@b.com --role sme
#   AWS_PROFILE=pmo-intelligence scripts/user-role.sh staging --email a@b.com --role none
#   AWS_PROFILE=pmo-intelligence scripts/user-role.sh staging --list
#
# Needs: terraform, the AWS CLI, the environment applied
# (infra/environments/<env>) and a backend image that has app.cli.user_role.
# See docs/DEPLOYMENT.md, "Granting roles".
set -euo pipefail

usage="usage: scripts/user-role.sh <environment> (--email <address> --role <role|none> | --list)"
env_name="${1:?$usage}"
shift

roles="pmo_manager sme tech_lead ps admin none"
email="" role="" list=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --email) email="${2:-}"; shift 2 ;;
    --role) role="${2:-}"; shift 2 ;;
    --list) list="yes"; shift ;;
    *) echo "unknown option: $1" >&2; echo "$usage" >&2; exit 2 ;;
  esac
done

# The values go into a JSON override, so accept only plain addresses and the
# known roles: nothing that could close a string or add an argument
if [[ -n "$list" ]]; then
  [[ -z "$email$role" ]] || { echo "--list takes no --email or --role" >&2; exit 2; }
  command='["python","-m","app.cli.user_role","--list"]'
else
  [[ "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] \
    || { echo "not an email address: $email" >&2; exit 2; }
  [[ " $roles " == *" $role "* ]] || { echo "role must be one of: $roles" >&2; exit 2; }
  command="[\"python\",\"-m\",\"app.cli.user_role\",\"--email\",\"$email\",\"--role\",\"$role\"]"
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stack="$repo_root/infra/environments/$env_name"
[[ -d "$stack" ]] || { echo "no such environment: $stack" >&2; exit 2; }

out() { terraform -chdir="$stack" output -raw "$1"; }
cluster="$(out ecs_cluster_name)"
task_definition="$(out admin_cli_task_definition)"
subnets="$(out db_bootstrap_subnets)"
security_group="$(out db_bootstrap_security_group)"
log_group="$(out admin_cli_log_group)"

overrides="{\"containerOverrides\":[{\"name\":\"admin-cli\",\"command\":$command}]}"

echo "Running the role command in $env_name on cluster $cluster"
task_arn="$(aws ecs run-task \
  --cluster "$cluster" \
  --task-definition "$task_definition" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$security_group],assignPublicIp=ENABLED}" \
  --overrides "$overrides" \
  --query 'tasks[0].taskArn' --output text)"
echo "Task: $task_arn"

echo "Waiting for the task to stop (about a minute)..."
aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task_arn"

exit_code="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
  --query 'tasks[0].containers[0].exitCode' --output text)"
reason="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
  --query 'tasks[0].stoppedReason' --output text)"

# This task's own log stream only (ecs/<container>/<task id>)
echo "--- task log ---"
MSYS_NO_PATHCONV=1 aws logs get-log-events --log-group-name "$log_group" \
  --log-stream-name "ecs/admin-cli/${task_arn##*/}" --start-from-head \
  --query 'events[].message' --output text | tr '\t' '\n' || true
echo "---"
echo "Exit code: $exit_code ($reason)"

[[ "$exit_code" == "0" ]]
