from unittest.mock import patch

from django.test import TestCase
from google.adk.events import Event

from core.models import AWSCredentialConfig
from system_intelligence.models import SystemIntelligenceConfig
from system_intelligence.services.adk import (
    AGENT_NAME,
    SystemIntelligenceADKError,
    _to_litellm_bedrock_model,
    invoke_system_intelligence_stream,
)


class SystemIntelligenceADKInvocationTests(TestCase):
    def setUp(self):
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            system_prompt="Use tools.",
        )

    def test_sync_stream_wraps_bedrock_dns_error(self):
        async def failing_async_stream(*args, **kwargs):
            raise Exception(
                "litellm.ServiceUnavailableError: BedrockException - Cannot connect to host bedrock-runtime.us-west-2.amazonaws.com:443 ssl:<ssl.SSLContext object> [Could not contact DNS servers]"
            )
            yield Event(author=AGENT_NAME)

        with patch(
            "system_intelligence.services.adk._invoke_system_intelligence_stream_async", new=failing_async_stream
        ):
            events = list(
                invoke_system_intelligence_stream(
                    [{"role": "user", "content": "Current"}],
                    chat_config=self.chat_config,
                    aws_config=self.aws_config,
                    model_id=self.aws_config.default_model_id,
                    user_id="42",
                )
            )
        self.assertEqual(
            events,
            [
                {
                    "type": "error",
                    "error": "Unable to reach AWS Bedrock Runtime in us-west-2. Check network/DNS connectivity for the server and try again.",
                }
            ],
        )

    def test_sync_stream_loads_configs_before_entering_async_context(self):
        async def fake_async_stream(*args, **kwargs):
            self.assertEqual(kwargs["aws_config"], self.aws_config)
            self.assertEqual(kwargs["chat_config"].system_prompt, "Use tools.")
            self.assertEqual(kwargs["model_id"], self.aws_config.default_model_id)
            yield {"type": "text", "chunk": "Loaded"}

        with patch("system_intelligence.services.adk._invoke_system_intelligence_stream_async", new=fake_async_stream):
            events = list(invoke_system_intelligence_stream([{"role": "user", "content": "Current"}], user_id="42"))
        self.assertEqual(events, [{"type": "text", "chunk": "Loaded"}])

    def test_litellm_model_adapter_normalizes_without_catalog_lookup(self):
        with patch("core.services.bedrock.models.catalog.fetch_models_from_aws", side_effect=AssertionError):
            self.assertEqual(
                _to_litellm_bedrock_model("us.anthropic.claude-sonnet-4-20250514-v1:0"),
                "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
            )
            self.assertEqual(
                _to_litellm_bedrock_model("bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0"),
                "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
            )

    def test_litellm_model_adapter_rejects_empty_model_id(self):
        with self.assertRaises(SystemIntelligenceADKError):
            _to_litellm_bedrock_model("")
