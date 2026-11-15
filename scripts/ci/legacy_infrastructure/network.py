from __future__ import annotations

from typing import Any

from .template import require, resource


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
