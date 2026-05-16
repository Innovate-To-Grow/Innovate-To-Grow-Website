from django.test import SimpleTestCase
from google.adk.events import Event
from google.genai import types

from system_intelligence.models import SystemIntelligenceConfig
from system_intelligence.services.adk import (
    AGENT_NAME,
    _build_generate_content_config,
    _configure_litellm_bedrock_transport,
    _is_temperature_deprecated_error,
    _normalize_adk_event,
    _prefer_threaded_aiohttp_resolver,
    _StreamState,
    format_system_intelligence_error,
)


class SystemIntelligenceADKEventTests(SimpleTestCase):
    def test_generate_content_config_can_omit_temperature(self):
        chat_config = SystemIntelligenceConfig(temperature=0.3, max_tokens=123)
        self.assertEqual(_build_generate_content_config(chat_config, include_temperature=True).temperature, 0.3)
        without_temperature = _build_generate_content_config(chat_config, include_temperature=False)
        self.assertIsNone(without_temperature.temperature)
        self.assertEqual(without_temperature.max_output_tokens, 123)

    def test_temperature_deprecated_error_detection_checks_exception_chain(self):
        wrapped = RuntimeError("outer")
        wrapped.__cause__ = Exception("BedrockException: `temperature` is deprecated for this model.")
        self.assertTrue(_is_temperature_deprecated_error(wrapped))
        self.assertFalse(_is_temperature_deprecated_error(Exception("unrelated provider error")))

    def test_bedrock_dns_error_is_formatted_for_admin(self):
        raw = "litellm.ServiceUnavailableError: BedrockException - Cannot connect to host bedrock-runtime.us-west-2.amazonaws.com:443 ssl:<ssl.SSLContext object> [Could not contact DNS servers]"
        message = format_system_intelligence_error(raw)
        self.assertEqual(
            message,
            "Unable to reach AWS Bedrock Runtime in us-west-2. Check network/DNS connectivity for the server and try again.",
        )
        self.assertNotIn("litellm.ServiceUnavailableError", message)

    def test_threaded_aiohttp_resolver_is_preferred_for_litellm_bedrock(self):
        import aiohttp.connector
        import aiohttp.resolver

        original_connector = aiohttp.connector.DefaultResolver
        original_resolver = aiohttp.resolver.DefaultResolver
        self.addCleanup(setattr, aiohttp.connector, "DefaultResolver", original_connector)
        self.addCleanup(setattr, aiohttp.resolver, "DefaultResolver", original_resolver)
        aiohttp.connector.DefaultResolver = aiohttp.resolver.AsyncResolver
        aiohttp.resolver.DefaultResolver = aiohttp.resolver.AsyncResolver
        _prefer_threaded_aiohttp_resolver()
        self.assertIs(aiohttp.connector.DefaultResolver, aiohttp.resolver.ThreadedResolver)
        self.assertIs(aiohttp.resolver.DefaultResolver, aiohttp.resolver.ThreadedResolver)

    def test_litellm_aiohttp_transport_is_disabled_for_bedrock(self):
        import litellm

        original_disable = litellm.disable_aiohttp_transport
        original_use = litellm.use_aiohttp_transport
        self.addCleanup(setattr, litellm, "disable_aiohttp_transport", original_disable)
        self.addCleanup(setattr, litellm, "use_aiohttp_transport", original_use)
        litellm.disable_aiohttp_transport = False
        litellm.use_aiohttp_transport = True
        _configure_litellm_bedrock_transport()
        self.assertTrue(litellm.disable_aiohttp_transport)
        self.assertFalse(litellm.use_aiohttp_transport)

    def test_partial_and_final_text_events(self):
        state = _StreamState()
        first = Event(
            author=AGENT_NAME,
            partial=True,
            content=types.Content(role="model", parts=[types.Part.from_text(text="Hel")]),
        )
        second = Event(
            author=AGENT_NAME,
            partial=True,
            content=types.Content(role="model", parts=[types.Part.from_text(text="lo")]),
        )
        final = Event(
            author=AGENT_NAME,
            partial=False,
            content=types.Content(role="model", parts=[types.Part.from_text(text="Hello")]),
            usageMetadata=types.GenerateContentResponseUsageMetadata(
                promptTokenCount=3, candidatesTokenCount=4, totalTokenCount=7
            ),
        )
        self.assertEqual(_normalize_adk_event(first, state), [{"type": "text", "chunk": "Hel"}])
        self.assertEqual(_normalize_adk_event(second, state), [{"type": "text", "chunk": "lo"}])
        self.assertEqual(
            _normalize_adk_event(final, state),
            [{"type": "usage", "inputTokens": 3, "outputTokens": 4, "totalTokens": 7}],
        )

    def test_final_text_suffix_and_final_only_text(self):
        state = _StreamState()
        partial = Event(
            author=AGENT_NAME,
            partial=True,
            content=types.Content(role="model", parts=[types.Part.from_text(text="Hel")]),
        )
        final = Event(
            author=AGENT_NAME,
            partial=False,
            content=types.Content(role="model", parts=[types.Part.from_text(text="Hello")]),
        )
        self.assertEqual(_normalize_adk_event(partial, state), [{"type": "text", "chunk": "Hel"}])
        self.assertEqual(_normalize_adk_event(final, state), [{"type": "text", "chunk": "lo"}])
        self.assertEqual(_normalize_adk_event(final, _StreamState()), [{"type": "text", "chunk": "Hello"}])

    def test_function_call_and_response_emit_existing_tool_call_shape(self):
        state = _StreamState()
        call = Event(
            author=AGENT_NAME,
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        functionCall=types.FunctionCall(id="call-1", name="search_members", args={"name": "Ada"})
                    )
                ],
            ),
        )
        response = Event(
            author=AGENT_NAME,
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        functionResponse=types.FunctionResponse(
                            id="call-1", name="search_members", response={"result": "Showing 1 of 1 result."}
                        )
                    )
                ],
            ),
        )
        self.assertEqual(_normalize_adk_event(call, state), [])
        self.assertEqual(
            _normalize_adk_event(response, state),
            [
                {
                    "type": "tool_call",
                    "name": "search_members",
                    "input": {"name": "Ada"},
                    "result_preview": "Showing 1 of 1 result.",
                }
            ],
        )

    def test_function_response_with_action_request_emits_approval_event(self):
        state = _StreamState()
        action = {
            "id": "action-1",
            "status": "pending",
            "action_type": "db_update",
            "title": "Update feed",
            "summary": "Review it.",
            "target": {"app_label": "cms", "model": "NewsFeedSource", "pk": "1", "repr": "Feed"},
            "diff": [],
            "preview_url": "",
            "created_at": "2026-04-25T00:00:00",
        }
        response = Event(
            author=AGENT_NAME,
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        functionResponse=types.FunctionResponse(
                            id="call-1",
                            name="propose_db_update",
                            response={
                                "result": "Database update request is ready for approval.",
                                "action_request": action,
                            },
                        )
                    )
                ],
            ),
        )
        self.assertEqual(
            _normalize_adk_event(response, state),
            [
                {
                    "type": "tool_call",
                    "name": "propose_db_update",
                    "input": {},
                    "result_preview": "Database update request is ready for approval.",
                },
                {"type": "action_request", **action},
            ],
        )
