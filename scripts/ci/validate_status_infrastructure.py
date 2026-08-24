#!/usr/bin/env python3
"""Assert security and architecture invariants for the two status stacks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAIN_TEMPLATE = REPOSITORY_ROOT / "aws" / "status" / "template.yaml"
CERTIFICATE_TEMPLATE = REPOSITORY_ROOT / "aws" / "status" / "certificate-template.yaml"


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


def load_template(path: Path) -> dict[str, Any]:
    template = yaml.load(path.read_text(encoding="utf-8"), Loader=CloudFormationLoader)
    if not isinstance(template, dict):
        raise AssertionError(f"{path} is not a CloudFormation mapping")
    return template


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def resource(template: dict[str, Any], logical_id: str, expected_type: str) -> dict[str, Any]:
    value = template.get("Resources", {}).get(logical_id)
    require(isinstance(value, dict), f"missing resource {logical_id}")
    require(value.get("Type") == expected_type, f"{logical_id} must be {expected_type}")
    return value


def values(value: str | list[str]) -> set[str]:
    return {value} if isinstance(value, str) else set(value)


def validate_certificate_stack(template: dict[str, Any]) -> None:
    certificate_rule = template.get("Rules", {}).get("CloudFrontCertificateRegion", {})
    require(
        certificate_rule.get("Assertions", [{}])[0].get("Assert")
        == {"!Equals": [{"!Ref": "AWS::Region"}, "us-east-1"]},
        "the certificate stack must reject regions other than us-east-1",
    )
    resources = template.get("Resources", {})
    require(
        {item.get("Type") for item in resources.values()} == {"AWS::CertificateManager::Certificate"},
        "the us-east-1 stack may own only ACM certificate resources",
    )
    certificate = resource(template, "StatusCertificate", "AWS::CertificateManager::Certificate")
    properties = certificate["Properties"]
    require(properties.get("ValidationMethod") == "DNS", "status certificate must use DNS validation")
    validation = properties.get("DomainValidationOptions", [])
    require(len(validation) == 1, "status certificate must have one Route53 validation option")
    require("HostedZoneId" in validation[0], "certificate validation must reference the existing hosted zone")
    require(
        template.get("Outputs", {}).get("CertificateArn", {}).get("Value") == {"!Ref": "StatusCertificate"},
        "certificate stack must output CertificateArn",
    )


def validate_site_bucket(template: dict[str, Any]) -> None:
    status_rule = template.get("Rules", {}).get("StatusServiceRegion", {})
    require(
        status_rule.get("Assertions", [{}])[0].get("Assert") == {"!Equals": [{"!Ref": "AWS::Region"}, "us-west-2"]},
        "the main status stack must reject regions other than us-west-2",
    )
    bucket = resource(template, "StatusSiteBucket", "AWS::S3::Bucket")
    require(bucket.get("DeletionPolicy") == "Retain", "status site bucket must be retained on stack deletion")
    require(bucket.get("UpdateReplacePolicy") == "Retain", "replacement status site bucket must be retained")
    properties = bucket["Properties"]
    require(properties.get("VersioningConfiguration", {}).get("Status") == "Enabled", "site bucket must be versioned")
    public_block = properties.get("PublicAccessBlockConfiguration", {})
    for key in ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"):
        require(public_block.get(key) is True, f"site bucket must enable {key}")
    require(bool(properties.get("BucketEncryption")), "site bucket must enable server-side encryption")
    lifecycle = properties.get("LifecycleConfiguration", {}).get("Rules", [])
    retirement_rules = [
        rule
        for rule in lifecycle
        if rule.get("Prefix") == "assets/"
        and any(
            tag.get("Key") == "status-retire" and str(tag.get("Value")).lower() == "true"
            for tag in rule.get("TagFilters", [])
        )
    ]
    require(retirement_rules, "hashed status assets need tag-scoped delayed cleanup")
    require(
        all(rule.get("ExpirationInDays", 0) >= 30 for rule in retirement_rules),
        "retired hash assets must remain available for at least 30 days",
    )
    require(
        any(rule.get("NoncurrentVersionExpiration") for rule in lifecycle),
        "noncurrent site versions need delayed cleanup",
    )

    policy = resource(template, "StatusSiteBucketPolicy", "AWS::S3::BucketPolicy")
    statements = policy["Properties"]["PolicyDocument"]["Statement"]
    allow = [statement for statement in statements if statement.get("Effect") == "Allow"]
    require(len(allow) == 1, "site bucket policy must contain one read-only allow")
    require(values(allow[0]["Action"]) == {"s3:GetObject"}, "site bucket policy may allow only s3:GetObject")
    require(
        allow[0].get("Principal") == {"Service": "cloudfront.amazonaws.com"},
        "site bucket policy may allow only the CloudFront service principal",
    )
    require("Condition" in allow[0], "CloudFront bucket access must be scoped to the distribution ARN")


def validate_data_and_scheduler(template: dict[str, Any]) -> None:
    table = resource(template, "StatusTable", "AWS::DynamoDB::Table")
    require(table.get("DeletionPolicy") == "Retain", "status history table must be retained")
    require(table.get("UpdateReplacePolicy") == "Retain", "replacement status history table must be retained")
    properties = table["Properties"]
    require(properties.get("BillingMode") == "PAY_PER_REQUEST", "status table must use on-demand billing")
    require(
        properties.get("PointInTimeRecoverySpecification", {}).get("PointInTimeRecoveryEnabled") is True,
        "status table must enable PITR",
    )
    require(properties.get("SSESpecification", {}).get("SSEEnabled") is True, "status table must enable encryption")
    require(properties.get("TimeToLiveSpecification", {}).get("Enabled") is True, "status table must enable TTL")

    dlq = resource(template, "SchedulerDlq", "AWS::SQS::Queue")
    require(dlq["Properties"].get("SqsManagedSseEnabled") is True, "scheduler DLQ must be encrypted")
    probe = resource(template, "ProbeFunction", "AWS::Serverless::Function")
    schedule = probe["Properties"].get("Events", {}).get("FiveMinuteSchedule", {})
    require(schedule.get("Type") == "ScheduleV2", "probe must use EventBridge Scheduler")
    schedule_properties = schedule.get("Properties", {})
    require(schedule_properties.get("ScheduleExpression") == "rate(5 minutes)", "probe must run every five minutes")
    require("DeadLetterConfig" in schedule_properties, "probe scheduler must use the encrypted DLQ")
    require(
        "<aws.scheduler.scheduled-time>" in str(schedule_properties.get("Input", "")),
        "scheduler must pass its stable scheduled-time token for slot idempotency",
    )
    retry = schedule_properties.get("RetryPolicy", {})
    require(retry.get("MaximumRetryAttempts", 99) <= 2, "scheduler retries must be finite and limited")


def validate_exact_resource_parameters(template: dict[str, Any]) -> None:
    parameters = template.get("Parameters", {})
    exact_parameters = {
        "BackendTaskRoleName",
        "EcsClusterName",
        "ProductionEcsService",
        "DemoEcsService",
        "ArchiveEcsService",
        "ProductionTargetGroupArn",
        "DemoTargetGroupArn",
        "ArchiveTargetGroupArn",
        "RdsInstanceId",
        "ProductionAssetsBucket",
        "DemoAssetsBucket",
        "ProductionAmplifyAppId",
        "DemoAmplifyAppId",
        "ProductionAmplifyBranch",
        "DemoAmplifyBranch",
    }
    for name in exact_parameters:
        pattern = str(parameters.get(name, {}).get("AllowedPattern", ""))
        require(pattern.startswith("^") and pattern.endswith("$"), f"{name} must use an anchored AllowedPattern")
        for unsafe in ("*", "resource*", "targetgroup/*", "?", "[resource]"):
            require(re.fullmatch(pattern, unsafe) is None, f"{name} must reject wildcard input")

    for name in ("ProductionTargetGroupArn", "DemoTargetGroupArn", "ArchiveTargetGroupArn"):
        pattern = str(parameters[name]["AllowedPattern"])
        require("elasticloadbalancing:us-west-2:" in pattern, f"{name} must be pinned to us-west-2")
        require("targetgroup/" in pattern and "{16}$" in pattern, f"{name} must match one complete target group ARN")


def validate_api_and_cloudfront(template: dict[str, Any]) -> None:
    oac = resource(template, "StatusOriginAccessControl", "AWS::CloudFront::OriginAccessControl")
    oac_config = oac["Properties"]["OriginAccessControlConfig"]
    require(oac_config.get("SigningBehavior") == "always", "CloudFront OAC must sign every S3 request")
    require(oac_config.get("SigningProtocol") == "sigv4", "CloudFront OAC must use SigV4")
    headers = resource(template, "StatusSecurityHeaders", "AWS::CloudFront::ResponseHeadersPolicy")
    require(
        "ContentSecurityPolicy" in headers["Properties"]["ResponseHeadersPolicyConfig"]["SecurityHeadersConfig"],
        "CloudFront must apply a Content Security Policy",
    )
    distribution = resource(template, "StatusDistribution", "AWS::CloudFront::Distribution")
    config = distribution["Properties"]["DistributionConfig"]
    require(config.get("IPV6Enabled") is True, "CloudFront must enable IPv6 for the A/AAAA aliases")
    require(config.get("DefaultRootObject") == "index.html", "CloudFront default root must be index.html")
    viewer_certificate = config.get("ViewerCertificate", {})
    require(
        viewer_certificate.get("AcmCertificateArn") == {"!Ref": "CertificateArn"},
        "CloudFront must use the separately deployed us-east-1 certificate",
    )
    origins = {origin["Id"]: origin for origin in config.get("Origins", [])}
    require("OriginAccessControlId" in origins.get("status-site", {}), "S3 origin must use OAC")
    require(
        config.get("DefaultCacheBehavior", {}).get("TargetOriginId") == "status-site",
        "the default CloudFront origin must be the private S3 bucket",
    )
    api_behaviors = [item for item in config.get("CacheBehaviors", []) if item.get("PathPattern") == "api/status"]
    require(len(api_behaviors) == 1, "CloudFront must forward only /api/status to API Gateway")
    require(api_behaviors[0].get("TargetOriginId") == "status-api", "public API behavior must target API Gateway")
    require(
        not any(item.get("PathPattern") == "internal/status" for item in config.get("CacheBehaviors", [])),
        "the IAM-protected internal route must not be exposed through CloudFront",
    )
    api_cache = resource(template, "StatusApiCachePolicy", "AWS::CloudFront::CachePolicy")
    api_cache_config = api_cache["Properties"]["CachePolicyConfig"]
    require(api_cache_config.get("DefaultTTL") == 60, "public status API cache must default to 60 seconds")
    require(
        api_cache_config.get("MaxTTL") == 960,
        "public API cache max TTL must permit the 15-minute stale-if-error fallback",
    )
    require(api_cache_config.get("MinTTL") == 0, "public status API cache must permit uncached error responses")

    dns_a = resource(template, "StatusDnsA", "AWS::Route53::RecordSet")
    dns_aaaa = resource(template, "StatusDnsAAAA", "AWS::Route53::RecordSet")
    require(dns_a["Properties"].get("Type") == "A", "status domain must publish a Route53 A alias")
    require(dns_aaaa["Properties"].get("Type") == "AAAA", "status domain must publish a Route53 AAAA alias")
    for record in (dns_a, dns_aaaa):
        require(
            record["Properties"].get("AliasTarget", {}).get("DNSName") == {"!GetAtt": "StatusDistribution.DomainName"},
            "status DNS aliases must target the CloudFront distribution",
        )

    stage = resource(template, "StatusApiStage", "AWS::ApiGatewayV2::Stage")
    require(stage["Properties"].get("StageName") == "prod", "status API must use the explicit prod stage")
    public_route = resource(template, "PublicReadRoute", "AWS::ApiGatewayV2::Route")
    internal_route = resource(template, "InternalReadRoute", "AWS::ApiGatewayV2::Route")
    require(public_route["Properties"].get("RouteKey") == "GET /api/status", "public route must be GET /api/status")
    require(public_route["Properties"].get("AuthorizationType") == "NONE", "public status route must be unsigned")
    require(
        internal_route["Properties"].get("RouteKey") == "GET /internal/status",
        "internal route must be GET /internal/status",
    )
    require(internal_route["Properties"].get("AuthorizationType") == "AWS_IAM", "internal route must require IAM")

    invoke_policy = resource(template, "BackendInternalStatusInvokePolicy", "AWS::IAM::Policy")
    statements = invoke_policy["Properties"]["PolicyDocument"]["Statement"]
    require(len(statements) == 1, "backend task role must receive one status statement")
    statement = statements[0]
    require(values(statement.get("Action", [])) == {"execute-api:Invoke"}, "backend role may only invoke API Gateway")
    invoke_resource = statement.get("Resource")
    require(
        isinstance(invoke_resource, dict)
        and str(invoke_resource.get("!Sub", "")).endswith("/prod/GET/internal/status"),
        "backend role invoke permission must be exact to GET /prod/internal/status",
    )


def validate_observability_and_iam(template: dict[str, Any]) -> None:
    resources = template.get("Resources", {})
    require(
        not any(item.get("Type") in {"AWS::SNS::Topic", "AWS::SNS::Subscription"} for item in resources.values()),
        "status alarms must not create notification actions",
    )
    alarms = [item for item in resources.values() if item.get("Type") == "AWS::CloudWatch::Alarm"]
    require(bool(alarms), "status stack must define runtime alarms")
    for alarm in alarms:
        properties = alarm.get("Properties", {})
        for action_key in ("AlarmActions", "OKActions", "InsufficientDataActions"):
            require(not properties.get(action_key), f"status alarms must not set {action_key}")
    resource(template, "StatusDashboard", "AWS::CloudWatch::Dashboard")

    log_groups = [item for item in resources.values() if item.get("Type") == "AWS::Logs::LogGroup"]
    require(len(log_groups) >= 3, "each status Lambda needs an explicit log group")
    require(
        all(item.get("Properties", {}).get("RetentionInDays") == 30 for item in log_groups),
        "all status log groups must retain logs for 30 days",
    )

    function_resources = {
        logical_id: item for logical_id, item in resources.items() if item.get("Type") == "AWS::Serverless::Function"
    }
    functions = list(function_resources.values())
    require(len(functions) == 3, "status stack must have exactly three Lambda functions")

    monitoring_environment = {
        "ECS_CLUSTER_NAME",
        "PRODUCTION_ECS_SERVICE",
        "DEMO_ECS_SERVICE",
        "ARCHIVE_ECS_SERVICE",
        "PRODUCTION_TARGET_GROUP_ARN",
        "DEMO_TARGET_GROUP_ARN",
        "ARCHIVE_TARGET_GROUP_ARN",
        "RDS_INSTANCE_ID",
        "PRODUCTION_ASSETS_BUCKET",
        "DEMO_ASSETS_BUCKET",
        "PRODUCTION_AMPLIFY_APP_ID",
        "DEMO_AMPLIFY_APP_ID",
        "PRODUCTION_AMPLIFY_BRANCH",
        "DEMO_AMPLIFY_BRANCH",
        "STATUS_ALARM_PREFIX",
    }
    global_environment = template.get("Globals", {}).get("Function", {}).get("Environment", {}).get("Variables", {})
    require(
        not (monitoring_environment & set(global_environment)),
        "monitoring resource identifiers must not be inherited by public/internal read functions",
    )
    probe_environment = (
        resource(template, "ProbeFunction", "AWS::Serverless::Function")
        .get("Properties", {})
        .get("Environment", {})
        .get("Variables", {})
    )
    require(
        monitoring_environment <= set(probe_environment),
        "the probe alone must receive the monitoring resource identifiers",
    )
    for logical_id in ("PublicReadFunction", "InternalReadFunction"):
        read_environment = (
            resource(template, logical_id, "AWS::Serverless::Function")
            .get("Properties", {})
            .get("Environment", {})
            .get("Variables", {})
        )
        require(
            not (monitoring_environment & set(read_environment)),
            f"{logical_id} must not receive monitoring resource identifiers",
        )

    public_statements = {
        statement["Sid"]: statement
        for statement in resource(template, "PublicReadFunction", "AWS::Serverless::Function")["Properties"][
            "Policies"
        ][0]["Statement"]
    }
    public_get_keys = public_statements["PublicProjectionGet"]["Condition"]["ForAllValues:StringLike"][
        "dynamodb:LeadingKeys"
    ]
    public_query_keys = public_statements["PublicProjectionTableQuery"]["Condition"]["ForAllValues:StringLike"][
        "dynamodb:LeadingKeys"
    ]
    public_index_keys = public_statements["PublicProjectionIncidentIndexQuery"]["Condition"][
        "ForAllValues:StringEquals"
    ]["dynamodb:LeadingKeys"]
    require(
        set(public_get_keys) == {"PUBLIC", "COMPONENT#*", "INCIDENT#*"},
        "public GetItem access must be limited to public/component/incident partitions",
    )
    require(
        set(public_query_keys) == {"COMPONENT#*", "INCIDENT#*"},
        "public table queries must be limited to component and incident partitions",
    )
    require(public_index_keys == ["INCIDENTS"], "public GSI queries must be limited to the incident index partition")
    require("INTERNAL" not in str(public_statements), "the public Lambda must never read the internal partition")

    internal_statement = resource(template, "InternalReadFunction", "AWS::Serverless::Function")["Properties"][
        "Policies"
    ][0]["Statement"][0]
    require(
        internal_statement["Condition"]["ForAllValues:StringEquals"]["dynamodb:LeadingKeys"] == ["INTERNAL"],
        "the internal Lambda must read only the internal snapshot partition",
    )

    probe_statements = {
        statement["Sid"]: statement
        for statement in resource(template, "ProbeFunction", "AWS::Serverless::Function")["Properties"]["Policies"][0][
            "Statement"
        ]
    }
    requested_region_condition = {"StringEquals": {"aws:RequestedRegion": {"!Ref": "AWS::Region"}}}
    for sid, action in (
        ("ExistingTargetHealthRead", "elasticloadbalancing:DescribeTargetHealth"),
        ("ExistingAmplifyJobList", "amplify:ListJobs"),
    ):
        statement = probe_statements[sid]
        require(values(statement.get("Action", [])) == {action}, f"{sid} must grant only {action}")
        require(statement.get("Resource") == "*", f"{sid} must use the service-required wildcard resource")
        require(
            statement.get("Condition") == requested_region_condition,
            f"{sid} must be limited to the deployment region",
        )

    amplify_branch_read = probe_statements["ExistingAmplifyRead"]
    require(
        values(amplify_branch_read.get("Action", [])) == {"amplify:GetBranch"},
        "Amplify branch access must grant only GetBranch",
    )
    expected_branch_resources = {
        "arn:${AWS::Partition}:amplify:${AWS::Region}:${AWS::AccountId}:apps/${ProductionAmplifyAppId}/branches/${ProductionAmplifyBranch}",
        "arn:${AWS::Partition}:amplify:${AWS::Region}:${AWS::AccountId}:apps/${DemoAmplifyAppId}/branches/${DemoAmplifyBranch}",
    }
    branch_resources = amplify_branch_read.get("Resource", [])
    require(
        isinstance(branch_resources, list)
        and len(branch_resources) == len(expected_branch_resources)
        and all(isinstance(item, dict) and set(item) == {"!Sub"} for item in branch_resources),
        "Amplify GetBranch resources must be canonical !Sub ARN entries only",
    )
    actual_branch_resources = {str(item.get("!Sub", "")) for item in branch_resources if isinstance(item, dict)}
    require(
        actual_branch_resources == expected_branch_resources,
        "Amplify GetBranch must be limited to the two configured branches",
    )

    alarm_read = probe_statements["StatusAlarmRead"]
    require(
        values(alarm_read.get("Action", [])) == {"cloudwatch:DescribeAlarms"},
        "the alarm statement must grant only DescribeAlarms",
    )
    alarm_names = {str(alarm.get("Properties", {}).get("AlarmName", {}).get("!Sub", "")) for alarm in alarms}
    expected_alarm_resources = {
        f"arn:${{AWS::Partition}}:cloudwatch:${{AWS::Region}}:${{AWS::AccountId}}:alarm:{name}" for name in alarm_names
    }
    alarm_resources = alarm_read.get("Resource", [])
    require(
        isinstance(alarm_resources, list)
        and len(alarm_resources) == len(expected_alarm_resources)
        and all(isinstance(item, dict) and set(item) == {"!Sub"} for item in alarm_resources),
        "DescribeAlarms resources must be canonical !Sub ARN entries only",
    )
    actual_alarm_resources = {str(item.get("!Sub", "")) for item in alarm_resources if isinstance(item, dict)}
    require(
        len(alarm_names) == 5 and actual_alarm_resources == expected_alarm_resources,
        "DescribeAlarms must be limited to the five exact status-stack alarms",
    )

    allowed_wildcard_resources = {
        ("ProbeFunction", "ExistingEcsRuntimeRead"): {
            "ecs:DescribeServices",
            "ecs:ListTasks",
            "ecs:DescribeTasks",
        },
        ("ProbeFunction", "ExistingTaskDefinitionRead"): {"ecs:DescribeTaskDefinition"},
        ("ProbeFunction", "ExistingTargetHealthRead"): {"elasticloadbalancing:DescribeTargetHealth"},
        ("ProbeFunction", "ExistingAmplifyJobList"): {"amplify:ListJobs"},
        ("ProbeFunction", "StatusMetricWrite"): {"cloudwatch:PutMetricData"},
    }
    observed_wildcard_resources: set[tuple[str, str]] = set()
    for logical_id, function in function_resources.items():
        for policy in function.get("Properties", {}).get("Policies", []):
            for statement in policy.get("Statement", []):
                actions = values(statement.get("Action", []))
                require("*" not in actions, "status Lambda policies must not grant wildcard actions")
                resource_value = statement.get("Resource")
                require(
                    not (isinstance(resource_value, list) and "*" in resource_value),
                    f"{logical_id}/{statement.get('Sid', '')} must not mix wildcard and scoped resources",
                )
                uses_wildcard_resource = resource_value == "*"
                if uses_wildcard_resource:
                    key = (logical_id, str(statement.get("Sid", "")))
                    require(
                        key in allowed_wildcard_resources and actions == allowed_wildcard_resources[key],
                        f"unexpected wildcard-resource status permissions in {key}: {sorted(actions)}",
                    )
                    observed_wildcard_resources.add(key)
    require(
        observed_wildcard_resources == set(allowed_wildcard_resources),
        "status wildcard-resource statements must match the reviewed allowlist exactly",
    )


def validate_outputs(template: dict[str, Any]) -> None:
    expected = {
        "SiteBucketName",
        "DistributionId",
        "PublicUrl",
        "PublicApiUrl",
        "InternalApiUrl",
        "ProbeFunctionName",
    }
    require(expected <= set(template.get("Outputs", {})), "main stack is missing required deployment outputs")
    outputs = template["Outputs"]
    require(
        outputs["PublicApiUrl"].get("Value") == {"!Sub": "https://${StatusDomainName}/api/status"},
        "PublicApiUrl must be the same-origin CloudFront route",
    )
    require(
        str(outputs["InternalApiUrl"].get("Value", {}).get("!Sub", "")).endswith("/prod/internal/status"),
        "InternalApiUrl must be the direct IAM-protected prod-stage route",
    )


def main() -> int:
    certificate = load_template(CERTIFICATE_TEMPLATE)
    main_template = load_template(MAIN_TEMPLATE)
    validate_certificate_stack(certificate)
    validate_site_bucket(main_template)
    validate_data_and_scheduler(main_template)
    validate_exact_resource_parameters(main_template)
    validate_api_and_cloudfront(main_template)
    validate_observability_and_iam(main_template)
    validate_outputs(main_template)
    print("Status infrastructure security invariants passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
