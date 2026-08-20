"""Environment-backed configuration for fixed status resources."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    table_name: str
    release_sha: str
    aws_region: str
    ecs_cluster_name: str
    production_ecs_service: str
    demo_ecs_service: str
    archive_ecs_service: str
    production_target_group_arn: str
    demo_target_group_arn: str
    archive_target_group_arn: str
    rds_instance_id: str
    production_assets_bucket: str
    demo_assets_bucket: str
    production_amplify_app_id: str
    demo_amplify_app_id: str
    production_amplify_branch: str
    demo_amplify_branch: str
    alarm_prefix: str
    stack_name: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            table_name=_required("STATUS_TABLE_NAME"),
            release_sha=os.environ.get("RELEASE_SHA", "unknown")[:64],
            aws_region=os.environ.get("AWS_REGION", "us-west-2"),
            ecs_cluster_name=os.environ.get("ECS_CLUSTER_NAME", "itg-backend-cluster"),
            production_ecs_service=os.environ.get("PRODUCTION_ECS_SERVICE", "itg-backend-service"),
            demo_ecs_service=os.environ.get("DEMO_ECS_SERVICE", "itg-backend-demo-service"),
            archive_ecs_service=os.environ.get("ARCHIVE_ECS_SERVICE", "itg-archive-service"),
            production_target_group_arn=_required("PRODUCTION_TARGET_GROUP_ARN"),
            demo_target_group_arn=_required("DEMO_TARGET_GROUP_ARN"),
            archive_target_group_arn=_required("ARCHIVE_TARGET_GROUP_ARN"),
            rds_instance_id=os.environ.get("RDS_INSTANCE_ID", "i2g-prod-postgres-west2"),
            production_assets_bucket=os.environ.get("PRODUCTION_ASSETS_BUCKET", "itg-static-assets"),
            demo_assets_bucket=os.environ.get("DEMO_ASSETS_BUCKET", "itg-demo-static-assets"),
            production_amplify_app_id=_required("PRODUCTION_AMPLIFY_APP_ID"),
            demo_amplify_app_id=_required("DEMO_AMPLIFY_APP_ID"),
            production_amplify_branch=os.environ.get("PRODUCTION_AMPLIFY_BRANCH", "main"),
            demo_amplify_branch=os.environ.get("DEMO_AMPLIFY_BRANCH", "main"),
            alarm_prefix=os.environ.get("STATUS_ALARM_PREFIX", "I2GStatus-"),
            stack_name=os.environ.get("STATUS_STACK_NAME", "i2g-status"),
        )


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
