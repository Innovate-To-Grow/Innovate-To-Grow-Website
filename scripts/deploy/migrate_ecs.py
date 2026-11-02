"""Run the release's migrations as a single ECS task before updating the service."""

import copy
import json
import os
import subprocess
import sys
import time


def aws(*args):
    return json.loads(subprocess.check_output(["aws", "ecs", *args, "--output", "json"], text=True))


def migration_definition(task):
    task = copy.deepcopy(task)
    task["family"] += "-migrate"
    web = next(c for c in task["containerDefinitions"] if c["name"] == "itg-backend")
    task["containerDefinitions"] = [web]
    for field in ("healthCheck", "portMappings", "dependsOn"):
        web.pop(field, None)
    web["entryPoint"] = ["python"]
    web["command"] = ["manage.py", "migrate", "--noinput"]
    web["logConfiguration"]["options"]["awslogs-stream-prefix"] = "migration"
    return task


def main():
    cluster, service = os.environ["ECS_CLUSTER"], os.environ["ECS_SERVICE"]
    with open(sys.argv[1]) as source:
        definition = migration_definition(json.load(source))
    # A cancelled workflow can leave its migration running. Refuse overlapping DDL.
    active = aws("list-tasks", "--cluster", cluster, "--family", definition["family"])
    if active["taskArns"]:
        raise RuntimeError(f"A migration task is still active: {active['taskArns']}")
    live = aws("describe-services", "--cluster", cluster, "--services", service)
    if live.get("failures") or len(live.get("services", [])) != 1:
        raise RuntimeError("Cannot determine the service network configuration")
    registered = aws("register-task-definition", "--cli-input-json", json.dumps(definition))
    launched = aws(
        "run-task",
        "--cluster",
        cluster,
        "--launch-type",
        "FARGATE",
        "--task-definition",
        registered["taskDefinition"]["taskDefinitionArn"],
        "--network-configuration",
        json.dumps(live["services"][0]["networkConfiguration"]),
        "--started-by",
        "github-migration-" + os.environ.get("GITHUB_RUN_ID", "manual"),
    )
    if launched.get("failures") or len(launched.get("tasks", [])) != 1:
        raise RuntimeError("ECS could not start the migration task")
    task_arn = launched["tasks"][0]["taskArn"]
    print(f"Migration task: {task_arn}", flush=True)
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        result = aws("describe-tasks", "--cluster", cluster, "--tasks", task_arn)
        if result.get("failures") or len(result.get("tasks", [])) != 1:
            raise RuntimeError(f"Cannot inspect migration task {task_arn}")
        task = result["tasks"][0]
        if task["lastStatus"] == "STOPPED":
            containers = task.get("containers", [])
            if len(containers) != 1 or containers[0].get("exitCode") != 0:
                raise RuntimeError(f"Migration failed; inspect {task_arn} and its migration log stream")
            print("Migration completed successfully")
            return
        time.sleep(10)
    raise RuntimeError(f"Migration timed out; inspect {task_arn} before retrying. Service was not updated.")


if __name__ == "__main__":
    main()
