from __future__ import annotations

from typing import Any

from .template import require, resource


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
