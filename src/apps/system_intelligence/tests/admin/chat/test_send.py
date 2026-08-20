import asyncio
import json
from io import BytesIO
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.handlers.asgi import ASGIRequest
from django.urls import reverse

from apps.system_intelligence.admin.stream import _STREAM_HEARTBEAT, _with_heartbeats, build_stream_response
from apps.system_intelligence.models import ChatMessage, SystemIntelligenceActionRequest
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class SystemIntelligenceAdminSendTests(SystemIntelligenceAdminBase):
    def test_async_stream_sends_heartbeats_and_cancels_the_provider(self):
        async def consume():
            release_second_frame = asyncio.Event()
            provider_closed = asyncio.Event()

            async def source():
                try:
                    yield "event: start\ndata: {}\n\n"
                    await release_second_frame.wait()
                    yield "event: done\ndata: {}\n\n"
                finally:
                    provider_closed.set()

            stream = _with_heartbeats(source(), heartbeat_seconds=0.01)
            self.assertEqual(await anext(stream), "event: start\ndata: {}\n\n")
            self.assertIs(await anext(stream), _STREAM_HEARTBEAT)
            await stream.aclose()
            await asyncio.wait_for(provider_closed.wait(), timeout=0.1)

        async_to_sync(consume)()

    def test_async_stream_does_not_mask_a_provider_timeout_as_a_heartbeat(self):
        async def consume():
            async def source():
                raise TimeoutError("provider timed out")
                yield  # pragma: no cover - makes this an async generator

            stream = _with_heartbeats(source(), heartbeat_seconds=0.01)
            with self.assertRaisesRegex(TimeoutError, "provider timed out"):
                await anext(stream)

        async_to_sync(consume)()

    def test_asgi_request_receives_an_async_streaming_response(self):
        request = ASGIRequest(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "path": "/admin/system-intelligence/send/",
                "raw_path": b"/admin/system-intelligence/send/",
                "query_string": b"",
                "headers": [],
                "server": ("testserver", 80),
                "client": ("127.0.0.1", 50000),
                "scheme": "http",
            },
            BytesIO(),
        )
        request.user = self.admin_user

        response = build_stream_response(request, self.conversation)

        self.assertTrue(response.is_async)

    def test_asgi_response_streams_native_agent_events_and_persists_the_assistant(self):
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="Hello")
        request = ASGIRequest(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "path": "/admin/system-intelligence/send/",
                "raw_path": b"/admin/system-intelligence/send/",
                "query_string": b"",
                "headers": [],
                "server": ("testserver", 80),
                "client": ("127.0.0.1", 50000),
                "scheme": "http",
            },
            BytesIO(),
        )
        request.user = self.admin_user

        async def fake_stream(*_args, **_kwargs):
            yield {"type": "text", "chunk": "Hello from ASGI"}
            yield {"type": "usage", "inputTokens": 2, "outputTokens": 3, "totalTokens": 5}

        async def consume(response):
            chunks = [chunk async for chunk in response.streaming_content]
            return b"".join(chunks).decode()

        with patch(
            "apps.system_intelligence.admin.stream._async_stream_callable",
            return_value=fake_stream,
        ) as stream_callable:
            body = async_to_sync(consume)(build_stream_response(request, self.conversation))

        self.assertIn('event: start\ndata: {"model_id":', body)
        self.assertIn('event: text\ndata: {"chunk": "Hello from ASGI"}', body)
        self.assertIn("event: done", body)
        stream_callable.assert_called_once_with()
        assistant = ChatMessage.objects.get(conversation=self.conversation, role="assistant")
        self.assertEqual(assistant.content, "Hello from ASGI")
        self.assertEqual(assistant.token_usage["totalTokens"], 5)

    def test_send_stream_preserves_sse_protocol_and_persists_assistant_metadata(self):
        stream_events = [
            {"type": "text", "chunk": "Hello"},
            {
                "type": "tool_call",
                "name": "search_members",
                "input": {"name": "Ada"},
                "result_preview": "Showing 1 of 1 result.",
            },
            {
                "type": "usage",
                "inputTokens": 2,
                "outputTokens": 3,
                "totalTokens": 5,
                "cacheReadInputTokens": 4,
                "cacheWriteInputTokens": 1,
            },
        ]
        with patch(
            "apps.system_intelligence.admin.invoke_system_intelligence_stream", return_value=iter(stream_events)
        ) as stream:
            response = self.client.post(
                reverse("admin:system_intelligence_send", args=[self.conversation.id]),
                data=json.dumps({"message": "Find Ada"}),
                content_type="application/json",
            )
            body = b"".join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn('event: context\ndata: {"contextWindow": 200000', body)
        self.assertIn('event: text\ndata: {"chunk": "Hello"}', body)
        self.assertLess(body.index("event: context"), body.index("event: text"))
        self.assertIn('event: tool_call\ndata: {"type": "tool_call"', body)
        self.assertIn(
            'event: usage\ndata: {"inputTokens": 2, "outputTokens": 3, "totalTokens": 5, '
            '"cacheReadInputTokens": 4, "cacheWriteInputTokens": 1}',
            body,
        )
        self.assertIn('event: done\ndata: {"id":', body)
        self.assertEqual(stream.call_args.args[0], [{"role": "user", "content": "Find Ada"}])
        self.assertEqual(stream.call_args.kwargs["chat_config"], self.chat_config)
        self.assertEqual(stream.call_args.kwargs["aws_config"], self.aws_config)
        messages = list(ChatMessage.objects.filter(conversation=self.conversation).order_by("created_at"))
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertEqual(messages[1].content, "Hello")
        self.assertEqual(
            messages[1].token_usage,
            {
                "inputTokens": 2,
                "outputTokens": 3,
                "totalTokens": 5,
                "cacheReadInputTokens": 4,
                "cacheWriteInputTokens": 1,
            },
        )
        self.assertEqual(messages[1].context_usage["preparedMessageCount"], 1)
        detail = self.client.get(reverse("admin:system_intelligence_detail", args=[self.conversation.id]))
        self.assertEqual(detail.json()["messages"][-1]["context_usage"]["preparedMessageCount"], 1)

    def test_send_stream_emits_action_request_and_links_it_to_assistant_message(self):
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            target_pk="123",
            target_repr="Feed",
            title="Update feed",
            summary="Needs review.",
            diff=[{"field": "name", "before": "Old", "after": "New"}],
        )
        event = {
            "type": "action_request",
            "id": str(action.id),
            "status": "pending",
            "action_type": "db_update",
            "title": "Update feed",
            "summary": "Needs review.",
            "target": {"app_label": "cms", "model": "NewsFeedSource", "pk": "123", "repr": "Feed"},
            "diff": [{"field": "name", "before": "Old", "after": "New"}],
            "preview_url": "",
            "created_at": "2026-04-25T00:00:00",
        }
        with patch(
            "apps.system_intelligence.admin.invoke_system_intelligence_stream",
            return_value=iter([{"type": "text", "chunk": "I prepared a change."}, event]),
        ):
            response = self.client.post(
                reverse("admin:system_intelligence_send", args=[self.conversation.id]),
                data=json.dumps({"message": "Change it"}),
                content_type="application/json",
            )
            body = b"".join(response.streaming_content).decode()
        self.assertIn("event: action_request", body)
        action.refresh_from_db()
        self.assertEqual(action.assistant_message.content, "I prepared a change.")
        detail = self.client.get(reverse("admin:system_intelligence_detail", args=[self.conversation.id]))
        self.assertEqual(detail.json()["messages"][-1]["action_requests"][0]["id"], str(action.id))

    def test_send_rejects_messages_above_length_cap(self):
        from apps.system_intelligence.admin.stream import USER_MESSAGE_MAX_CHARS

        oversized = "x" * (USER_MESSAGE_MAX_CHARS + 1)
        response = self.client.post(
            reverse("admin:system_intelligence_send", args=[self.conversation.id]),
            data=json.dumps({"message": oversized}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("characters", response.json()["error"])
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation, role="user").exists())

    def test_send_does_not_overwrite_user_renamed_title_named_new_chat(self):
        from apps.system_intelligence.models import ChatConversation

        ChatConversation.objects.filter(pk=self.conversation.pk).update(title="New Chat", auto_title=False)
        with patch(
            "apps.system_intelligence.admin.invoke_system_intelligence_stream",
            return_value=iter([{"type": "text", "chunk": "Hi"}]),
        ):
            response = self.client.post(
                reverse("admin:system_intelligence_send", args=[self.conversation.id]),
                data=json.dumps({"message": "First message that would otherwise become the title."}),
                content_type="application/json",
            )
            b"".join(response.streaming_content)

        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, "New Chat")
        self.assertFalse(self.conversation.auto_title)

    def test_send_stream_sanitizes_bedrock_dns_error(self):
        raw_error = "litellm.ServiceUnavailableError: BedrockException - Cannot connect to host bedrock-runtime.us-west-2.amazonaws.com:443 ssl:<ssl.SSLContext object> [Could not contact DNS servers]"
        with patch(
            "apps.system_intelligence.admin.invoke_system_intelligence_stream",
            return_value=iter([{"type": "error", "error": raw_error}]),
        ):
            response = self.client.post(
                reverse("admin:system_intelligence_send", args=[self.conversation.id]),
                data=json.dumps({"message": "hello"}),
                content_type="application/json",
            )
            body = b"".join(response.streaming_content).decode()
        self.assertIn("Unable to reach AWS Bedrock Runtime in us-west-2", body)
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation, role="assistant").exists())
