from __future__ import annotations

import sys
from pathlib import Path

import pytest

FUNCTIONS_DIR = Path(__file__).resolve().parents[1] / "functions"
sys.path.insert(0, str(FUNCTIONS_DIR))

from status_service.settings import Settings  # noqa: E402


@pytest.fixture
def settings_factory():
    def build(**overrides):
        values = {
            "table_name": "status-table",
            "release_sha": "abc123",
            "aws_region": "us-west-2",
            "ecs_cluster_name": "itg-backend-cluster",
            "production_ecs_service": "itg-backend-service",
            "demo_ecs_service": "itg-backend-demo-service",
            "archive_ecs_service": "itg-archive-service",
            "production_target_group_arn": "arn:aws:elasticloadbalancing:us-west-2:111111111111:targetgroup/prod/1",
            "demo_target_group_arn": "arn:aws:elasticloadbalancing:us-west-2:111111111111:targetgroup/demo/2",
            "archive_target_group_arn": "arn:aws:elasticloadbalancing:us-west-2:111111111111:targetgroup/archive/3",
            "rds_instance_id": "i2g-prod-postgres-west2",
            "production_assets_bucket": "itg-static-assets",
            "demo_assets_bucket": "itg-demo-static-assets",
            "production_amplify_app_id": "prod-app",
            "demo_amplify_app_id": "demo-app",
            "production_amplify_branch": "main",
            "demo_amplify_branch": "main",
            "alarm_prefix": "i2g-status-",
            "stack_name": "i2g-status",
        }
        values.update(overrides)
        return Settings(**values)

    return build
