"""Tests for bedrock converse / streaming / stream_parser / prepare / clients."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.test import SimpleTestCase, TestCase

from apps.system_intelligence.services.bedrock.clients.exceptions import BedrockError
from apps.system_intelligence.services.bedrock.clients.prepare import build_kwargs, prepare


def _client_error():
    return ClientError({"Error": {"Code": "Boom", "Message": "bad"}}, "Converse")


class FakeChatConfig:
    is_configured = True
    default_model_id = "anthropic.claude-3"
    max_tokens = 1024
    temperature = 0.5
    system_prompt = "You are helpful."


# ---------- prepare / build_kwargs ----------


class BuildKwargsTest(SimpleTestCase):
    def test_includes_system_and_tools(self):
        cfg = FakeChatConfig()
        with patch(
            "apps.system_intelligence.services.bedrock.clients.prepare.get_tool_definitions",
            return_value=[{"toolSpec": {"name": "x"}}],
        ):
            user = SimpleNamespace(is_authenticated=True, is_staff=True, is_active=True, is_superuser=True)
            kwargs = build_kwargs(cfg, "model-1", user=user)
        self.assertEqual(kwargs["modelId"], "model-1")
        self.assertEqual(kwargs["inferenceConfig"], {"maxTokens": 1024, "temperature": 0.5})
        self.assertEqual(kwargs["system"], [{"text": "You are helpful."}])
        self.assertIn("toolConfig", kwargs)

    def test_omits_system_and_tools_when_empty(self):
        cfg = FakeChatConfig()
        cfg.system_prompt = ""
        with patch("apps.system_intelligence.services.bedrock.clients.prepare.get_tool_definitions", return_value=[]):
            kwargs = build_kwargs(cfg, "model-1")
        self.assertNotIn("system", kwargs)
        self.assertNotIn("toolConfig", kwargs)


class PrepareTest(SimpleTestCase):
    def test_raises_when_chat_config_not_configured(self):
        bad_cfg = MagicMock()
        bad_cfg.is_configured = False
        with self.assertRaises(BedrockError) as cm:
            prepare([{"role": "user", "content": "hi"}], bad_cfg, MagicMock(), "m")
        self.assertIn("AI Chat is not configured", str(cm.exception))

    def test_loads_default_config_and_model_and_builds_messages(self):
        loaded = FakeChatConfig()
        with (
            patch(
                "apps.system_intelligence.services.bedrock.clients.prepare.SystemIntelligenceConfig.load",
                return_value=loaded,
            ),
            patch("apps.system_intelligence.services.bedrock.clients.prepare.get_client", return_value="CLIENT"),
            patch("apps.system_intelligence.services.bedrock.clients.prepare.get_tool_definitions", return_value=[]),
        ):
            client, messages, kwargs = prepare(
                [{"role": "user", "content": "hello"}],
                None,
                MagicMock(),
                None,
            )
        self.assertEqual(client, "CLIENT")
        self.assertEqual(messages, [{"role": "user", "content": [{"text": "hello"}]}])
        # model_id falls back to chat_config.default_model_id
        self.assertEqual(kwargs["modelId"], "anthropic.claude-3")


# ---------- clients ----------


class ClientsTest(TestCase):
    def test_get_aws_config_raises_when_unconfigured(self):
        from apps.system_intelligence.services.bedrock.clients import get_aws_config

        cfg = MagicMock()
        cfg.is_configured = False
        with self.assertRaises(BedrockError) as cm:
            get_aws_config(cfg)
        self.assertIn("AWS credentials are not configured", str(cm.exception))

    def test_get_aws_config_loads_default(self):
        from apps.system_intelligence.services.bedrock.clients import get_aws_config

        loaded = MagicMock()
        loaded.is_configured = True
        with patch(
            "apps.system_intelligence.services.bedrock.clients._aws.AWSCredentialConfig.load",
            return_value=loaded,
        ):
            self.assertIs(get_aws_config(None), loaded)

    def test_get_client_builds_runtime_client(self):
        from apps.system_intelligence.services.bedrock.clients import get_client

        cfg = MagicMock()
        cfg.is_configured = True
        cfg.region = "us-west-2"
        cfg.access_key_id = "AKIA"
        cfg.secret_access_key = "sek"
        cfg.credentials_secret_arn = ""
        with patch("apps.system_intelligence.services.bedrock.clients._aws.boto3.client", return_value="RT") as boto:
            self.assertEqual(get_client(cfg), "RT")
        boto.assert_called_once_with(
            "bedrock-runtime",
            region_name="us-west-2",
            aws_access_key_id="AKIA",
            aws_secret_access_key="sek",
        )

    def test_get_management_client_builds_bedrock_client(self):
        from apps.system_intelligence.services.bedrock.clients import get_management_client

        cfg = MagicMock()
        cfg.is_configured = True
        cfg.region = "eu-west-1"
        cfg.access_key_id = "AKIA"
        cfg.secret_access_key = "sek"
        cfg.credentials_secret_arn = ""
        with patch("apps.system_intelligence.services.bedrock.clients._aws.boto3.client", return_value="MGMT") as boto:
            self.assertEqual(get_management_client(cfg), "MGMT")
        boto.assert_called_once_with(
            "bedrock",
            region_name="eu-west-1",
            aws_access_key_id="AKIA",
            aws_secret_access_key="sek",
        )

    def test_get_cloudwatch_client_builds_cloudwatch_client(self):
        from apps.system_intelligence.services.bedrock.clients import get_cloudwatch_client

        cfg = MagicMock()
        cfg.is_configured = True
        cfg.region = "us-west-2"
        cfg.access_key_id = "AKIA"
        cfg.secret_access_key = "sek"
        cfg.credentials_secret_arn = ""
        with patch("apps.system_intelligence.services.bedrock.clients._aws.boto3.client", return_value="CW") as boto:
            self.assertEqual(get_cloudwatch_client(cfg), "CW")
        # Never Cost Explorer ("ce") -- CloudWatch reads only.
        boto.assert_called_once_with(
            "cloudwatch",
            region_name="us-west-2",
            aws_access_key_id="AKIA",
            aws_secret_access_key="sek",
        )


# ---------- converse (non-streaming) ----------


# ---------- stream_parser ----------


# ---------- streaming ----------
