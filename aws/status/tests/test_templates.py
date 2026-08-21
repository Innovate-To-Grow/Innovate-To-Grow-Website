from __future__ import annotations

from pathlib import Path

import yaml

STATUS_DIR = Path(__file__).resolve().parents[1]


class IntrinsicLoader(yaml.SafeLoader):
    pass


def _intrinsic(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


IntrinsicLoader.add_multi_constructor("!", _intrinsic)


def load(name):
    return yaml.load((STATUS_DIR / name).read_text(), Loader=IntrinsicLoader)


def test_certificate_template_has_only_certificate_output_contract():
    template = load("certificate-template.yaml")

    assert template["Rules"]["CloudFrontCertificateRegion"]["Assertions"][0]["Assert"] == [
        "AWS::Region",
        "us-east-1",
    ]
    assert "StatusCertificate" in template["Resources"]
    assert set(template["Outputs"]) == {"CertificateArn"}
    assert template["Resources"]["StatusCertificate"]["Properties"]["ValidationMethod"] == "DNS"


def test_main_stack_security_region_and_output_contract():
    template = load("template.yaml")
    resources = template["Resources"]

    assert template["Rules"]["StatusServiceRegion"]["Assertions"][0]["Assert"] == [
        "AWS::Region",
        "us-west-2",
    ]
    assert template["Globals"]["Function"]["Runtime"] == "python3.13"
    assert set(template["Globals"]["Function"]["Environment"]["Variables"]) == {"STATUS_TABLE_NAME"}
    assert resources["StatusSiteBucket"]["Properties"]["VersioningConfiguration"]["Status"] == "Enabled"
    assert all(resources["StatusSiteBucket"]["Properties"]["PublicAccessBlockConfiguration"].values())
    assert (
        resources["StatusOriginAccessControl"]["Properties"]["OriginAccessControlConfig"]["SigningBehavior"] == "always"
    )
    assert (
        resources["StatusOriginAccessControl"]["Properties"]["OriginAccessControlConfig"]["SigningProtocol"] == "sigv4"
    )
    assert resources["StatusTable"]["Properties"]["PointInTimeRecoverySpecification"]["PointInTimeRecoveryEnabled"]
    assert resources["StatusTable"]["Properties"]["TimeToLiveSpecification"]["AttributeName"] == "expiresAt"
    assert resources["InternalReadRoute"]["Properties"]["AuthorizationType"] == "AWS_IAM"
    assert resources["StatusApiStage"]["Properties"]["StageName"] == "prod"
    assert (
        "<aws.scheduler.scheduled-time>"
        in resources["ProbeFunction"]["Properties"]["Events"]["FiveMinuteSchedule"]["Properties"]["Input"]
    )
    assert set(template["Outputs"]) == {
        "SiteBucketName",
        "DistributionId",
        "PublicUrl",
        "PublicApiUrl",
        "InternalApiUrl",
        "ProbeFunctionName",
    }


def test_alarms_have_no_actions_and_logs_are_sanitized_retained_30_days():
    resources = load("template.yaml")["Resources"]
    alarms = [resource for resource in resources.values() if resource["Type"] == "AWS::CloudWatch::Alarm"]
    assert alarms
    assert all(
        not set(resource["Properties"]) & {"AlarmActions", "OKActions", "InsufficientDataActions"}
        for resource in alarms
    )

    log_groups = [resource for resource in resources.values() if resource["Type"] == "AWS::Logs::LogGroup"]
    assert log_groups
    assert all(resource["Properties"]["RetentionInDays"] == 30 for resource in log_groups)
    assert all(resource["DeletionPolicy"] == "Retain" for resource in log_groups)
    access_format = resources["StatusApiStage"]["Properties"]["AccessLogSettings"]["Format"]
    assert "requestId" in access_format
    assert not any(
        secret_field in access_format.lower() for secret_field in ("header", "body", "identity", "errormessage")
    )


def test_asset_retirement_is_tag_gated_and_api_cache_keeps_stale_fallback():
    resources = load("template.yaml")["Resources"]
    lifecycle = resources["StatusSiteBucket"]["Properties"]["LifecycleConfiguration"]["Rules"]
    retirement = next(rule for rule in lifecycle if rule["Id"] == "RemoveRetiredHashedAssets")

    assert retirement["Prefix"] == "assets/"
    assert retirement["TagFilters"] == [{"Key": "status-retire", "Value": "true"}]
    assert retirement["ExpirationInDays"] == 30
    cache = resources["StatusApiCachePolicy"]["Properties"]["CachePolicyConfig"]
    assert cache["DefaultTTL"] == 60
    assert cache["MaxTTL"] >= 960


def test_disabled_html_cache_does_not_vary_on_compression_headers():
    resources = load("template.yaml")["Resources"]
    cache = resources["StatusNoCachePolicy"]["Properties"]["CachePolicyConfig"]

    assert cache["MinTTL"] == cache["DefaultTTL"] == cache["MaxTTL"] == 0
    parameters = cache["ParametersInCacheKeyAndForwardedToOrigin"]
    assert parameters["EnableAcceptEncodingBrotli"] is False
    assert parameters["EnableAcceptEncodingGzip"] is False


def test_public_and_internal_dynamodb_read_permissions_are_partition_isolated():
    resources = load("template.yaml")["Resources"]
    public_statements = resources["PublicReadFunction"]["Properties"]["Policies"][0]["Statement"]
    internal_statement = resources["InternalReadFunction"]["Properties"]["Policies"][0]["Statement"][0]

    public_conditions = str([statement.get("Condition", {}) for statement in public_statements])
    assert "PUBLIC" in public_conditions
    assert "COMPONENT#*" in public_conditions
    assert "INCIDENT#*" in public_conditions
    assert "INCIDENTS" in public_conditions
    assert "INTERNAL" not in public_conditions
    assert internal_statement["Condition"]["ForAllValues:StringEquals"]["dynamodb:LeadingKeys"] == ["INTERNAL"]


def test_runtime_wildcards_are_isolated_and_region_limited():
    resources = load("template.yaml")["Resources"]
    statements = resources["ProbeFunction"]["Properties"]["Policies"][0]["Statement"]
    by_sid = {statement["Sid"]: statement for statement in statements}

    assert by_sid["ExistingTargetHealthRead"] == {
        "Sid": "ExistingTargetHealthRead",
        "Effect": "Allow",
        "Action": "elasticloadbalancing:DescribeTargetHealth",
        "Resource": "*",
        "Condition": {"StringEquals": {"aws:RequestedRegion": "AWS::Region"}},
    }
    assert by_sid["ExistingAmplifyJobList"] == {
        "Sid": "ExistingAmplifyJobList",
        "Effect": "Allow",
        "Action": "amplify:ListJobs",
        "Resource": "*",
        "Condition": {"StringEquals": {"aws:RequestedRegion": "AWS::Region"}},
    }


def test_amplify_branch_and_alarm_reads_use_exact_resources():
    resources = load("template.yaml")["Resources"]
    statements = resources["ProbeFunction"]["Properties"]["Policies"][0]["Statement"]
    by_sid = {statement["Sid"]: statement for statement in statements}

    amplify_read = by_sid["ExistingAmplifyRead"]
    assert amplify_read["Action"] == "amplify:GetBranch"
    assert amplify_read["Resource"] == [
        "arn:${AWS::Partition}:amplify:${AWS::Region}:${AWS::AccountId}:apps/${ProductionAmplifyAppId}/branches/${ProductionAmplifyBranch}",
        "arn:${AWS::Partition}:amplify:${AWS::Region}:${AWS::AccountId}:apps/${DemoAmplifyAppId}/branches/${DemoAmplifyBranch}",
    ]

    alarm_read = by_sid["StatusAlarmRead"]
    assert alarm_read["Action"] == "cloudwatch:DescribeAlarms"
    assert alarm_read["Resource"] == [
        f"arn:${{AWS::Partition}}:cloudwatch:${{AWS::Region}}:${{AWS::AccountId}}:alarm:${{AWS::StackName}}-{suffix}"
        for suffix in (
            "ProbeFunctionErrors",
            "ProbeMissing",
            "PublicApi5xx",
            "DynamoThrottles",
            "SchedulerDlqMessages",
        )
    ]
