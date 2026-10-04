"""Unit tests for the actor identity that budgets and throttles are keyed on."""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.test import SimpleTestCase, override_settings

from apps.system_intelligence.services.public_assistant import actors, budget

DAY = 24 * 60 * 60


def at(seconds_from_now):
    """Patch the clock django.core.signing stamps and checks signatures with."""
    return patch("django.core.signing.time.time", return_value=time.time() + seconds_from_now)


class VisitorTokenTests(SimpleTestCase):
    def test_issued_value_resolves_to_a_visitor_with_a_64_hex_key(self):
        actor = actors.visitor_actor(actors.issue_visitor_token())

        self.assertEqual(actor.kind, actors.KIND_VISITOR)
        self.assertRegex(actor.key, r"^[0-9a-f]{64}$")
        self.assertIsNone(actor.replacement)

    def test_each_issued_value_is_a_distinct_visitor(self):
        keys = {actors.visitor_actor(actors.issue_visitor_token()).key for _ in range(50)}

        self.assertEqual(len(keys), 50)

    def test_the_same_value_always_resolves_to_the_same_visitor(self):
        presented = actors.issue_visitor_token()

        self.assertEqual(actors.visitor_actor(presented), actors.visitor_actor(presented))

    def test_the_raw_visitor_id_never_appears_in_the_budget_key(self):
        with patch.object(actors.secrets, "token_hex", return_value="ab" * 16):
            presented = actors.issue_visitor_token()

        self.assertNotIn("ab" * 16, actors.visitor_actor(presented).key)

    def test_missing_and_malformed_values_fall_into_the_one_legacy_bucket(self):
        legacy_key = actors.legacy_actor().key
        for presented in (None, "", "   ", "not-a-signed-value", "a:b:c", 123, 1.5, True, [], ["x"], {}, {"v": "x"}):
            with self.subTest(presented=presented):
                actor = actors.visitor_actor(presented)
                self.assertEqual(actor.kind, actors.KIND_LEGACY)
                self.assertEqual(actor.key, legacy_key)

    def test_oversized_value_is_rejected_without_verifying_it(self):
        with patch.object(actors.signing, "loads") as loads:
            actor = actors.visitor_actor("x" * 513)

        self.assertEqual(actor.kind, actors.KIND_LEGACY)
        loads.assert_not_called()

    def test_tampered_signature_is_legacy(self):
        presented = actors.issue_visitor_token()
        flipped = "A" if presented[-1] != "A" else "B"

        self.assertEqual(actors.visitor_actor(presented[:-1] + flipped).kind, actors.KIND_LEGACY)

    def test_tampered_payload_is_legacy(self):
        presented = actors.issue_visitor_token()
        _payload, rest = presented.split(":", 1)
        forged_payload = signing.b64_encode(b'{"v":"' + b"f" * 32 + b'"}').decode()

        self.assertEqual(actors.visitor_actor(f"{forged_payload}:{rest}").kind, actors.KIND_LEGACY)

    def test_value_signed_for_another_purpose_is_legacy(self):
        # Same SECRET_KEY, different salt: e.g. a value lifted from another
        # signed feature of this site must not pass as a visitor identity.
        other = signing.dumps({"v": "c" * 32}, salt="some.other.feature")

        self.assertEqual(actors.visitor_actor(other).kind, actors.KIND_LEGACY)

    def test_value_signed_with_another_key_is_legacy(self):
        with override_settings(SECRET_KEY="an-attacker-chosen-signing-key"):
            self_minted = actors.issue_visitor_token()

        self.assertEqual(actors.visitor_actor(self_minted).kind, actors.KIND_LEGACY)

    def test_correctly_signed_value_with_the_wrong_shape_is_legacy(self):
        for payload in ({"v": 5}, {"v": "short"}, {"x": "c" * 32}, ["c" * 32], "c" * 32):
            with self.subTest(payload=payload):
                presented = signing.dumps(payload, salt=actors._SIGNING_SALT)
                self.assertEqual(actors.visitor_actor(presented).kind, actors.KIND_LEGACY)

    def test_expired_value_is_legacy_and_carries_a_new_identity(self):
        presented = actors.issue_visitor_token()
        original = actors.visitor_actor(presented)

        with at(actors.VISITOR_MAX_AGE_SECONDS + 60):
            expired = actors.visitor_actor(presented)
            replacement = actors.visitor_actor(expired.replacement)

        self.assertEqual(expired.kind, actors.KIND_LEGACY)
        self.assertEqual(expired.key, actors.legacy_actor().key)
        # The replacement is a brand-new visitor, not the expired one revived.
        self.assertEqual(replacement.kind, actors.KIND_VISITOR)
        self.assertNotEqual(replacement.key, original.key)

    def test_ageing_value_keeps_its_identity_and_is_re_signed(self):
        presented = actors.issue_visitor_token()
        original = actors.visitor_actor(presented)

        with at(actors.VISITOR_RENEW_AFTER_SECONDS + 60):
            ageing = actors.visitor_actor(presented)
            renewed = actors.visitor_actor(ageing.replacement)

        self.assertEqual(ageing.kind, actors.KIND_VISITOR)
        self.assertEqual(ageing.key, original.key)
        self.assertIsNotNone(ageing.replacement)
        self.assertNotEqual(ageing.replacement, presented)
        # Same visitor, same budget row, and the fresh signature needs no renewal.
        self.assertEqual(renewed.key, original.key)
        self.assertIsNone(renewed.replacement)

    def test_value_is_honoured_for_about_thirty_days(self):
        self.assertEqual(actors.VISITOR_MAX_AGE_SECONDS, 30 * DAY)
        presented = actors.issue_visitor_token()

        with at(29 * DAY):
            self.assertEqual(actors.visitor_actor(presented).kind, actors.KIND_VISITOR)
        with at(31 * DAY):
            self.assertEqual(actors.visitor_actor(presented).kind, actors.KIND_LEGACY)

    def test_legacy_actor_always_offers_a_usable_replacement(self):
        legacy = actors.legacy_actor()

        self.assertEqual(actors.visitor_actor(legacy.replacement).kind, actors.KIND_VISITOR)
        self.assertNotEqual(legacy.replacement, actors.legacy_actor().replacement)


class ActorKeyTests(SimpleTestCase):
    def test_member_keys_are_per_member_and_stable(self):
        first, second = uuid.uuid4(), uuid.uuid4()

        self.assertEqual(actors.member_actor(first), actors.member_actor(first))
        self.assertNotEqual(actors.member_actor(first).key, actors.member_actor(second).key)
        self.assertEqual(actors.member_actor(first).kind, actors.KIND_MEMBER)
        self.assertRegex(actors.member_actor(first).key, r"^[0-9a-f]{64}$")
        self.assertNotIn(first.hex, actors.member_actor(first).key)

    def test_actor_namespaces_never_collide_with_each_other_or_the_global_rows(self):
        shared_id = "d" * 32
        with patch.object(actors.secrets, "token_hex", return_value=shared_id):
            visitor = actors.visitor_actor(actors.issue_visitor_token())
        global_keys = set(budget.GLOBAL_BUDGET_KEYS.values())
        keys = {
            visitor.key,
            actors.member_actor(shared_id).key,
            actors.legacy_actor().key,
            *global_keys,
        }

        self.assertEqual(len(global_keys), 2)
        self.assertEqual(len(keys), 5)
        for key in global_keys:
            self.assertRegex(key, r"^[0-9a-f]{64}$")

    def test_only_the_legacy_actor_is_exempt_from_the_per_actor_token_limit(self):
        visitor = actors.visitor_actor(actors.issue_visitor_token())
        member = actors.member_actor(uuid.uuid4())

        self.assertEqual(visitor.kind, actors.KIND_VISITOR)
        self.assertEqual(actors.actor_token_limit(visitor, 50_000), 50_000)
        self.assertEqual(actors.actor_token_limit(member, 50_000), 50_000)
        self.assertEqual(actors.actor_token_limit(actors.legacy_actor(), 50_000), 0)
        # A limit the admin switched off stays off for everybody.
        self.assertEqual(actors.actor_token_limit(visitor, 0), 0)


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
