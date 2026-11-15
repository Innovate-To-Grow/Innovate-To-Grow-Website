import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.test import SimpleTestCase

from apps.system_intelligence.services.public_assistant.chat import actors


class ResolveChatActorTests(SimpleTestCase):
    def _request(self, data, user=None):
        return SimpleNamespace(data=data, user=user or AnonymousUser())

    def test_reads_the_visitor_value_from_the_request_body(self):
        presented = actors.issue_visitor_token()

        actor = actors.resolve_chat_actor(self._request({"message": "hi", actors.VISITOR_FIELD: presented}))

        self.assertEqual(actor, actors.visitor_actor(presented))

    def test_body_without_the_field_is_legacy(self):
        self.assertEqual(actors.resolve_chat_actor(self._request({"message": "hi"})).kind, actors.KIND_LEGACY)

    def test_non_object_body_is_legacy(self):
        for data in (["not", "an", "object"], "text", None, 7):
            with self.subTest(data=data):
                self.assertEqual(actors.resolve_chat_actor(self._request(data)).kind, actors.KIND_LEGACY)

    def test_result_is_memoised_on_the_request(self):
        request = self._request({actors.VISITOR_FIELD: actors.issue_visitor_token()})

        with patch.object(actors.signing, "loads", wraps=signing.loads) as loads:
            first = actors.resolve_chat_actor(request)
            second = actors.resolve_chat_actor(request)

        self.assertIs(first, second)
        self.assertEqual(loads.call_count, 1)

    def test_authenticated_member_is_keyed_on_the_member_not_the_visitor_value(self):
        member_pk = uuid.uuid4()
        user = SimpleNamespace(is_authenticated=True, pk=member_pk)

        actor = actors.resolve_chat_actor(self._request({actors.VISITOR_FIELD: actors.issue_visitor_token()}, user))

        self.assertEqual(actor, actors.member_actor(member_pk))
        self.assertIsNone(actor.replacement)
