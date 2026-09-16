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

from apps.authn.models import SendDestinationState, SendQuotaWindow, SendVerificationChallenge, SendVerificationRequest
from apps.authn.services.send_verification.config import load_settings
from apps.authn.services.send_verification.constants import OP_LOGIN_REQUEST_CODE, OP_PHONE_AUTH_REQUEST_CODE
from apps.authn.services.send_verification.hashing import hash_value
from apps.authn.services.send_verification.http import guarded_send


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

    def test_sms_daily_limit_serializes_different_destinations(self):
        destinations = ["+12025550100", "+12025550101"]
        requests = [
            verified_request(destination=value, kind="phone", operation=OP_PHONE_AUTH_REQUEST_CODE)
            for value in destinations
        ]
        provider = Mock(return_value={"message": "sent"})
        responses = self.parallel(
            [
                lambda i=i: send(
                    requests[i],
                    provider,
                    destination=destinations[i],
                    channel="sms",
                    operation=OP_PHONE_AUTH_REQUEST_CODE,
                )
                for i in range(2)
            ]
        )
        self.assertEqual(sorted(response.status_code for response in responses), [202, 429])
        provider.assert_called_once()
        self.assertEqual(SendQuotaWindow.objects.get(kind="sms_daily").reserved_count, 1)
        self.assertEqual(SendVerificationRequest.objects.filter(quota_reserved=True).count(), 1)
