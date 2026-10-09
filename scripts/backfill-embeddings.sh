#!/usr/bin/env bash
# Embed the signals that have no embedding yet in a deployed environment, as a
# one-off ECS task from the backend service's own task definition: it has the
# Azure OpenAI settings, which the admin-cli task does not. Its migration
# container runs first, as it does for the service (a no-op when the database
# is current); the backend container runs the backfill instead of the server,
# so it takes no processing ownership.
#
#   AWS_PROFILE=pmo-intelligence scripts/backfill-embeddings.sh staging --dry-run
#   AWS_PROFILE=pmo-intelligence scripts/backfill-embeddings.sh staging
#
# Needs: terraform, the AWS CLI, the environment applied
# (infra/environments/<env>) and a backend image that has
# app.cli.backfill_signal_embeddings. See docs/DEPLOYMENT.md, "Backfilling
# signal embeddings".
set -euo pipefail

usage="usage: scripts/backfill-embeddings.sh <environment> [--dry-run]"
env_name="${1:?$usage}"
shift

command='["python","-m","app.cli.backfill_signal_embeddings"]'
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) command='["python","-m","app.cli.backfill_signal_embeddings","--dry-run"]'; shift ;;
    *) echo "unknown option: $1" >&2; echo "$usage" >&2; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stack="$repo_root/infra/environments/$env_name"
[[ -d "$stack" ]] || { echo "no such environment: $stack" >&2; exit 2; }

out() { terraform -chdir="$stack" output -raw "$1"; }
cluster="$(out ecs_cluster_name)"
subnets="$(out db_bootstrap_subnets)"
security_group="$(out db_bootstrap_security_group)"

# The task definition the backend service runs now, and its log group
service="pmo-intelligence-$env_name-backend"
task_definition="$(aws ecs describe-services --cluster "$cluster" --services "$service" \
  --query 'services[0].taskDefinition' --output text)"
[[ "$task_definition" == arn:* ]] || { echo "no backend service $service" >&2; exit 2; }
log_group="$(aws ecs describe-task-definition --task-definition "$task_definition" \
  --query "taskDefinition.containerDefinitions[?name=='backend'] | [0].logConfiguration.options.\"awslogs-group\"" \
  --output text)"

overrides="{\"containerOverrides\":[{\"name\":\"backend\",\"command\":$command}]}"

echo "Running the embedding backfill in $env_name on cluster $cluster"
echo "Task definition: $task_definition"
task_arn="$(aws ecs run-task \
  --cluster "$cluster" \
  --task-definition "$task_definition" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$security_group],assignPublicIp=ENABLED}" \
  --overrides "$overrides" \
  --query 'tasks[0].taskArn' --output text)"
echo "Task: $task_arn"

echo "Waiting for the task to stop (a minute or two)..."
aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task_arn"

exit_code="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
  --query "tasks[0].containers[?name=='backend'] | [0].exitCode" --output text)"
reason="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
  --query 'tasks[0].stoppedReason' --output text)"

# This task's own log stream only (ecs/<container>/<task id>)
echo "--- task log ---"
MSYS_NO_PATHCONV=1 aws logs get-log-events --log-group-name "$log_group" \
  --log-stream-name "ecs/backend/${task_arn##*/}" --start-from-head \
  --query 'events[].message' --output text | tr '\t' '\n' || true
echo "---"
echo "Exit code: $exit_code ($reason)"

[[ "$exit_code" == "0" ]]
