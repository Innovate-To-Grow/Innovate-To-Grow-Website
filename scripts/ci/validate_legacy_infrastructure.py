#!/usr/bin/env python3
"""Assert the security boundaries of the legacy-view CloudFormation stack."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPOSITORY_ROOT / "aws" / "legacy" / "template.yaml"
MONITORING_TEMPLATE_PATH = REPOSITORY_ROOT / "aws" / "legacy" / "monitoring-us-east-1.yaml"
NGINX_SERVER_PATH = REPOSITORY_ROOT / "aws" / "legacy" / "nginx" / "i2g-legacy-private-readonly.conf"
NGINX_UWSGI_PATH = REPOSITORY_ROOT / "aws" / "legacy" / "nginx" / "i2g-legacy-readonly-uwsgi.conf"
DJANGO_POLICY_PATH = REPOSITORY_ROOT / "src" / "apps" / "core" / "legacy_view" / "policies.py"


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


def validate_network(template: dict[str, Any]) -> None:
    peering = resource(template, "LegacyVpcPeering", "AWS::EC2::VPCPeeringConnection")
    require(
        peering["Properties"].get("VpcId") == {"!Ref": "ApplicationVpcId"},
        "peering requester must be the application VPC",
    )
    require(
        peering["Properties"].get("PeerVpcId") == {"!Ref": "LegacyVpcId"},
        "peering accepter must be the legacy VPC",
    )

    expected_routes = {
        "ApplicationToLegacyRoute": ("ApplicationRouteTableId", "LegacyVpcCidr"),
        "LegacyToApplicationRoute": ("LegacyRouteTableId", "ApplicationVpcCidr"),
    }
    for logical_id, (route_table, destination) in expected_routes.items():
        route = resource(template, logical_id, "AWS::EC2::Route")
        properties = route["Properties"]
        require(properties.get("RouteTableId") == {"!Ref": route_table}, f"{logical_id} route table is wrong")
        require(
            properties.get("DestinationCidrBlock") == {"!Ref": destination},
            f"{logical_id} destination is wrong",
        )
        require(
            properties.get("VpcPeeringConnectionId") == {"!Ref": "LegacyVpcPeering"},
            f"{logical_id} must use the managed peering connection",
        )

    ingress = resource(template, "LegacyPrivateIngress", "AWS::EC2::SecurityGroupIngress")["Properties"]
    require(ingress.get("GroupId") == {"!Ref": "LegacySecurityGroupId"}, "ingress must target the legacy SG")
    require(ingress.get("SourceSecurityGroupId") == {"!Ref": "ApplicationSecurityGroupId"}, "bad SG source")
    require(ingress.get("IpProtocol") == "tcp", "legacy private listener must use TCP")
    require(ingress.get("FromPort") == {"!Ref": "LegacyPrivatePort"}, "legacy ingress start port is wrong")
    require(ingress.get("ToPort") == {"!Ref": "LegacyPrivatePort"}, "legacy ingress end port is wrong")
    require("CidrIp" not in ingress and "CidrIpv6" not in ingress, "legacy port must never be CIDR-accessible")


def validate_secret(template: dict[str, Any]) -> None:
    secret_name = template.get("Parameters", {}).get("OriginHeaderSecretName", {})
    require(
        secret_name.get("Default") == "itg/backend/legacy-view-origin-header",
        "the generated secret must stay under the existing backend execution-role namespace",
    )
    secret = resource(template, "LegacyOriginHeaderSecret", "AWS::SecretsManager::Secret")
    require(secret.get("DeletionPolicy") == "Retain", "shared header secret must survive stack deletion")
    require(secret.get("UpdateReplacePolicy") == "Retain", "replacement shared header secret must be retained")
    properties = secret["Properties"]
    require("SecretString" not in properties, "the template must never contain a literal shared header")
    generation = properties.get("GenerateSecretString", {})
    require(generation.get("PasswordLength", 0) >= 32, "shared header must have at least 32 generated characters")
    require(generation.get("ExcludePunctuation") is True, "shared header must be safe in an HTTP field value")


def _validate_no_alarms_and_no_cache(template: dict[str, Any]) -> None:
    require(
        not any(item.get("Type") == "AWS::CloudWatch::Alarm" for item in template.get("Resources", {}).values()),
        "CloudFront alarms must be deployed by the separate us-east-1 monitoring stack",
    )
    no_cache = resource(template, "LegacyNoCachePolicy", "AWS::CloudFront::CachePolicy")
    cache_config = no_cache["Properties"]["CachePolicyConfig"]
    require(
        all(cache_config.get(name) == 0 for name in ("MinTTL", "DefaultTTL", "MaxTTL")),
        "legacy responses must not be cached",
    )


def _validate_origin_request_policy(template: dict[str, Any]) -> None:
    request_policy = resource(template, "LegacyOriginRequestPolicy", "AWS::CloudFront::OriginRequestPolicy")
    request_config = request_policy["Properties"]["OriginRequestPolicyConfig"]
    require(len(request_config.get("Comment", "")) <= 128, "origin-request policy comment exceeds AWS limit")
    cookies = request_config.get("CookiesConfig", {})
    require(cookies.get("CookieBehavior") == "whitelist", "legacy cookies must use a whitelist")
    require(cookies.get("Cookies") == ["i2g_legacy_viewer"], "only the isolated viewer cookie may be forwarded")
    headers = request_config.get("HeadersConfig", {})
    require(headers.get("HeaderBehavior") == "whitelist", "origin headers must use a whitelist")
    forwarded_headers = {str(value).lower() for value in headers.get("Headers", [])}
    require(
        forwarded_headers
        == {"accept", "accept-language", "content-type", "if-modified-since", "if-none-match", "if-range"},
        "origin headers must be the audited representation/exchange allowlist",
    )
    require("host" not in forwarded_headers, "the viewer Host header must never reach the API origin")
    require("authorization" not in forwarded_headers, "viewer Authorization must never reach the API origin")
    require(
        request_config.get("QueryStringsConfig", {}).get("QueryStringBehavior") == "all",
        "historical read-only navigation query strings must reach the fixed Django gateway",
    )


def _validate_distribution_origin(template: dict[str, Any]) -> dict[str, Any]:
    """Check the single fixed origin; return the distribution config for the behavior checks."""
    distribution = resource(template, "LegacyDistribution", "AWS::CloudFront::Distribution")
    config = distribution["Properties"]["DistributionConfig"]
    require(config.get("ViewerCertificate") == {"CloudFrontDefaultCertificate": True}, "use the AWS default cert")
    origins = config.get("Origins", [])
    require(len(origins) == 1, "legacy CloudFront must have exactly one fixed origin")
    origin = origins[0]
    require(origin.get("DomainName") == {"!Ref": "BackendOriginDomainName"}, "origin domain must be parameterized")
    require(origin.get("OriginPath") == {"!Ref": "BackendOriginPath"}, "origin path must be /legacy-view")
    require(
        origin.get("CustomOriginConfig", {}).get("OriginProtocolPolicy") == "https-only",
        "CloudFront must use HTTPS to Django",
    )
    custom_headers = origin.get("OriginCustomHeaders", [])
    require(len(custom_headers) == 1, "CloudFront must send exactly one custom origin header")
    require(
        custom_headers[0].get("HeaderName") == {"!Ref": "OriginHeaderName"},
        "the custom origin header name must be shared with Django",
    )
    header_value = str(custom_headers[0].get("HeaderValue", {}))
    require("resolve:secretsmanager:" in header_value, "the origin header value must resolve from Secrets Manager")
    return config


def _validate_default_behavior(config: dict[str, Any]) -> None:
    behavior = config.get("DefaultCacheBehavior", {})
    require(behavior.get("ViewerProtocolPolicy") == "https-only", "the viewer endpoint must reject HTTP")
    require(
        set(behavior.get("AllowedMethods", [])) == {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"},
        "CloudFront must carry the exchange POST while Django enforces the method allowlist",
    )
    require(behavior.get("CachePolicyId") == {"!Ref": "LegacyNoCachePolicy"}, "the no-cache policy is required")
    require(
        behavior.get("OriginRequestPolicyId") == {"!Ref": "LegacyOriginRequestPolicy"},
        "the restricted origin-request policy is required",
    )
    require(behavior.get("Compress") is False, "CloudFront compression must not alter Range response semantics")


def validate_cloudfront(template: dict[str, Any]) -> None:
    _validate_no_alarms_and_no_cache(template)
    _validate_origin_request_policy(template)
    _validate_default_behavior(_validate_distribution_origin(template))


def validate_outputs(template: dict[str, Any]) -> None:
    outputs = template.get("Outputs", {})
    for output in (
        "VpcPeeringConnectionId",
        "LegacyOriginHeaderSecretArn",
        "LegacyOriginHeaderName",
        "LegacyViewerDomainName",
        "LegacyViewerUrl",
        "LegacyDistributionId",
    ):
        require(output in outputs, f"missing operator output {output}")


def validate_monitoring(template: dict[str, Any]) -> None:
    resources = template.get("Resources", {})
    require(
        {item.get("Type") for item in resources.values()} == {"AWS::CloudWatch::Alarm"},
        "the us-east-1 monitoring stack may own only CloudWatch alarms",
    )
    alarm = resource(template, "LegacyDistribution5xxAlarm", "AWS::CloudWatch::Alarm")["Properties"]
    require(alarm.get("Namespace") == "AWS/CloudFront", "the 5xx alarm must monitor CloudFront")
    require(alarm.get("MetricName") == "5xxErrorRate", "the alarm must use the CloudFront 5xx rate")
    require(not alarm.get("AlarmActions"), "the initial alarm is intentionally actionless")
    dimensions = {item["Name"]: item["Value"] for item in alarm.get("Dimensions", [])}
    require(dimensions.get("DistributionId") == {"!Ref": "DistributionId"}, "alarm needs the distribution ID")
    require(dimensions.get("Region") == "Global", "CloudFront alarm Region dimension must be Global")
    require(
        template.get("Outputs", {}).get("LegacyDistribution5xxAlarmName", {}).get("Value")
        == {"!Ref": "LegacyDistribution5xxAlarm"},
        "monitoring stack must output the alarm name",
    )


def _policy_string_set(name: str) -> set[str]:
    tree = ast.parse(DJANGO_POLICY_PATH.read_text(encoding="utf-8"), filename=str(DJANGO_POLICY_PATH))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            value = ast.literal_eval(node.value)
            require(isinstance(value, set), f"{name} must remain a literal set so infrastructure CI can audit it")
            return {str(item).lower() for item in value}
    raise AssertionError(f"missing Django policy set {name}")


def _nginx_alternatives_after_marker(server_config: str, marker: str, prefix: str = "/") -> set[str]:
    lines = server_config.splitlines()
    marker_index = next((index for index, line in enumerate(lines) if line.strip() == f"# {marker}"), None)
    require(marker_index is not None, f"missing Nginx policy marker {marker}")
    location = next((line.strip() for line in lines[marker_index + 1 :] if line.strip()), "")
    require("(?:" in location, f"{marker} must be followed by an alternation location")
    alternatives = location.split("(?:", 1)[1].split(")", 1)[0].split("|")
    require(all(alternatives), f"{marker} contains an empty path alternative")
    return {f"{prefix}{item}".lower() for item in alternatives}


def _validate_private_server(server_config: str) -> None:
    for required in (
        "listen 172.31.69.63:8080;",
        "server 127.0.0.1:5001;",
        "allow 10.2.0.0/16;",
        "deny all;",
        "GET  1;",
        "HEAD 1;",
        "return 405;",
        "return 404;",
        "access_log /var/log/nginx/i2g-legacy-private-access.log i2g_legacy_private;",
    ):
        require(required in server_config, f"private Nginx config is missing {required}")

    log_format = server_config.split("log_format i2g_legacy_private", 1)[1].split(";", 1)[0]
    require("$request_method" in log_format and "$uri" in log_format, "private log needs method and path")
    log_format_names = log_format.replace("$request_method", "").replace("$request_time", "")
    require("$request" not in log_format_names, "private log must not record raw requests")
    require("$args" not in log_format, "private log must not record query strings")
    error_logs = [line.strip() for line in server_config.splitlines() if line.strip().startswith("error_log ")]
    require(
        error_logs == ["error_log /dev/null error;"],
        "private Nginx error log must not record request lines or query strings",
    )


def _validate_uwsgi_snippet(uwsgi_config: str) -> None:
    for required in (
        "uwsgi_pass i2g_legacy_application;",
        'uwsgi_param HTTP_AUTHORIZATION "";',
        'uwsgi_param HTTP_COOKIE "";',
        "uwsgi_hide_header Set-Cookie;",
    ):
        require(required in uwsgi_config, f"uWSGI snippet is missing {required}")


def _validate_route_parity(server_config: str) -> None:
    """The Nginx route lists must match the Django policy exactly."""
    information = _nginx_alternatives_after_marker(server_config, "I2G_LEGACY_INFORMATION_PATHS")
    require(
        information == _policy_string_set("_INFORMATION_PATHS") - {"/"},
        "Nginx information routes must exactly match the Django positive allowlist",
    )
    apis = _nginx_alternatives_after_marker(server_config, "I2G_LEGACY_READ_ONLY_API_PATHS", "/api/")
    require(apis == _policy_string_set("_READ_ONLY_API_PATHS"), "Nginx read-only APIs must match Django")
    blocked = _nginx_alternatives_after_marker(server_config, "I2G_LEGACY_BLOCKED_PREFIXES")
    require(blocked == _policy_string_set("_BLOCKED_PREFIXES"), "Nginx blocked prefixes must match Django")

    blocked_static = _nginx_alternatives_after_marker(
        server_config,
        "I2G_LEGACY_BLOCKED_STATIC_PATHS",
        "/static/",
    )
    blocked_static = {path.replace(r"\.", ".") for path in blocked_static}
    require(blocked_static == _policy_string_set("_BLOCKED_STATIC_PATHS"), "Nginx blocked static paths must match")
    require("location ~* ^/event/" in server_config, "Nginx must block Flask-Admin /event descendants")
    require("location ~* ^/static/admin(?:/|$)" in server_config, "Nginx must block Flask-Admin static assets")
    require("location ~* ^/static/.+" in server_config, "reviewed pages require their non-admin static assets")
    require("location = /" in server_config, "the audited information root must be allowed explicitly")
    require("^/past-projects/[0-9a-f]{8}" in server_config, "the audited UUID detail route is missing")


def validate_nginx_policy() -> None:
    server_config = NGINX_SERVER_PATH.read_text(encoding="utf-8")
    uwsgi_config = NGINX_UWSGI_PATH.read_text(encoding="utf-8")
    _validate_private_server(server_config)
    _validate_uwsgi_snippet(uwsgi_config)
    _validate_route_parity(server_config)


def main() -> int:
    template = load_template(TEMPLATE_PATH)
    validate_network(template)
    validate_secret(template)
    validate_cloudfront(template)
    validate_outputs(template)
    validate_nginx_policy()
    validate_monitoring(load_template(MONITORING_TEMPLATE_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
