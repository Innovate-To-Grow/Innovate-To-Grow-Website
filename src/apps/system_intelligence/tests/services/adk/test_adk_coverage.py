"""Line-coverage tests for apps.system_intelligence.services.adk.

Each test executes a previously uncovered branch and asserts the resulting
behavior (return value, raised exception, persisted state, or side effect).
All heavy external dependencies (google.adk runtime, LiteLlm, litellm,
aiohttp) are mocked -- no network or real LLM calls happen.
"""

import asyncio
import sys
import time
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from google.adk.events import Event
from google.genai import types

from apps.core.models import AWSCredentialConfig
from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.models import (
    ChatConversation,
    ChatMessage,
    SystemIntelligenceActionRequest,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.adk import (
    AGENT_NAME,
    SystemIntelligenceADKError,
)
from apps.system_intelligence.services.adk.constants import _TTLSet
from apps.system_intelligence.services.adk.context_manager import summary as summary_mod
from apps.system_intelligence.services.adk.context_manager.limits import (
    combine_prepared_messages,
    enforce_hard_limit,
)
from apps.system_intelligence.services.adk.context_manager.messages import (
    format_messages_for_summary,
)
from apps.system_intelligence.services.adk.context_manager.prepare import (
    prepare_conversation_context,
)
from apps.system_intelligence.services.adk.context_manager.summary import (
    ensure_context_summary,
    summarize_context,
    summarize_context_async,
    summary_prompt,
    unsummarized_candidates,
)
from apps.system_intelligence.services.adk.context_manager.tokens import (
    estimate_text_tokens,
    trim_text_to_token_budget,
)
from apps.system_intelligence.services.adk.context_manager.usage import base_usage
from apps.system_intelligence.services.adk.context_window import estimate_context_window
from apps.system_intelligence.services.adk.errors import format_system_intelligence_error
from apps.system_intelligence.services.adk.events import (
    StreamState,
    extract_text,
    metadata_int,
    normalize_adk_event,
    result_preview,
    text_events,
    usage_event,
)
from apps.system_intelligence.services.adk.history import (
    seed_session_history,
    split_history_and_current_message,
)
from apps.system_intelligence.services.adk.litellm import (
    build_lite_llm_model,
    configure_litellm_bedrock_transport,
    prefer_threaded_aiohttp_resolver,
)
from apps.system_intelligence.services.adk.stream import (
    get_aws_config,
    invoke_system_intelligence_stream_async,
)


def _text_event(text, *, partial=False):
    return Event(
        author=AGENT_NAME,
        partial=partial,
        content=types.Content(role="model", parts=[types.Part.from_text(text=text)]),
    )


# ---------------------------------------------------------------------------
# context_window/__init__.py  (lines 5, 8)
# ---------------------------------------------------------------------------
class EstimateContextWindowTests(SimpleTestCase):
    def test_opus_returns_large_window(self):
        self.assertEqual(estimate_context_window("us.anthropic.claude-opus-4"), 200_000)

    def test_sonnet_returns_large_window(self):
        self.assertEqual(estimate_context_window("us.anthropic.claude-sonnet-4"), 200_000)

    def test_unknown_model_returns_conservative_default(self):
        self.assertEqual(estimate_context_window("some-other-model"), 64_000)


# ---------------------------------------------------------------------------
# context_manager/tokens.py  (lines 21, 34)
# ---------------------------------------------------------------------------
class TokenEstimationTests(SimpleTestCase):
    def test_empty_text_estimates_zero_tokens(self):
        self.assertEqual(estimate_text_tokens(""), 0)

    def test_tiny_budget_hard_truncates_without_prefix(self):
        # token_budget * 4 chars <= 32 takes the hard-slice branch (no prefix marker).
        result = trim_text_to_token_budget("abcdefghij" * 10, token_budget=4)
        self.assertEqual(result, ("abcdefghij" * 10)[:16])
        self.assertNotIn("Earlier context truncated", result)

    def test_larger_budget_uses_truncation_prefix(self):
        result = trim_text_to_token_budget("z" * 1000, token_budget=40)
        self.assertTrue(result.startswith("[Earlier context truncated]\n"))


# ---------------------------------------------------------------------------
# context_manager/usage.py  (lines 24-26: base_usage body)
# ---------------------------------------------------------------------------
class BaseUsageTests(TestCase):
    def test_base_usage_counts_raw_tokens_and_messages(self):
        admin = make_superuser()
        conversation = ChatConversation.objects.create(created_by=admin)
        messages = [
            ChatMessage.objects.create(conversation=conversation, role="user", content="hi there"),
            ChatMessage.objects.create(conversation=conversation, role="assistant", content="hello back"),
        ]

        usage = base_usage(
            context_window=64_000,
            compact_threshold=44_800,
            hard_limit=54_400,
            system_tokens=100,
            messages=messages,
        )

        self.assertEqual(usage["contextWindow"], 64_000)
        self.assertEqual(usage["systemTokens"], 100)
        self.assertEqual(usage["rawMessageCount"], 2)
        # rawTokens = system_tokens + sum(len(content)/4 ceil + overhead) ; strictly greater than system.
        self.assertGreater(usage["rawTokens"], 100)
        self.assertFalse(usage["compacted"])


# ---------------------------------------------------------------------------
# context_manager/messages/__init__.py  (line 14: action_requests loop)
# ---------------------------------------------------------------------------
class FormatMessagesForSummaryTests(TestCase):
    def test_attached_action_requests_are_rendered_inline(self):
        admin = make_superuser()
        conversation = ChatConversation.objects.create(created_by=admin)
        message = ChatMessage.objects.create(conversation=conversation, role="assistant", content="Proposed change.")
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=conversation,
            assistant_message=message,
            created_by=admin,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            target_app_label="cms",
            target_model="CMSPage",
            target_pk="7",
            title="Update page",
            summary="Tweak heading.",
        )

        rendered = format_messages_for_summary([message])

        self.assertIn("Proposed change.", rendered)
        self.assertIn(f"Action request {action.id}", rendered)
        self.assertIn("status=", rendered)
        self.assertIn("target=cms.CMSPage:7", rendered)


# ---------------------------------------------------------------------------
# context_manager/limits.py  (lines 39-40, 44, 63)
# ---------------------------------------------------------------------------
class EnforceHardLimitTests(SimpleTestCase):
    def test_action_message_is_trimmed_and_error_reported_when_still_too_large(self):
        # A huge action message that survives recent-message trimming forces the
        # action-trim branch (39-40) and the final over-limit error branch (44).
        action_message = {"role": "assistant", "content": "A" * 80_000}
        current_message = {"role": "user", "content": "B" * 80_000}
        recent = [{"role": "user", "content": "C" * 1000}]

        prepared, meta = enforce_hard_limit(
            summary_message=None,
            action_message=action_message,
            recent_messages=recent,
            current_message=current_message,
            system_tokens=0,
            hard_limit=500,
            minimum_recent_count=0,
        )

        # Action message content was trimmed down to the 1000-token budget.
        trimmed_action = next(m for m in prepared if m["role"] == "assistant")
        self.assertLess(len(trimmed_action["content"]), len(action_message["content"]))
        self.assertTrue(meta["error"])
        self.assertIn("too large for the configured model context window", meta["error"])

    def test_combine_includes_action_message_branch(self):
        # Directly exercises line 63 (action_message appended) without summary.
        combined = combine_prepared_messages(
            None,
            {"role": "assistant", "content": "action"},
            [{"role": "user", "content": "recent"}],
            {"role": "user", "content": "current"},
        )
        self.assertEqual(
            [m["content"] for m in combined],
            ["action", "recent", "current"],
        )


# ---------------------------------------------------------------------------
# context_manager/prepare.py  (lines 35, 38, 46)
# ---------------------------------------------------------------------------
class PrepareConversationContextEdgeTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="k",
            secret_access_key="s",
            default_region="us-west-2",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            system_prompt="Use tools.",
        )
        self.conversation = ChatConversation.objects.create(created_by=self.admin)

    def _prepare(self, messages):
        return prepare_conversation_context(
            self.conversation,
            messages,
            chat_config=self.chat_config,
            aws_config=self.aws_config,
            model_id=self.chat_config.default_model_id,
            user_id=str(self.admin.pk),
        )

    def test_empty_history_returns_error(self):
        prepared = self._prepare([])
        self.assertEqual(prepared.messages, [])
        self.assertEqual(prepared.error, "Message history is empty.")

    def test_latest_message_not_user_returns_error(self):
        msg = ChatMessage.objects.create(conversation=self.conversation, role="assistant", content="hi")
        prepared = self._prepare([msg])
        self.assertEqual(prepared.error, "The latest message must be a user message.")

    def test_current_message_too_large_returns_error(self):
        msg = ChatMessage.objects.create(conversation=self.conversation, role="user", content="x" * 4000)
        with patch(
            "apps.system_intelligence.services.adk.context_manager.prepare.estimate_context_window",
            return_value=100,
        ):
            prepared = self._prepare([msg])
        self.assertEqual(prepared.messages, [])
        self.assertEqual(prepared.error, "The current message is too large for the configured model context window.")
        self.assertEqual(prepared.usage["rawMessageCount"], 1)


# ---------------------------------------------------------------------------
# context_manager/summary.py
# ---------------------------------------------------------------------------
class EnsureContextSummaryTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="k",
            secret_access_key="s",
            default_region="us-west-2",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            system_prompt="Use tools.",
        )
        self.conversation = ChatConversation.objects.create(created_by=self.admin)

    def _msg(self, role, content):
        return ChatMessage.objects.create(conversation=self.conversation, role=role, content=content)

    def test_no_candidates_returns_existing_summary(self):
        # Line 50: empty compact_candidates short-circuits to existing summary.
        self.conversation.context_summary = "Existing"
        self.conversation.save(update_fields=["context_summary", "updated_at"])
        result, meta = ensure_context_summary(
            self.conversation,
            [],
            chat_config=self.chat_config,
            aws_config=self.aws_config,
            model_id="m",
            user_id="u",
        )
        self.assertEqual(result, "Existing")
        self.assertTrue(meta["summary_used"])
        self.assertFalse(meta["summary_updated"])

    def test_already_summarized_candidates_skip_resummary(self):
        # Lines 54-55: existing summary already covers all candidates, force=False.
        first = self._msg("user", "one")
        second = self._msg("assistant", "two")
        self.conversation.context_summary = "Existing summary"
        self.conversation.context_summary_through_message = second
        self.conversation.save(update_fields=["context_summary", "context_summary_through_message", "updated_at"])

        with patch.object(summary_mod, "summarize_context", side_effect=AssertionError("should not summarize")):
            result, meta = ensure_context_summary(
                self.conversation,
                [first, second],
                chat_config=self.chat_config,
                aws_config=self.aws_config,
                model_id="m",
                user_id="u",
                force=False,
            )

        self.assertEqual(result, "Existing summary")
        self.assertTrue(meta["summary_used"])
        self.assertFalse(meta["summary_updated"])

    def test_force_resummarizes_all_candidates_when_none_are_new(self):
        # Line 57: new_candidates empty but force=True falls back to all candidates.
        first = self._msg("user", "one")
        second = self._msg("assistant", "two")
        self.conversation.context_summary = "Existing summary"
        self.conversation.context_summary_through_message = second
        self.conversation.save(update_fields=["context_summary", "context_summary_through_message", "updated_at"])

        with patch.object(summary_mod, "summarize_context", return_value="Fresh summary") as mocked:
            result, meta = ensure_context_summary(
                self.conversation,
                [first, second],
                chat_config=self.chat_config,
                aws_config=self.aws_config,
                model_id="m",
                user_id="u",
                force=True,
            )

        mocked.assert_called_once()
        self.assertEqual(result, "Fresh summary")
        self.assertTrue(meta["summary_updated"])
        self.assertEqual(meta["summarized_messages"], 2)

    def test_unsummarized_candidates_returns_tail_after_through_message(self):
        # Lines 102-104: through_id matches a candidate; tail after it is returned.
        first = self._msg("user", "one")
        second = self._msg("assistant", "two")
        third = self._msg("user", "three")
        self.conversation.context_summary = "Existing"
        self.conversation.context_summary_through_message = first
        self.conversation.save(update_fields=["context_summary", "context_summary_through_message", "updated_at"])

        tail = unsummarized_candidates(self.conversation, [first, second, third])

        self.assertEqual(tail, [second, third])

    def test_unsummarized_candidates_returns_all_when_through_id_not_in_list(self):
        # Line 105: through_id set but not present among candidates -> return all.
        first = self._msg("user", "one")
        second = self._msg("assistant", "two")
        # through_message points at a message that is NOT in the candidate list.
        orphan = self._msg("user", "orphan")
        self.conversation.context_summary = "Existing"
        self.conversation.context_summary_through_message = orphan
        self.conversation.save(update_fields=["context_summary", "context_summary_through_message", "updated_at"])

        result = unsummarized_candidates(self.conversation, [first, second])

        self.assertEqual(result, [first, second])


class SummarizeContextAsyncTests(TestCase):
    def setUp(self):
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="k",
            secret_access_key="s",
            default_region="us-west-2",
        )
        self.chat_config = SystemIntelligenceConfig(system_prompt="System note", max_tokens=256, temperature=0.2)

    def _patches(self, runner_factory):
        class FakeSessionService:
            async def create_session(self, *, app_name, user_id, session_id):
                class _Session:
                    id = session_id

                return _Session()

        return (
            patch.object(summary_mod, "build_lite_llm_model", return_value=object()),
            patch.object(summary_mod, "LlmAgent", return_value=object()),
            patch.object(summary_mod, "InMemorySessionService", return_value=FakeSessionService()),
            patch.object(summary_mod, "Runner", return_value=runner_factory()),
        )

    def test_summarize_context_async_joins_streamed_text(self):
        # Lines 138-167, 169: full async path returning a non-empty summary.
        class FakeRunner:
            async def run_async(self, **kwargs):
                yield _text_event("Sum", partial=True)
                yield _text_event("mary", partial=True)

        p1, p2, p3, p4 = self._patches(FakeRunner)
        with p1, p2, p3, p4:
            result = asyncio.run(
                summarize_context_async(
                    existing_summary="prev",
                    new_context="new messages",
                    chat_config=self.chat_config,
                    aws_config=self.aws_config,
                    model_id="us.anthropic.claude-sonnet-4",
                    user_id="42",
                )
            )
        self.assertEqual(result, "Summary")

    def test_summarize_context_async_raises_on_empty_response(self):
        # Line 168: empty streamed text raises ValueError.
        class EmptyRunner:
            async def run_async(self, **kwargs):
                if False:  # pragma: no cover - generator with no yields
                    yield None

        p1, p2, p3, p4 = self._patches(EmptyRunner)
        with p1, p2, p3, p4, self.assertRaises(ValueError) as ctx:
            asyncio.run(
                summarize_context_async(
                    existing_summary="",
                    new_context="ctx",
                    chat_config=self.chat_config,
                    aws_config=self.aws_config,
                    model_id="m",
                    user_id="",
                )
            )
        self.assertIn("empty response", str(ctx.exception))

    def test_summarize_context_sync_wrapper_runs_async(self):
        # Line 117: synchronous wrapper drives summarize_context_async via asyncio.run.
        with patch.object(summary_mod, "summarize_context_async") as mocked:

            async def _result(**kwargs):
                return "wrapped summary"

            mocked.side_effect = _result
            result = summarize_context(
                existing_summary="prev",
                new_context="ctx",
                chat_config=self.chat_config,
                aws_config=self.aws_config,
                model_id="m",
                user_id="u",
            )
        self.assertEqual(result, "wrapped summary")

    def test_summary_prompt_embeds_system_note_and_existing_summary(self):
        # Lines 173-174: prompt builder reads chat_config.system_prompt.
        prompt = summary_prompt("Existing", "New stuff", self.chat_config)
        self.assertIn("System note", prompt)
        self.assertIn("Existing", prompt)
        self.assertIn("New stuff", prompt)


# ---------------------------------------------------------------------------
# events/__init__.py
# ---------------------------------------------------------------------------
class NormalizeAdkEventTests(SimpleTestCase):
    def test_error_message_event_short_circuits(self):
        # Line 20: event with error_message returns a single error dict.
        event = Event(author=AGENT_NAME, error_message="boom failure")
        result = normalize_adk_event(event, StreamState())
        self.assertEqual(result, [{"type": "error", "error": "boom failure"}])

    def test_text_after_tool_calls_is_suppressed(self):
        # Line 46: a final text event accompanied by function calls yields nothing.
        state = StreamState()
        event = Event(
            author=AGENT_NAME,
            partial=False,
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(text="ignored trailing text"),
                    types.Part(functionCall=types.FunctionCall(id="c1", name="search", args={})),
                ],
            ),
        )
        self.assertEqual(text_events(event, state), [])

    def test_final_text_with_prior_stream_but_no_shared_prefix_appends_whole_text(self):
        # Lines 52-53: streamed_text set, final text neither shares a prefix nor equals it.
        state = StreamState()
        state.streamed_text = "alpha"
        event = _text_event("beta", partial=False)
        self.assertEqual(text_events(event, state), [{"type": "text", "chunk": "beta"}])
        self.assertEqual(state.streamed_text, "alphabeta")

    def test_extract_text_returns_empty_when_no_content(self):
        # Line 81: event without content returns empty string.
        self.assertEqual(extract_text(Event(author=AGENT_NAME)), "")

    def test_result_preview_stringifies_non_dict_non_str(self):
        # Line 89: a non-dict, non-str response is stringified.
        self.assertEqual(result_preview(12345), "12345")

    def test_usage_event_returns_none_when_all_zero(self):
        # Line 102: usage metadata with all-zero counts yields no usage event.
        metadata = types.GenerateContentResponseUsageMetadata(
            promptTokenCount=0, candidatesTokenCount=0, totalTokenCount=0
        )
        self.assertIsNone(usage_event(metadata))

    def test_metadata_int_falls_back_to_attribute_then_zero(self):
        # Line 110: value missing from dict is read from the object attribute.
        class Holder:
            promptTokenCount = 9

        self.assertEqual(metadata_int({}, Holder(), "prompt_token_count", "promptTokenCount"), 9)
        # Line 113: nothing matches -> 0.
        self.assertEqual(metadata_int({}, object(), "missing"), 0)

    def test_usage_event_reads_attribute_fallback_path(self):
        class Meta:
            promptTokenCount = 5
            candidatesTokenCount = 7
            totalTokenCount = 0

        usage = usage_event(Meta())
        self.assertEqual(usage, {"type": "usage", "inputTokens": 5, "outputTokens": 7, "totalTokens": 12})

    def test_usage_event_preserves_cache_token_metadata(self):
        class Meta:
            promptTokenCount = 5
            candidatesTokenCount = 7
            totalTokenCount = 12
            cachedContentTokenCount = 4
            cacheWriteInputTokens = 2

        usage = usage_event(Meta())
        self.assertEqual(
            usage,
            {
                "type": "usage",
                "inputTokens": 5,
                "outputTokens": 7,
                "totalTokens": 12,
                "cacheReadInputTokens": 4,
                "cacheWriteInputTokens": 2,
            },
        )


# ---------------------------------------------------------------------------
# litellm.py  (lines 13-16, 36-37, 49-51)
# ---------------------------------------------------------------------------
class LiteLlmBuilderTests(SimpleTestCase):
    def test_build_lite_llm_model_passes_credentials_and_region(self):
        captured = {}

        class FakeLiteLlm:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        aws_config = AWSCredentialConfig(
            access_key_id="AKIA-test",
            secret_access_key="secret-test",
            default_region="eu-west-1",
        )
        with (
            patch("apps.system_intelligence.services.adk.litellm.configure_litellm_bedrock_transport"),
            patch.dict(sys.modules, {"google.adk.models.lite_llm": type(sys)("google.adk.models.lite_llm")}),
        ):
            sys.modules["google.adk.models.lite_llm"].LiteLlm = FakeLiteLlm
            build_lite_llm_model(aws_config=aws_config, model_id="us.anthropic.claude-sonnet-4")

        self.assertEqual(captured["model"], "bedrock/us.anthropic.claude-sonnet-4")
        self.assertEqual(captured["aws_access_key_id"], "AKIA-test")
        self.assertEqual(captured["aws_secret_access_key"], "secret-test")
        self.assertEqual(captured["aws_region_name"], "eu-west-1")

    def test_build_lite_llm_model_defaults_region(self):
        captured = {}

        class FakeLiteLlm:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        aws_config = AWSCredentialConfig(
            access_key_id="k",
            secret_access_key="s",
            default_region="",
        )
        with (
            patch("apps.system_intelligence.services.adk.litellm.configure_litellm_bedrock_transport"),
            patch.dict(sys.modules, {"google.adk.models.lite_llm": type(sys)("google.adk.models.lite_llm")}),
        ):
            sys.modules["google.adk.models.lite_llm"].LiteLlm = FakeLiteLlm
            build_lite_llm_model(aws_config=aws_config, model_id="us.anthropic.claude-sonnet-4")

        self.assertEqual(captured["aws_region_name"], "us-west-2")

    def test_configure_litellm_transport_logs_when_litellm_import_fails(self):
        # Lines 36-37: import litellm raises -> debug log, no attribute set.
        with (
            patch.dict(sys.modules, {"litellm": None}),
            patch("apps.system_intelligence.services.adk.litellm.prefer_threaded_aiohttp_resolver") as resolver,
            patch("apps.system_intelligence.services.adk.litellm.logger.debug") as debug_log,
        ):
            configure_litellm_bedrock_transport()
        debug_log.assert_called_once()
        self.assertIn("LiteLLM transport configuration skipped", debug_log.call_args.args[0])
        resolver.assert_called_once()

    def test_prefer_threaded_resolver_logs_when_aiohttp_import_fails(self):
        # Lines 49-51: aiohttp import raises -> debug log and early return.
        with (
            patch.dict(sys.modules, {"aiohttp.connector": None, "aiohttp.resolver": None}),
            patch("apps.system_intelligence.services.adk.litellm.logger.debug") as debug_log,
        ):
            prefer_threaded_aiohttp_resolver()
        debug_log.assert_called_once()
        self.assertIn("aiohttp resolver patch skipped", debug_log.call_args.args[0])


# ---------------------------------------------------------------------------
# history/__init__.py  (lines 14, 17, 20, 30, 39)
# ---------------------------------------------------------------------------
class HistorySplitTests(SimpleTestCase):
    def test_empty_history_raises(self):
        with self.assertRaises(SystemIntelligenceADKError) as ctx:
            split_history_and_current_message([])
        self.assertIn("Message history is empty.", str(ctx.exception))

    def test_latest_not_user_raises(self):
        with self.assertRaises(SystemIntelligenceADKError) as ctx:
            split_history_and_current_message([{"role": "assistant", "content": "hi"}])
        self.assertIn("latest message must be a user message", str(ctx.exception))

    def test_blank_current_message_raises(self):
        with self.assertRaises(SystemIntelligenceADKError) as ctx:
            split_history_and_current_message([{"role": "user", "content": "   "}])
        self.assertIn("Message cannot be empty.", str(ctx.exception))


class SeedSessionHistoryTests(SimpleTestCase):
    def test_blank_and_unknown_role_messages_are_skipped(self):
        # Line 30: blank content skipped; line 39: unknown role skipped.
        appended = []

        class FakeSessionService:
            async def append_event(self, *, session, event):
                appended.append(event.content.parts[0].text)

        async def run():
            await seed_session_history(
                FakeSessionService(),
                object(),
                [
                    {"role": "user", "content": "   "},  # blank -> skipped
                    {"role": "system", "content": "ignored"},  # unknown role -> skipped
                    {"role": "user", "content": "kept"},
                ],
            )

        asyncio.run(run())
        self.assertEqual(appended, ["kept"])


# ---------------------------------------------------------------------------
# constants.py  (lines 97-100: _TTLSet expired entry)
# ---------------------------------------------------------------------------
class TTLSetTests(SimpleTestCase):
    def test_expired_entry_is_evicted_and_reports_absent(self):
        ttl_set = _TTLSet(ttl_seconds=100)
        ttl_set.add("model-x")
        # Membership while fresh.
        self.assertIn("model-x", ttl_set)
        # Advance the monotonic clock past the TTL so __contains__ evicts it.
        with patch(
            "apps.system_intelligence.services.adk.constants.time.monotonic", return_value=time.monotonic() + 10_000
        ):
            self.assertNotIn("model-x", ttl_set)
        # Entry was popped: even rewinding the clock, it stays absent.
        self.assertNotIn("model-x", ttl_set)


# ---------------------------------------------------------------------------
# errors.py  (line 23: non-connectivity error returns str(error))
# ---------------------------------------------------------------------------
class FormatErrorTests(SimpleTestCase):
    def test_non_connectivity_error_returns_str(self):
        err = RuntimeError("Some unrelated provider failure")
        self.assertEqual(format_system_intelligence_error(err), "Some unrelated provider failure")


# ---------------------------------------------------------------------------
# stream.py  (lines 58, 96, 117, 138)
# ---------------------------------------------------------------------------
class StreamAsyncTests(TestCase):
    def setUp(self):
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="k",
            secret_access_key="s",
            default_region="us-west-2",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            system_prompt="Use tools.",
        )

    def test_get_aws_config_raises_when_not_configured(self):
        # Line 138: an unconfigured AWS config raises a clear error.
        unconfigured = AWSCredentialConfig(access_key_id="", secret_access_key="")
        with self.assertRaises(SystemIntelligenceADKError) as ctx:
            get_aws_config(unconfigured)
        self.assertIn("AWS credentials are not configured", str(ctx.exception))

    def test_async_stream_raises_when_no_model_configured(self):
        # Line 96: empty model id raises before any runner work.
        self.chat_config.default_model_id = ""

        async def collect():
            return [
                event
                async for event in invoke_system_intelligence_stream_async(
                    [{"role": "user", "content": "Current"}],
                    chat_config=self.chat_config,
                    aws_config=self.aws_config,
                    model_id="",
                    user_id="42",
                )
            ]

        with self.assertRaises(SystemIntelligenceADKError) as ctx:
            asyncio.run(collect())
        self.assertIn("No Bedrock model is configured", str(ctx.exception))

    def test_async_stream_reraises_after_emitting_events(self):
        # Lines 116-117: once an event has been emitted, a later failure must
        # re-raise WITHOUT a temperature retry. Assert both halves: the partial
        # event WAS delivered to the caller, and run_async ran exactly once (a
        # retry would invoke run_async again).
        run_calls = {"n": 0}

        class PartiallyFailingRunner:
            async def run_async(self, **kwargs):
                run_calls["n"] += 1
                yield _text_event("partial", partial=False)
                raise Exception("BedrockException: `temperature` is deprecated for this model.")

        collected = []

        async def collect():
            with patch(
                "apps.system_intelligence.services.adk._build_runner",
                return_value=(PartiallyFailingRunner(), _FakeSessionService()),
            ):
                async for event in invoke_system_intelligence_stream_async(
                    [{"role": "user", "content": "Current"}],
                    chat_config=self.chat_config,
                    aws_config=self.aws_config,
                    model_id=self.chat_config.default_model_id,
                    user_id="42",
                ):
                    collected.append(event)

        with self.assertRaises(Exception) as ctx:
            asyncio.run(collect())
        self.assertIn("temperature", str(ctx.exception))
        # The partial event emitted before the failure reached the caller.
        self.assertEqual(len(collected), 1)
        # No retry: the emitted-event guard short-circuits the temperature-retry path.
        self.assertEqual(run_calls["n"], 1)


class _FakeSessionService:
    async def create_session(self, *, app_name, user_id, session_id):
        class _Session:
            id = session_id
            events = []

        return _Session()

    async def append_event(self, *, session, event):
        return None


class StreamSyncErrorLoggingTests(TestCase):
    def setUp(self):
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="k",
            secret_access_key="s",
            default_region="us-west-2",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            system_prompt="Use tools.",
        )

    def test_sync_stream_logs_exception_for_generic_failure(self):
        # Line 58: an error that is NOT reformatted goes through logger.exception.
        from apps.system_intelligence.services.adk import invoke_system_intelligence_stream

        async def failing_async_stream(*args, **kwargs):
            raise RuntimeError("totally generic failure")
            yield {}  # pragma: no cover - generator marker

        with (
            patch(
                "apps.system_intelligence.services.adk._invoke_system_intelligence_stream_async",
                new=failing_async_stream,
            ),
            patch("apps.system_intelligence.services.adk.stream.logger.exception") as exc_log,
            patch("apps.system_intelligence.services.adk.stream.logger.warning") as warn_log,
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

        self.assertEqual(events, [{"type": "error", "error": "totally generic failure"}])
        exc_log.assert_called_once()
        warn_log.assert_not_called()


# ---------------------------------------------------------------------------
# runner.py  (lines 78-88: build_runner)
# ---------------------------------------------------------------------------
class BuildRunnerTests(TestCase):
    def setUp(self):
        self.aws_config = AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="k",
            secret_access_key="s",
            default_region="us-west-2",
        )
        self.chat_config = SystemIntelligenceConfig.objects.create(
            name="System Intelligence",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            system_prompt="Use tools.",
        )

    def test_build_runner_returns_runner_and_session_service(self):
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        from apps.system_intelligence.services.adk.constants import APP_NAME
        from apps.system_intelligence.services.adk.runner import build_runner

        # LlmAgent accepts a raw model-id string, so patching build_lite_llm_model
        # avoids contacting Bedrock while still exercising the real build_agent path.
        with patch(
            "apps.system_intelligence.services.adk.runner.build_lite_llm_model",
            return_value="bedrock/test-model",
        ):
            runner, session_service = build_runner(
                chat_config=self.chat_config,
                aws_config=self.aws_config,
                model_id=self.chat_config.default_model_id,
                include_temperature=False,
                mode="normal",
            )

        self.assertIsInstance(runner, Runner)
        self.assertIsInstance(session_service, InMemorySessionService)
        self.assertEqual(runner.app_name, APP_NAME)
        self.assertEqual(runner.agent.name, AGENT_NAME)
        self.assertIs(runner.session_service, session_service)
