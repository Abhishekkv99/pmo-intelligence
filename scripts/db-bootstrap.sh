#!/usr/bin/env bash
# Run the database bootstrap for an environment as a one-off ECS task and wait
# for its result. RDS is private, so the bootstrap has to run inside the VPC.
#
#   AWS_PROFILE=pmo-intelligence scripts/db-bootstrap.sh staging [--rotate-password]
#
# Needs: terraform, the AWS CLI, and the environment applied
# (infra/environments/<env>). The task runs the backend image's
# `python -m app.cli.db_bootstrap`; see docs/DEPLOYMENT.md.
set -euo pipefail

env_name="${1:?usage: scripts/db-bootstrap.sh <environment> [--rotate-password]}"
shift
rotate=""
if [[ "${1:-}" == "--rotate-password" ]]; then
  rotate="--rotate-password"
elif [[ -n "${1:-}" ]]; then
  echo "unknown option: $1" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stack="$repo_root/infra/environments/$env_name"
[[ -d "$stack" ]] || { echo "no such environment: $stack" >&2; exit 2; }

out() { terraform -chdir="$stack" output -raw "$1"; }
cluster="$(out ecs_cluster_name)"
task_definition="$(out db_bootstrap_task_definition)"
subnets="$(out db_bootstrap_subnets)"
security_group="$(out db_bootstrap_security_group)"
log_group="$(out db_bootstrap_log_group)"

overrides='{}'
if [[ -n "$rotate" ]]; then
  overrides='{"containerOverrides":[{"name":"db-bootstrap","command":["python","-m","app.cli.db_bootstrap","--rotate-password"]}]}'
fi

echo "Starting the $env_name database bootstrap ${rotate:+($rotate) }on cluster $cluster"
task_arn="$(aws ecs run-task \
  --cluster "$cluster" \
  --task-definition "$task_definition" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$security_group],assignPublicIp=ENABLED}" \
  --overrides "$overrides" \
  --query 'tasks[0].taskArn' --output text)"
echo "Task: $task_arn"

echo "Waiting for the task to stop (a few minutes)..."
aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task_arn"

exit_code="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
  --query 'tasks[0].containers[0].exitCode' --output text)"
reason="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
  --query 'tasks[0].stoppedReason' --output text)"

echo "--- task log ($log_group) ---"
MSYS_NO_PATHCONV=1 aws logs tail "$log_group" --since 30m --format short || true
echo "---"
echo "Exit code: $exit_code ($reason)"

[[ "$exit_code" == "0" ]]
