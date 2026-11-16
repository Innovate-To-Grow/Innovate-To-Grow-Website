import asyncio
from io import BytesIO
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.handlers.asgi import ASGIRequest

from apps.system_intelligence.admin.stream.heartbeats import _STREAM_HEARTBEAT, _with_heartbeats
from apps.system_intelligence.admin.stream.send import build_stream_response
from apps.system_intelligence.models import ChatMessage, SystemIntelligenceActionRequest
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


def _asgi_send_request(user):
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
    request.user = user
    return request


async def _consume_stream(response):
    chunks = [chunk async for chunk in response.streaming_content]
    return b"".join(chunks).decode()


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
        request = _asgi_send_request(self.admin_user)

        response = build_stream_response(request, self.conversation)

        self.assertTrue(response.is_async)

    def test_asgi_response_streams_native_agent_events_and_persists_the_assistant(self):
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="Hello")
        request = _asgi_send_request(self.admin_user)

        async def fake_stream(*_args, **_kwargs):
            yield {"type": "text", "chunk": "Hello from ASGI"}
            yield {"type": "usage", "inputTokens": 2, "outputTokens": 3, "totalTokens": 5}

        with patch(
            "apps.system_intelligence.admin.stream.async_events._async_stream_callable",
            return_value=fake_stream,
        ) as stream_callable:
            body = async_to_sync(_consume_stream)(build_stream_response(request, self.conversation))

        self.assertIn('event: start\ndata: {"model_id":', body)
        self.assertIn('event: text\ndata: {"chunk": "Hello from ASGI"}', body)
        self.assertIn("event: done", body)
        stream_callable.assert_called_once_with()
        assistant = ChatMessage.objects.get(conversation=self.conversation, role="assistant")
        self.assertEqual(assistant.content, "Hello from ASGI")
        self.assertEqual(assistant.token_usage["totalTokens"], 5)

    def test_asgi_provider_error_ends_the_stream_without_persisting_an_assistant(self):
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="Hello")
        request = _asgi_send_request(self.admin_user)
        later_event_seen = []

        async def fake_stream(*_args, **_kwargs):
            yield {"type": "text", "chunk": "partial"}
            yield {"type": "error", "error": "boom"}
            later_event_seen.append(True)
            yield {"type": "text", "chunk": "never sent"}

        with patch(
            "apps.system_intelligence.admin.stream.async_events._async_stream_callable", return_value=fake_stream
        ):
            body = async_to_sync(_consume_stream)(build_stream_response(request, self.conversation))

        self.assertIn("event: error", body)
        self.assertNotIn("never sent", body)
        self.assertNotIn("event: done", body)
        self.assertEqual(later_event_seen, [])
        self.assertFalse(ChatMessage.objects.filter(conversation=self.conversation, role="assistant").exists())

    def test_asgi_context_preparation_shares_the_request_database_connection(self):
        # The pending action is written on this thread's connection and not
        # committed yet. Context preparation must run on the same connection
        # (a worker-thread connection can't see it, and SQLite's shared-cache
        # test DB raises "database table is locked" on the read).
        ChatMessage.objects.create(conversation=self.conversation, role="user", content="Apply it")
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            target_pk="123",
            title="Update feed",
        )
        request = _asgi_send_request(self.admin_user)
        received_messages = []

        async def fake_stream(messages, **_kwargs):
            received_messages.extend(messages)
            yield {"type": "text", "chunk": "Waiting for approval."}

        with patch(
            "apps.system_intelligence.admin.stream.async_events._async_stream_callable", return_value=fake_stream
        ):
            body = async_to_sync(_consume_stream)(build_stream_response(request, self.conversation))

        self.assertIn("event: done", body)
        self.assertNotIn("event: error", body)
        self.assertIn(str(action.id), received_messages[0]["content"])
        self.assertEqual(received_messages[-1], {"role": "user", "content": "Apply it"})
