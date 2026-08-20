"""Sanitized read-only AWS runtime checks used by the status probe."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .settings import Settings
from .types import CheckResult


def _revision(task_definition_arn: str | None) -> str | None:
    if not task_definition_arn:
        return None
    # Return only the family:revision suffix, never an ARN/account identifier.
    return task_definition_arn.rsplit("/", 1)[-1]


class AwsRuntimeChecks:
    """Perform least-privilege AWS reads and normalize every failure."""

    def __init__(self, settings: Settings, client_factory: Callable[[str], Any] | None = None):
        self.settings = settings
        if client_factory is None:
            import boto3
            from botocore.config import Config

            session = boto3.session.Session(region_name=settings.aws_region)
            client_config = Config(
                connect_timeout=2,
                read_timeout=4,
                retries={"total_max_attempts": 2, "mode": "standard"},
            )

            def client_factory(service_name: str) -> Any:
                return session.client(service_name, config=client_config)

        self._client = client_factory

    def collect(self) -> dict[str, tuple[CheckResult, ...]]:
        """Return public-affecting checks grouped by public component."""

        checks: dict[str, list[CheckResult]] = {
            "production-website": [],
            "production-api": [],
            "demo-website": [],
            "demo-api": [],
            "project-archive": [],
        }
        operations: list[tuple[tuple[str, ...], str, Callable[[], CheckResult], bool]] = [
            (
                ("production-website",),
                "production-website.amplify",
                lambda: self._amplify(
                    "production-website.amplify",
                    self.settings.production_amplify_app_id,
                    self.settings.production_amplify_branch,
                ),
                True,
            ),
            (
                ("demo-website",),
                "demo-website.amplify",
                lambda: self._amplify(
                    "demo-website.amplify",
                    self.settings.demo_amplify_app_id,
                    self.settings.demo_amplify_branch,
                ),
                True,
            ),
            (("production-api", "demo-api"), "shared.database", self._rds, True),
            (
                ("production-api",),
                "production-api.assets",
                lambda: self._bucket("production-api.assets", self.settings.production_assets_bucket),
                True,
            ),
            (
                ("demo-api",),
                "demo-api.assets",
                lambda: self._bucket("demo-api.assets", self.settings.demo_assets_bucket),
                True,
            ),
        ]
        for component_id, service_name, target_group_arn in (
            ("production-api", self.settings.production_ecs_service, self.settings.production_target_group_arn),
            ("demo-api", self.settings.demo_ecs_service, self.settings.demo_target_group_arn),
            ("project-archive", self.settings.archive_ecs_service, self.settings.archive_target_group_arn),
        ):
            operations.extend(
                (
                    (
                        (component_id,),
                        f"{component_id}.compute",
                        lambda name=service_name, check_id=f"{component_id}.compute": self._ecs(check_id, name),
                        True,
                    ),
                    (
                        (component_id,),
                        f"{component_id}.load-balancer",
                        lambda arn=target_group_arn, check_id=f"{component_id}.load-balancer": self._target_group(
                            check_id, arn
                        ),
                        True,
                    ),
                )
            )

        with ThreadPoolExecutor(max_workers=10, thread_name_prefix="status-aws") as executor:
            futures = {
                executor.submit(self._safe, check_id, operation, affects_public=affects_public): component_ids
                for component_ids, check_id, operation, affects_public in operations
            }
            for future in as_completed(futures):
                result = future.result()
                for component_id in futures[future]:
                    checks[component_id].append(result)
        for component_checks in checks.values():
            component_checks.sort(key=lambda item: item.check_id)
        return {key: tuple(value) for key, value in checks.items()}

    def alarm_summary(self) -> dict[str, Any]:
        """Return alarm state for staff; alarm failures never alter service health."""

        try:
            response = self._client("cloudwatch").describe_alarms(
                AlarmNamePrefix=self.settings.alarm_prefix,
                MaxRecords=100,
            )
            alarms = [
                {
                    "name": str(alarm.get("AlarmName", ""))[:128],
                    "state": str(alarm.get("StateValue", "UNKNOWN")),
                    "updatedAt": _iso(alarm.get("StateUpdatedTimestamp")),
                    "namespace": str(alarm.get("Namespace", ""))[:128],
                    "metric": str(alarm.get("MetricName", ""))[:128],
                    "reason": str(alarm.get("StateReason", ""))[:500],
                }
                for alarm in response.get("MetricAlarms", [])
            ]
            return {"state": "ok", "alarms": alarms}
        except Exception:
            return {"state": "partial", "code": "ALARMS_UNAVAILABLE", "alarms": []}

    def stack_summary(self) -> dict[str, Any]:
        try:
            cloudformation = self._client("cloudformation")
            stack = cloudformation.describe_stacks(StackName=self.settings.stack_name).get("Stacks", [])[0]
            resources = cloudformation.list_stack_resources(StackName=self.settings.stack_name).get(
                "StackResourceSummaries", []
            )
            return {
                "state": "ok",
                "name": self.settings.stack_name,
                "region": self.settings.aws_region,
                "stackStatus": str(stack.get("StackStatus", "UNKNOWN"))[:80],
                "resources": [
                    {
                        "logicalId": str(item.get("LogicalResourceId", ""))[:128],
                        "type": str(item.get("ResourceType", ""))[:128],
                        "physicalId": _physical_id(item.get("PhysicalResourceId")),
                        "status": str(item.get("ResourceStatus", "UNKNOWN"))[:80],
                    }
                    for item in resources[:250]
                ],
            }
        except Exception:
            return {
                "state": "partial",
                "code": "STACK_UNAVAILABLE",
                "name": self.settings.stack_name,
                "region": self.settings.aws_region,
                "stackStatus": "UNKNOWN",
                "resources": [],
            }

    def _safe(self, check_id: str, operation: Callable[[], CheckResult], *, affects_public: bool = True) -> CheckResult:
        try:
            return operation()
        except Exception:
            return CheckResult(check_id, "aws", "unknown", "AWS_CHECK_ERROR", affects_public=affects_public)

    def _ecs(self, check_id: str, service_name: str) -> CheckResult:
        ecs = self._client("ecs")
        response = ecs.describe_services(cluster=self.settings.ecs_cluster_name, services=[service_name])
        services = response.get("services", [])
        if response.get("failures") or len(services) != 1:
            return CheckResult(check_id, "aws", "unhealthy", "ECS_SERVICE_MISSING")
        service = services[0]
        desired = int(service.get("desiredCount", 0))
        running = int(service.get("runningCount", 0))
        detail = {
            "service": service_name,
            "cluster": self.settings.ecs_cluster_name,
            "desiredTasks": desired,
            "runningTasks": running,
            "pendingTasks": int(service.get("pendingCount", 0)),
            "taskDefinition": _revision(service.get("taskDefinition")),
            "deployments": [
                {
                    "status": str(deployment.get("status", ""))[:40],
                    "rolloutState": str(deployment.get("rolloutState", ""))[:40],
                }
                for deployment in service.get("deployments", [])[:10]
            ],
        }
        if desired < 1 or running < desired:
            return CheckResult(check_id, "aws", "unhealthy", "ECS_CAPACITY_LOW", detail=detail)

        task_arns = ecs.list_tasks(cluster=self.settings.ecs_cluster_name, serviceName=service_name).get("taskArns", [])
        if len(task_arns) < desired:
            return CheckResult(check_id, "aws", "unhealthy", "ECS_TASKS_MISSING", detail=detail)
        described = ecs.describe_tasks(cluster=self.settings.ecs_cluster_name, tasks=task_arns[:100])
        tasks = described.get("tasks", [])
        if described.get("failures") or len(tasks) < desired:
            return CheckResult(check_id, "aws", "unhealthy", "ECS_TASK_DESCRIBE_INCOMPLETE", detail=detail)
        task_definition = ecs.describe_task_definition(taskDefinition=service.get("taskDefinition", "")).get(
            "taskDefinition", {}
        )
        essential_names = {
            str(container.get("name"))
            for container in task_definition.get("containerDefinitions", [])
            if container.get("essential", True)
        }
        essential_stopped = not essential_names or any(
            any(containers.get(name, {}).get("lastStatus") != "RUNNING" for name in essential_names)
            for containers in (
                {str(container.get("name")): container for container in task.get("containers", [])} for task in tasks
            )
        )
        if essential_stopped:
            return CheckResult(check_id, "aws", "unhealthy", "ECS_CONTAINER_NOT_RUNNING", detail=detail)
        return CheckResult(check_id, "aws", "healthy", "ECS_HEALTHY", detail=detail)

    def _target_group(self, check_id: str, target_group_arn: str) -> CheckResult:
        descriptions = (
            self._client("elbv2")
            .describe_target_health(TargetGroupArn=target_group_arn)
            .get("TargetHealthDescriptions", [])
        )
        states = [description.get("TargetHealth", {}).get("State", "unknown") for description in descriptions]
        detail = {
            "registeredTargets": len(states),
            "healthyTargets": states.count("healthy"),
            "targetHealth": [{"state": str(state)[:40]} for state in states[:20]],
        }
        if not states or any(state != "healthy" for state in states):
            return CheckResult(check_id, "aws", "unhealthy", "TARGETS_NOT_HEALTHY", detail=detail)
        return CheckResult(check_id, "aws", "healthy", "TARGETS_HEALTHY", detail=detail)

    def _rds(self) -> CheckResult:
        instances = (
            self._client("rds")
            .describe_db_instances(DBInstanceIdentifier=self.settings.rds_instance_id)
            .get("DBInstances", [])
        )
        if len(instances) != 1:
            return CheckResult("shared.database", "aws", "unhealthy", "DATABASE_MISSING")
        status = str(instances[0].get("DBInstanceStatus", "unknown"))
        detail = {"database": self.settings.rds_instance_id, "status": status}
        if status != "available":
            return CheckResult("shared.database", "aws", "unhealthy", "DATABASE_NOT_AVAILABLE", detail=detail)
        return CheckResult("shared.database", "aws", "healthy", "DATABASE_AVAILABLE", detail=detail)

    def _bucket(self, check_id: str, bucket_name: str) -> CheckResult:
        self._client("s3").head_bucket(Bucket=bucket_name)
        return CheckResult(check_id, "aws", "healthy", "BUCKET_ACCESSIBLE", detail={"bucket": bucket_name})

    def _amplify(self, check_id: str, app_id: str, branch_name: str) -> CheckResult:
        amplify = self._client("amplify")
        branch = amplify.get_branch(appId=app_id, branchName=branch_name).get("branch", {})
        jobs = amplify.list_jobs(appId=app_id, branchName=branch_name, maxResults=1).get("jobSummaries", [])
        latest_status = str(jobs[0].get("status", "UNKNOWN")) if jobs else "UNKNOWN"
        latest = jobs[0] if jobs else {}
        detail = {
            "appId": app_id,
            "branch": branch.get("branchName", branch_name),
            "latestDeploymentStatus": latest_status,
            "lastJob": {
                "status": latest_status,
                "commitId": str(latest.get("commitId", ""))[:64],
                "startedAt": _iso(latest.get("startTime")),
                "endedAt": _iso(latest.get("endTime")),
            },
        }
        # A failed deployment is staff-visible but cannot make a currently reachable page an outage.
        if latest_status in {"FAILED", "CANCELLED"}:
            return CheckResult(check_id, "aws", "degraded", "AMPLIFY_DEPLOYMENT_FAILED", detail=detail)
        return CheckResult(check_id, "aws", "info", "AMPLIFY_OBSERVED", affects_public=False, detail=detail)


def _iso(value: Any) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if hasattr(value, "isoformat") else None


def _physical_id(value: Any) -> str:
    text = str(value or "")
    if text.startswith("arn:"):
        text = text.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    elif "://" in text:
        text = text.rstrip("/").rsplit("/", 1)[-1]
    return text[:256]
