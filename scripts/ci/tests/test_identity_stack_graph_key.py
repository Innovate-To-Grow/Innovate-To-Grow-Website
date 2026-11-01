"""Static checks for the Microsoft Graph certificate-key secret and its narrow grant in the identity stack."""

import ast
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STACK = json.loads((ROOT / "aws/cicd/identity-stack.json").read_text())
RESOURCES = STACK["Resources"]
SECRET_REF = {"Ref": "GraphCertificateKeySecret"}
TASK_ROLE_ARN = "arn:aws:iam::394167325273:role/ecsTaskRole"
STORE_SETTINGS = ROOT / "src/config/settings/base/integrations/credential_store/__init__.py"
STORE_BACKEND = ROOT / "src/apps/core/services/credential_store/secrets_manager.py"


def _statements(document):
    statements = document["Statement"]
    return statements if isinstance(statements, list) else [statements]


def _actions(statement):
    actions = statement["Action"]
    return [actions] if isinstance(actions, str) else actions


def _setting(name):
    tree = ast.parse(STORE_SETTINGS.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(target, "id", "") == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not a literal in {STORE_SETTINGS}")


class GraphCertificateKeySecretTests(unittest.TestCase):
    def test_secret_is_created_empty_retained_and_named_as_the_backend_expects(self):
        secret = RESOURCES["GraphCertificateKeySecret"]
        self.assertEqual(secret["Type"], "AWS::SecretsManager::Secret")
        self.assertEqual(secret["DeletionPolicy"], "Retain")
        self.assertEqual(secret["UpdateReplacePolicy"], "Retain")
        self.assertNotIn("SecretString", secret["Properties"])
        self.assertNotIn("GenerateSecretString", secret["Properties"])
        self.assertEqual(
            secret["Properties"]["Name"], _setting("CREDENTIAL_STORE_SECRETS")["microsoft_graph_certificate_key"]
        )
        self.assertFalse(secret["Properties"]["Name"].startswith("itg/backend/aws-credentials/"))
        self.assertEqual(STACK["Outputs"]["GraphCertificateKeySecretArn"], {"Value": SECRET_REF})

    def test_task_role_grant_is_exact_and_covers_every_call_the_backend_makes(self):
        policy = RESOURCES["ApplicationGraphCertificateKey"]["Properties"]
        self.assertEqual(policy["Roles"], ["ecsTaskRole"])
        allow, deny = _statements(policy["PolicyDocument"])
        self.assertEqual(allow["Effect"], "Allow")
        self.assertEqual(allow["Resource"], SECRET_REF)
        self.assertEqual(
            sorted(_actions(allow)),
            [
                "secretsmanager:DescribeSecret",
                "secretsmanager:GetSecretValue",
                "secretsmanager:PutSecretValue",
                "secretsmanager:UpdateSecretVersionStage",
            ],
        )
        called = re.findall(r'_call\(\s*"([a-z_]+)"', STORE_BACKEND.read_text())
        self.assertTrue(called)
        for operation in called:
            action = "secretsmanager:" + "".join(part.title() for part in operation.split("_"))
            self.assertIn(action, _actions(allow), operation)

        self.assertEqual(deny["Effect"], "Deny")
        self.assertEqual(deny["Resource"], SECRET_REF)
        required = {"DeleteSecret", "UpdateSecret", "RotateSecret", "PutResourcePolicy", "DeleteResourcePolicy"}
        self.assertLessEqual({f"secretsmanager:{action}" for action in required}, set(_actions(deny)))

    def test_resource_policy_denies_reads_and_writes_by_any_other_principal(self):
        policy = RESOURCES["GraphCertificateKeySecretPolicy"]
        self.assertEqual(policy["Type"], "AWS::SecretsManager::ResourcePolicy")
        properties = policy["Properties"]
        self.assertEqual(properties["SecretId"], SECRET_REF)
        self.assertIs(properties["BlockPublicPolicy"], True)
        denied = set()
        for statement in _statements(properties["ResourcePolicy"]):
            self.assertEqual(statement["Effect"], "Deny")
            self.assertEqual(statement["Principal"], "*")
            self.assertEqual(statement["Condition"], {"ArnNotEquals": {"aws:PrincipalArn": TASK_ROLE_ARN}})
            denied.update(_actions(statement))
        self.assertEqual(
            denied,
            {
                "secretsmanager:GetSecretValue",
                "secretsmanager:PutSecretValue",
                "secretsmanager:UpdateSecretVersionStage",
            },
        )
        # The principal exempted here is the role the backend deployer passes to ECS tasks.
        pass_role = next(
            statement
            for statement in _statements(RESOURCES["BackendDeployer"]["Properties"]["Policies"][0]["PolicyDocument"])
            if statement.get("Action") == "iam:PassRole"
        )
        self.assertIn(TASK_ROLE_ARN, pass_role["Resource"])

    def test_no_secrets_manager_wildcard_and_the_aws_credentials_grant_is_unchanged(self):
        for name, resource in RESOURCES.items():
            for document in _policy_documents(resource):
                for statement in _statements(document):
                    for action in _actions(statement):
                        self.assertNotRegex(action, r"^(\*|secretsmanager:.*\*.*)$", name)
        aws_credentials = RESOURCES["ApplicationAwsCredentialsRead"]["Properties"]["PolicyDocument"]
        self.assertEqual(
            _statements(aws_credentials),
            [
                {
                    "Effect": "Allow",
                    "Action": ["secretsmanager:GetSecretValue"],
                    "Resource": "arn:aws:secretsmanager:us-west-2:394167325273:secret:itg/backend/aws-credentials/*",
                }
            ],
        )


def _policy_documents(resource):
    properties = resource.get("Properties", {})
    documents = [properties[key] for key in ("PolicyDocument", "ResourcePolicy") if key in properties]
    documents.extend(policy["PolicyDocument"] for policy in properties.get("Policies", []))
    return documents


if __name__ == "__main__":
    unittest.main()
