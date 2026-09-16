"""Fault injection around proof consumption and the delivery boundary."""

import base64
import json
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import SendDestinationState, SendVerificationChallenge, SendVerificationRequest
from apps.authn.services.email.challenges import AuthChallengeDeliveryError
from apps.authn.services.send_verification.constants import OP_REGISTER_RESEND_CODE
from apps.authn.services.send_verification.outcomes import record_otp_challenge
from apps.authn.tests.services.test_send_verification_concurrency import send, verified_request


@override_settings(
    SEND_VERIFICATION_TEST_AUTOSOLVE=False,
    SEND_VERIFICATION_MODE="enforce",
    SEND_VERIFICATION_COST=10,
    SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0,
)
class SendVerificationOutcomeTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_request_id_is_bound_to_operation_even_for_same_payload(self):
        request = verified_request()
        provider = Mock(return_value={"message": "sent"})
        self.assertEqual(send(request, provider).status_code, 202)
        response = send(request, provider, operation=OP_REGISTER_RESEND_CODE)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "send_request_conflict")
        provider.assert_called_once()

    def test_pending_request_cannot_be_dispatched_by_another_operation(self):
        from apps.authn.services.send_verification.guard import consume_and_reserve
        from apps.authn.services.send_verification.hashing import hash_value

        request = verified_request()
        consume_and_reserve(
            request,
            operation="login.request_code",
            destination_kind="email",
            destination_normalized="member@example.com",
            fingerprint=hash_value("member@example.com"),
            channel="email",
        )
        provider = Mock(return_value={"message": "sent"})
        response = send(request, provider, operation=OP_REGISTER_RESEND_CODE)
        self.assertEqual(response.status_code, 409)
        provider.assert_not_called()

    def test_constraint_failure_rolls_back_before_winner_lookup(self):
        request = verified_request()
        provider = Mock(return_value={"message": "sent"})

        def fail_quota(**kwargs):
            values = {"destination_kind": "email", "destination_normalized": "member@example.com"}
            SendDestinationState.objects.create(**values)
            SendDestinationState.objects.create(**values)

        with patch("apps.authn.services.send_verification.guard.reserve_send_quotas", side_effect=fail_quota):
            response = send(request, provider)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(SendVerificationRequest.objects.count(), 0)
        self.assertEqual(SendDestinationState.objects.count(), 0)
        self.assertEqual(SendVerificationChallenge.objects.get().status, "pending")
        provider.assert_not_called()

    def test_unknown_first_response_and_replay_retain_otp_and_reservation(self):
        request = verified_request()
        otp_id = "499738dd-35f8-415e-9b52-1d123f9e0e76"

        def provider_call():
            record_otp_challenge(otp_id)
            raise AuthChallengeDeliveryError("timeout", outcome="uncertain", challenge_id=otp_id)

        provider = Mock(side_effect=provider_call)
        first = send(request, provider)
        replay = send(request, provider)
        self.assertEqual(first.status_code, 409)
        self.assertEqual(first.data, replay.data)
        self.assertEqual(first.data["code"], "send_unknown")
        self.assertEqual(first.data["request_id"], request.data["send_request_id"])
        self.assertEqual(first.data["challenge_id"], otp_id)
        record = SendVerificationRequest.objects.get()
        self.assertEqual(record.status, "unknown")
        self.assertTrue(record.quota_reserved)
        provider.assert_called_once()

    def test_accepted_then_finalize_failure_remains_non_dispatchable(self):
        request = verified_request()
        provider = Mock(return_value={"message": "sent"})
        with patch(
            "apps.authn.services.send_verification.http.finalize_send_request", side_effect=RuntimeError("db down")
        ):
            first = send(request, provider)
        self.assertEqual(first.status_code, 409)
        self.assertEqual(SendVerificationRequest.objects.get().status, "sending")
        replay = send(request, provider)
        self.assertEqual(replay.data["code"], "send_unknown")
        provider.assert_called_once()

    def test_definite_provider_rejection_stays_definitely_failed(self):
        request = verified_request()
        provider = Mock(side_effect=AuthChallengeDeliveryError("rejected", outcome="permanent"))
        self.assertEqual(send(request, provider).status_code, 503)
        self.assertEqual(SendVerificationRequest.objects.get().status, "definitely_failed")
        self.assertEqual(send(request, provider).status_code, 503)
        provider.assert_called_once()

    def test_malformed_cost_is_invalid_and_does_not_consume(self):
        request = verified_request()
        original = json.loads(base64.b64decode(request.data["verification_payload"]))
        provider = Mock(return_value={"message": "sent"})
        for cost in [None, "bad", "10", 10.0, True, [], {}, -1]:
            with self.subTest(cost=cost):
                payload = json.loads(json.dumps(original))
                payload["challenge"]["parameters"]["cost"] = cost
                request.data["verification_payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
                response = send(request, provider)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["code"], "verification_invalid")
        provider.assert_not_called()
        self.assertEqual(SendVerificationChallenge.objects.get().status, "pending")

    def test_challenge_keeps_its_issued_cost_after_config_change(self):
        request = verified_request()
        provider = Mock(return_value={"message": "sent"})
        with override_settings(SEND_VERIFICATION_COST=25):
            self.assertEqual(send(request, provider).status_code, 202)
        provider.assert_called_once()
