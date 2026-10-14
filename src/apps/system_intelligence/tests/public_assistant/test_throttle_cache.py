"""The assistant's request-rate history lives in the bounded ``throttle`` cache, never in the default cache.

``PublicAssistantActorThrottle`` is keyed on the visitor token, and ``GET /assistant/config/`` hands a fresh token to
anyone who asks. Every token that sends one chat request is a throttle key. In the production default cache (a
per-container file cache) each key was a file, and every cache write of the container slowed down with the file
count. The limiter itself is unchanged: 6 a minute per visitor or member, 60 a minute for the shared legacy bucket.
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.core.utils.throttle_cache import throttle_cache
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.public_assistant import actors
from apps.system_intelligence.views.public_assistant import PublicAssistantActorThrottle
from config.settings.components.framework.cache import THROTTLE_CACHE

Member = get_user_model()

MOCK_RESULT = {
    "text": "Innovate to Grow connects student teams with industry partners.",
    "usage": {"inputTokens": 120, "outputTokens": 40, "totalTokens": 160},
}
INVOKE_PATH = "apps.system_intelligence.views.public_assistant.answer_public_question"
CONTEXT_PATH = "apps.system_intelligence.views.public_assistant.build_public_context"
CAMPUS_IP = "169.236.10.10"


def history_key(actor) -> str:
    """The cache key the throttle uses for ``actor`` (``throttle_<scope>_<kind>:<actor key>``)."""
    return f"throttle_public_assistant_{actor.kind}:{actor.key}"


def stored_keys(alias: str) -> set[str]:
    """Every key a LocMemCache alias holds, as the caller wrote it (without the ``prefix:version:`` part)."""
    return {key.split(":", 2)[2] for key in caches[alias]._cache}


def throttle_keys(alias: str) -> set[str]:
    return {key for key in stored_keys(alias) if key.startswith("throttle_")}


# The database budget path is the production path (no Redis).
@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class AssistantThrottleCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.chat_url = reverse("system_intelligence:public-assistant-chat")
        self.config_url = reverse("system_intelligence:public-assistant-config")
        SystemIntelligenceConfig.objects.create(
            name="Test",
            is_active=True,
            public_assistant_enabled=True,
            public_assistant_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            public_assistant_system_prompt="Be brief.",
            public_assistant_max_response_tokens=100,
        )
        AWSCredentialConfig.objects.create(
            name="Test AWS",
            is_active=True,
            access_key_id="AKIATESTKEY",
            secret_access_key="secret",
            default_region="us-west-2",
        )
        for target, result in ((CONTEXT_PATH, "ctx"), (INVOKE_PATH, MOCK_RESULT)):
            patcher = patch(target, return_value=result)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        cache.clear()

    def new_visitor(self) -> str:
        return self.client.get(self.config_url, REMOTE_ADDR=CAMPUS_IP).data["visitor_token"]

    def ask(self, visitor=None) -> int:
        payload = {"message": "hi"}
        if visitor is not None:
            payload["visitor_token"] = visitor
        return self.client.post(self.chat_url, payload, format="json", REMOTE_ADDR=CAMPUS_IP).status_code

    def test_the_throttle_keeps_its_history_in_the_throttle_alias(self):
        self.assertIs(PublicAssistantActorThrottle.cache, throttle_cache)
        self.assertIs(PublicAssistantActorThrottle().cache, throttle_cache)

    def test_chat_requests_write_throttle_history_to_the_throttle_cache_only(self):
        visitor = self.new_visitor()
        member = Member.objects.create_user(email="member@example.com", password="pw", is_active=True)

        visitor_statuses = [self.ask(visitor) for _ in range(7)]
        legacy_status = self.ask()
        self.client.force_authenticate(user=member)
        member_status = self.ask()

        self.assertEqual(visitor_statuses, [200] * 6 + [429])
        self.assertEqual((legacy_status, member_status), (200, 200))
        self.assertEqual(throttle_keys("default"), set())
        visitor_key = history_key(actors.visitor_actor(visitor))
        self.assertEqual(
            stored_keys("throttle"),
            {visitor_key, history_key(actors.legacy_actor()), history_key(actors.member_actor(member.pk))},
        )
        self.assertEqual(len(throttle_cache.get(visitor_key)), 6)
        self.assertEqual(len(throttle_cache.get(history_key(actors.legacy_actor()))), 1)

    def test_handing_out_visitor_tokens_writes_no_cache_entry_at_all(self):
        for _ in range(50):
            self.new_visitor()

        self.assertEqual(stored_keys("throttle"), set())
        self.assertEqual(throttle_keys("default"), set())

    def test_the_rate_holds_while_the_default_cache_refuses_throttle_keys(self):
        default = caches["default"]
        real = {name: getattr(default, name) for name in ("get", "set", "add")}

        def guarded(name):
            def call(key, *args, **kwargs):
                if "throttle" in str(key):
                    raise AssertionError(f"throttle history went to the default cache: {key}")
                return real[name](key, *args, **kwargs)

            return call

        visitor = self.new_visitor()
        with patch.multiple(default, get=guarded("get"), set=guarded("set"), add=guarded("add")):
            statuses = [self.ask(visitor) for _ in range(7)]
            other_visitor_status = self.ask(self.new_visitor())

        self.assertEqual(statuses, [200] * 6 + [429])
        self.assertEqual(other_visitor_status, 200)

    def test_the_legacy_bucket_still_allows_sixty_requests_a_minute(self):
        statuses = [self.ask() for _ in range(61)]

        self.assertEqual(statuses, [200] * 60 + [429])
        self.assertEqual(len(throttle_cache.get(history_key(actors.legacy_actor()))), 60)
        self.assertEqual(throttle_keys("default"), set())

    def test_a_flood_of_minted_tokens_cannot_grow_the_throttle_cache_past_its_cap(self):
        small = {**THROTTLE_CACHE, "LOCATION": "assistant-bound-probe", "OPTIONS": {"MAX_ENTRIES": 20}}
        with override_settings(CACHES={**settings.CACHES, "throttle": small}):
            self.addCleanup(caches["throttle"].clear)
            sizes = []
            for _ in range(80):
                self.assertEqual(self.ask(self.new_visitor()), 200)
                sizes.append(len(caches["throttle"]._cache))

            self.assertLessEqual(max(sizes), 20)
            self.assertGreater(max(sizes), 15)
            self.assertEqual(throttle_keys("default"), set())
            caches["throttle"].clear()
