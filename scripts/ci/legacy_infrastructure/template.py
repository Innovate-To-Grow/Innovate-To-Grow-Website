from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


TEMPLATE_PATH = REPOSITORY_ROOT / "aws" / "legacy" / "cloudformation" / "template.yaml"


MONITORING_TEMPLATE_PATH = REPOSITORY_ROOT / "aws" / "legacy" / "cloudformation" / "monitoring-us-east-1.yaml"


NGINX_SERVER_PATH = REPOSITORY_ROOT / "aws" / "legacy" / "nginx" / "i2g-legacy-private-readonly.conf"


NGINX_UWSGI_PATH = REPOSITORY_ROOT / "aws" / "legacy" / "nginx" / "i2g-legacy-readonly-uwsgi.conf"


DJANGO_POLICY_PATH = REPOSITORY_ROOT / "src" / "apps" / "core" / "legacy_view" / "origin" / "policies.py"


class CloudFormationLoader(yaml.SafeLoader):
    """Load CloudFormation YAML while preserving intrinsic functions."""


def _construct_tag(loader: CloudFormationLoader, suffix: str, node: yaml.Node) -> dict[str, Any]:
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {f"!{suffix}": value}


CloudFormationLoader.add_multi_constructor("!", _construct_tag)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_template(path: Path) -> dict[str, Any]:
    template = yaml.load(path.read_text(encoding="utf-8"), Loader=CloudFormationLoader)
    require(isinstance(template, dict), f"{path} must be a CloudFormation mapping")
    return template


def resource(template: dict[str, Any], logical_id: str, expected_type: str) -> dict[str, Any]:
    value = template.get("Resources", {}).get(logical_id)
    require(isinstance(value, dict), f"missing resource {logical_id}")
    require(value.get("Type") == expected_type, f"{logical_id} must be {expected_type}")
    return value
