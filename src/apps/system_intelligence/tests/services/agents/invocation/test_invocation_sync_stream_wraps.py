import os
from unittest.mock import patch

from apps.core.models import AWSCredentialConfig
from apps.system_intelligence.services.agents import (
    _bedrock_litellm_credentials,
    _to_litellm_bedrock_model,
    invoke_system_intelligence_stream,
)
from apps.system_intelligence.services.agents.errors import SystemIntelligenceAgentError
from apps.system_intelligence.tests.services.agents.invocation.test_invocation import (
    _SystemIntelligenceAgentInvocationCase,
)


class SystemIntelligenceAgentInvocationTests(_SystemIntelligenceAgentInvocationCase):
    def test_sync_stream_wraps_bedrock_dns_error(self):
        async def failing_async_stream(*args, **kwargs):
            raise Exception(
                "litellm.ServiceUnavailableError: BedrockException - Cannot connect to host bedrock-runtime.us-west-2.amazonaws.com:443 ssl:<ssl.SSLContext object> [Could not contact DNS servers]"
            )
            yield {"type": "text", "chunk": "unreachable"}

        with patch(
            "apps.system_intelligence.services.agents._invoke_system_intelligence_stream_async",
            new=failing_async_stream,
        ):
            events = list(
                invoke_system_intelligence_stream(
                    [{"role": "user", "content": "Current"}],
                    chat_config=self.chat_config,
                    aws_config=self.aws_config,
                    model_id=self.chat_config.default_model_id,
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

    def test_litellm_model_adapter_normalizes_without_catalog_lookup(self):
        with patch(
            "apps.system_intelligence.services.bedrock.models.catalog.fetch_models_from_aws", side_effect=AssertionError
        ):
            self.assertEqual(
                _to_litellm_bedrock_model("us.anthropic.claude-sonnet-4-20250514-v1:0"),
                "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
            )
            self.assertEqual(
                _to_litellm_bedrock_model("bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0"),
                "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
            )

    def test_litellm_model_adapter_rejects_empty_model_id(self):
        with self.assertRaises(SystemIntelligenceAgentError):
            _to_litellm_bedrock_model("")

    def test_bedrock_credentials_are_passed_per_call_without_touching_os_environ(self):
        original = os.environ.get("AWS_ACCESS_KEY_ID")
        creds = _bedrock_litellm_credentials(self.aws_config)
        self.assertEqual(
            creds,
            {
                "aws_access_key_id": "test-key",
                "aws_secret_access_key": "test-secret",
                "aws_region_name": "us-west-2",
            },
        )
        # Credentials are returned for ModelSettings.extra_args, never written to env.
        self.assertEqual(os.environ.get("AWS_ACCESS_KEY_ID"), original)

    def test_bedrock_credentials_require_configured_aws(self):
        unconfigured = AWSCredentialConfig(name="empty", is_active=True)
        with self.assertRaises(SystemIntelligenceAgentError):
            _bedrock_litellm_credentials(unconfigured)
