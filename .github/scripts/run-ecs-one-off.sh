#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 5 ]; then
  echo "usage: run-ecs-one-off.sh CLUSTER SERVICE TASK_DEFINITION CONTAINER COMMAND..." >&2
  exit 64
fi

cluster="$1"
service="$2"
task_definition="$3"
container="$4"
shift 4

network_configuration="$(
  aws ecs describe-services \
    --cluster "$cluster" \
    --services "$service" \
    --query 'services[0].networkConfiguration' \
    --output json
)"
if [ -z "$network_configuration" ] || [ "$network_configuration" = "null" ]; then
  echo "Unable to resolve the network configuration for ECS service $service." >&2
  exit 1
fi

command_json="$(printf '%s\n' "$@" | jq --raw-input . | jq --slurp .)"
overrides="$(
  jq --null-input \
    --arg container "$container" \
    --argjson command "$command_json" \
    '{containerOverrides: [{name: $container, command: $command}]}'
)"

run_result="$(
  aws ecs run-task \
    --cluster "$cluster" \
    --launch-type FARGATE \
    --task-definition "$task_definition" \
    --network-configuration "$network_configuration" \
    --overrides "$overrides" \
    --output json
)"
task_arn="$(jq --raw-output '.tasks[0].taskArn // empty' <<<"$run_result")"
if [ -z "$task_arn" ]; then
  echo "ECS refused to start the one-off task:" >&2
  jq '.failures' <<<"$run_result" >&2
  exit 1
fi

echo "Waiting for one-off task $task_arn"
aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task_arn"

task_result="$(
  aws ecs describe-tasks \
    --cluster "$cluster" \
    --tasks "$task_arn" \
    --output json
)"
exit_code="$(
  jq --raw-output \
    --arg container "$container" \
    '.tasks[0].containers[] | select(.name == $container) | .exitCode // empty' \
    <<<"$task_result"
)"
if [ "$exit_code" != "0" ]; then
  stopped_reason="$(jq --raw-output '.tasks[0].stoppedReason // "unknown"' <<<"$task_result")"
  container_reason="$(
    jq --raw-output \
      --arg container "$container" \
      '.tasks[0].containers[] | select(.name == $container) | .reason // "unknown"' \
      <<<"$task_result"
  )"
  echo "One-off task failed (exit=$exit_code, stopped=$stopped_reason, container=$container_reason)." >&2
  exit 1
fi

echo "One-off task completed successfully: $task_arn"
