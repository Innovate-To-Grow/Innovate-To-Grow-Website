from __future__ import annotations

import boto3
from status_service.aws_checks import AwsRuntimeChecks


class FakeEcs:
    def __init__(self, *, essential_status="RUNNING", nonessential_status="STOPPED", described=True):
        self.essential_status = essential_status
        self.nonessential_status = nonessential_status
        self.described = described

    def describe_services(self, **_kwargs):
        return {
            "services": [
                {
                    "desiredCount": 1,
                    "runningCount": 1,
                    "pendingCount": 0,
                    "taskDefinition": "arn:aws:ecs:us-west-2:111111111111:task-definition/itg-backend:9",
                    "deployments": [],
                }
            ]
        }

    def list_tasks(self, **_kwargs):
        return {"taskArns": ["arn:aws:ecs:us-west-2:111111111111:task/task-id"]}

    def describe_tasks(self, **_kwargs):
        if not self.described:
            return {"tasks": [], "failures": []}
        return {
            "tasks": [
                {
                    "containers": [
                        {"name": "itg-backend", "lastStatus": self.essential_status},
                        {"name": "sidecar", "lastStatus": self.nonessential_status},
                    ]
                }
            ]
        }

    def describe_task_definition(self, **_kwargs):
        return {
            "taskDefinition": {
                "containerDefinitions": [
                    {"name": "itg-backend", "essential": True},
                    {"name": "sidecar", "essential": False},
                ]
            }
        }


def test_ecs_checks_actual_essential_container_names(settings_factory):
    checks = AwsRuntimeChecks(settings_factory(), client_factory=lambda _name: FakeEcs(essential_status="STOPPED"))

    result = checks._ecs("production-api.compute", "itg-backend-service")

    assert result.state == "unhealthy"
    assert result.code == "ECS_CONTAINER_NOT_RUNNING"


def test_ecs_ignores_nonessential_container_and_rejects_missing_described_task(settings_factory):
    healthy = AwsRuntimeChecks(settings_factory(), client_factory=lambda _name: FakeEcs())
    incomplete = AwsRuntimeChecks(settings_factory(), client_factory=lambda _name: FakeEcs(described=False))

    assert healthy._ecs("production-api.compute", "itg-backend-service").state == "healthy"
    assert incomplete._ecs("production-api.compute", "itg-backend-service").code == "ECS_TASK_DESCRIBE_INCOMPLETE"


def test_default_aws_clients_use_bounded_botocore_config(monkeypatch, settings_factory):
    captured = {}

    class Session:
        def __init__(self, **kwargs):
            captured["session"] = kwargs

        def client(self, service_name, *, config):
            captured["service"] = service_name
            captured["config"] = config
            return object()

    monkeypatch.setattr(boto3.session, "Session", Session)
    checks = AwsRuntimeChecks(settings_factory())

    checks._client("ecs")

    assert captured["session"] == {"region_name": "us-west-2"}
    assert captured["config"].connect_timeout == 2
    assert captured["config"].read_timeout == 4
    assert captured["config"].retries["total_max_attempts"] == 2


def test_failed_amplify_deployment_is_a_public_degraded_signal(settings_factory):
    class Amplify:
        def get_branch(self, **_kwargs):
            return {"branch": {"branchName": "main"}}

        def list_jobs(self, **_kwargs):
            return {"jobSummaries": [{"status": "FAILED", "commitId": "abc123"}]}

    checks = AwsRuntimeChecks(settings_factory(), client_factory=lambda _name: Amplify())

    result = checks._amplify("production-website.amplify", "prod-app", "main")

    assert result.state == "degraded"
    assert result.affects_public is True


def test_alarm_summary_queries_only_the_five_stack_alarms(settings_factory):
    captured = {}

    class CloudWatch:
        def describe_alarms(self, **kwargs):
            captured.update(kwargs)
            return {
                "MetricAlarms": [
                    {"AlarmName": "i2g-status-PublicApi5xx", "StateValue": "OK"},
                    {"AlarmName": "i2g-status-ProbeFunctionErrors", "StateValue": "ALARM"},
                ]
            }

    checks = AwsRuntimeChecks(settings_factory(), client_factory=lambda _name: CloudWatch())

    result = checks.alarm_summary()

    assert captured == {
        "AlarmNames": [
            "i2g-status-ProbeFunctionErrors",
            "i2g-status-ProbeMissing",
            "i2g-status-PublicApi5xx",
            "i2g-status-DynamoThrottles",
            "i2g-status-SchedulerDlqMessages",
        ],
        "AlarmTypes": ["MetricAlarm"],
    }
    assert [alarm["name"] for alarm in result["alarms"]] == [
        "i2g-status-ProbeFunctionErrors",
        "i2g-status-PublicApi5xx",
    ]
