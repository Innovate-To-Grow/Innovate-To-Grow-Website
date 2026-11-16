#!/usr/bin/env python3
"""Assert the security boundaries of the legacy-view CloudFormation stack."""

from __future__ import annotations

from .cloudfront import validate_cloudfront, validate_monitoring
from .network import validate_network, validate_outputs, validate_secret
from .nginx import validate_nginx_policy
from .template import MONITORING_TEMPLATE_PATH, TEMPLATE_PATH, load_template


def main() -> int:
    template = load_template(TEMPLATE_PATH)
    validate_network(template)
    validate_secret(template)
    validate_cloudfront(template)
    validate_outputs(template)
    validate_nginx_policy()
    validate_monitoring(load_template(MONITORING_TEMPLATE_PATH))
    return 0
