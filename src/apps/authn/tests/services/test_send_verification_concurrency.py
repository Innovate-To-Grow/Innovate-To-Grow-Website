"""Exercise PostgreSQL locks and uniqueness with independent request connections."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, local
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import Mock, patch
from uuid import uuid4

from altcha import Payload, create_challenge, solve_challenge
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.authn.models import (
    PhoneVerificationChallenge,
    SendDestinationState,
    SendQuotaWindow,
    SendVerificationChallenge,
    SendVerificationRequest,
)
from apps.authn.services.send_verification.config import load_settings
from apps.authn.services.send_verification.constants import OP_LOGIN_REQUEST_CODE, OP_PHONE_AUTH_REQUEST_CODE
from apps.authn.services.send_verification.hashing import hash_value
from apps.authn.services.send_verification.http import guarded_send
from apps.authn.services.sms import start_phone_verification

SMS_BUDGET_SPENT_ANSWER = {
    "code": "send_throttled",
    "detail": "The SMS sending budget for today has been reached.",
    "retry_after": 3600,
}


def verified_request(
    *, destination="member@example.com", operation=OP_LOGIN_REQUEST_CODE, kind="email", request_id=None
):
    config = load_settings()
    expires_at = timezone.now() + timedelta(minutes=5)
    row = SendVerificationChallenge.objects.create(
        operation=operation,
        destination_kind=kind,
        destination_normalized=destination,
        principal_type="session",
        principal_key=hash_value("shared-test-session"),
        algorithm=config.algorithm,
        cost=config.cost,
        expires_at=expires_at,
    )
    challenge = create_challenge(
        algorithm=config.algorithm,
        cost=config.cost,
        expires_at=expires_at,
        hmac_secret=config.hmac_secret,
        hmac_key_secret=config.hmac_key_secret or None,
        data={"challenge_id": str(row.pk), "operation": operation},
    )
    solution = solve_challenge(challenge)
    assert solution is not None
    return SimpleNamespace(
        data={
            "verification_challenge_id": str(row.pk),
            "verification_payload": Payload(challenge, solution).to_base64(),
            "send_request_id": str(request_id or uuid4()),
        },
        user=AnonymousUser(),
        session=SimpleNamespace(session_key="shared-test-session"),
    )


def send(request, provider, *, destination="member@example.com", operation=OP_LOGIN_REQUEST_CODE, channel="email"):
    return guarded_send(
        request,
        operation=operation,
        destination_kind="phone" if channel == "sms" else "email",
        destination_normalized=destination,
        fingerprint=hash_value(destination),
        channel=channel,
        perform=lambda: (provider(), 202),
    )


def send_sms(request, destination):
    """A protected passwordless-phone send through the real SMS service (the caller replaces the provider)."""

    def perform():
        started = start_phone_verification(destination, purpose="phone_auth", context_identifier="1-US")
        return {"challenge_id": started["challenge_id"]}, 202

    return guarded_send(
        request,
        operation=OP_PHONE_AUTH_REQUEST_CODE,
        destination_kind="phone",
        destination_normalized=destination,
        fingerprint=hash_value(destination),
        channel="sms",
        perform=perform,
    )


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks and independent transactions")
@override_settings(
    SEND_VERIFICATION_TEST_AUTOSOLVE=False,
    SEND_VERIFICATION_MODE="enforce",
    SEND_VERIFICATION_COST=10,
    SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0,
    SEND_VERIFICATION_DESTINATION_HOURLY_LIMIT=100,
    SEND_VERIFICATION_SMS_DAILY_LIMIT=1,
)
class SendVerificationPostgresLockTests(TransactionTestCase):
    def setUp(self):
        cache.clear()

    def parallel(self, calls):
        from apps.authn.services.send_verification.guard import _load_existing_request

        barrier = Barrier(len(calls))
        missed_lookup = Barrier(len(calls))
        state = local()

        def synchronized_lookup(*args, **kwargs):
            result = _load_existing_request(*args, **kwargs)
            if not getattr(state, "looked_up", False):
                state.looked_up = True
                self.assertIsNone(result)
                # Hold every caller immediately after the initial missing-row
                # read, forcing the lock waiter/unique-conflict paths to run.
                missed_lookup.wait(timeout=5)
            return result

        def run(call):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=5)
                return call()
            finally:
                connections.close_all()

        with (
            patch(
                "apps.authn.services.send_verification.guard._load_existing_request", side_effect=synchronized_lookup
            ),
            ThreadPoolExecutor(max_workers=len(calls)) as pool,
        ):
            futures = [pool.submit(run, call) for call in calls]
            return [future.result(timeout=15) for future in futures]

    def test_same_request_same_challenge_sends_once(self):
        request = verified_request()
        provider = Mock(return_value={"message": "sent"})
        responses = self.parallel([lambda: send(request, provider), lambda: send(request, provider)])
        self.assertTrue(all(response.status_code in {202, 409} for response in responses))
        provider.assert_called_once()
        self.assertEqual(SendVerificationRequest.objects.filter(quota_reserved=True).count(), 1)
        self.assertEqual(SendDestinationState.objects.count(), 1)
        self.assertEqual(send(request, provider).status_code, 202)
        provider.assert_called_once()

    def test_same_challenge_different_request_cannot_double_send(self):
        request = verified_request()
        second = SimpleNamespace(**vars(request))
        second.data = {**request.data, "send_request_id": str(uuid4())}
        provider = Mock(return_value={"message": "sent"})
        responses = self.parallel([lambda: send(request, provider), lambda: send(second, provider)])
        self.assertEqual(sorted(response.status_code for response in responses), [202, 400])
        provider.assert_called_once()
        self.assertEqual(SendVerificationRequest.objects.count(), 1)

    @override_settings(SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=60)
    def test_same_request_different_challenge_replays_without_second_reservation(self):
        request = verified_request()
        other = verified_request(request_id=request.data["send_request_id"])
        provider = Mock(return_value={"message": "sent"})
        responses = self.parallel([lambda: send(request, provider), lambda: send(other, provider)])
        self.assertTrue(all(response.status_code in {202, 409} for response in responses))
        provider.assert_called_once()
        self.assertEqual(SendVerificationRequest.objects.filter(quota_reserved=True).count(), 1)
        self.assertEqual(SendVerificationChallenge.objects.filter(status="consumed").count(), 1)

    @override_settings(SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=60)
    def test_concurrent_first_destination_row_reserves_only_one_cooldown(self):
        first, second = verified_request(), verified_request()
        provider = Mock(return_value={"message": "sent"})
        responses = self.parallel([lambda: send(first, provider), lambda: send(second, provider)])
        self.assertEqual(sorted(response.status_code for response in responses), [202, 429])
        provider.assert_called_once()
        self.assertEqual(SendDestinationState.objects.count(), 1)
        self.assertEqual(SendVerificationRequest.objects.filter(quota_reserved=True).count(), 1)

    def parallel_sms(self, destinations):
        """One protected SMS send per destination, all at once, with the provider call replaced by a mock.

        The early budget check is switched off so every request reaches the dispatch step, as when they all arrive
        before any reservation has committed: the row lock in ``reserve_sms_dispatch`` alone has to decide.
        """
        requests = [
            verified_request(destination=value, kind="phone", operation=OP_PHONE_AUTH_REQUEST_CODE)
            for value in destinations
        ]
        aws_config = SimpleNamespace(render_sms_otp_message=lambda code: f"Code: {code}")
        with (
            patch("apps.authn.services.sms.sns_verify._assert_configured", return_value=aws_config),
            patch("apps.authn.services.sms.sns_verify._publish_sms", return_value="message-id") as publish,
            patch("apps.authn.services.send_verification.quotas._sms_budget_spent", return_value=False),
        ):
            responses = self.parallel(
                [lambda i=i: send_sms(requests[i], destinations[i]) for i in range(len(destinations))]
            )
        return responses, publish

    def assert_budget_refusals(self, responses, *, sent):
        statuses = sorted(response.status_code for response in responses)
        self.assertEqual(statuses, [202] * sent + [429] * (len(responses) - sent))
        for response in responses:
            if response.status_code == 429:
                self.assertEqual(response.data, SMS_BUDGET_SPENT_ANSWER)
                self.assertEqual(response["Retry-After"], "3600")

    def test_sms_daily_limit_serializes_different_destinations(self):
        responses, publish = self.parallel_sms(["+12025550100", "+12025550101"])

        self.assert_budget_refusals(responses, sent=1)
        publish.assert_called_once()
        self.assertEqual(SendQuotaWindow.objects.get(kind="sms_daily").reserved_count, 1)
        # The refused send rolled its code back with the reservation; its request row records the refusal.
        self.assertEqual(PhoneVerificationChallenge.objects.count(), 1)
        self.assertEqual(
            sorted(SendVerificationRequest.objects.values_list("status", flat=True)),
            ["definitely_failed", "provider_accepted"],
        )

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=2)
    def test_concurrent_sms_sends_never_overspend_the_budget(self):
        responses, publish = self.parallel_sms([f"+1202555011{index}" for index in range(5)])

        self.assert_budget_refusals(responses, sent=2)
        self.assertEqual(publish.call_count, 2)
        self.assertEqual(SendQuotaWindow.objects.get(kind="sms_daily").reserved_count, 2)
        self.assertEqual(PhoneVerificationChallenge.objects.count(), 2)
