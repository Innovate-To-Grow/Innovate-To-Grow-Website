"""Where and how the global SMS daily budget is reserved (``send_verification.quotas`` and ``sns_verify``).

The budget is reserved at dispatch, in the transaction that stores the code, and nowhere else. The API-level
behaviour is in ``apps.authn.tests.api.test_sms_daily_budget``; real row-lock contention is in
``test_send_verification_concurrency`` (PostgreSQL only).
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge, SendDestinationState, SendQuotaWindow
from apps.authn.services.send_verification.config import load_settings
from apps.authn.services.send_verification.exceptions import SendThrottled, SendVerificationUnavailable
from apps.authn.services.send_verification.quotas import (
    _sms_budget_spent,
    reserve_send_quotas,
    reserve_sms_dispatch,
)
from apps.authn.services.sms.sns_verify import (
    MAX_SENDS_PER_HOUR,
    PhoneVerificationDeliveryError,
    PhoneVerificationThrottled,
    check_phone_verification,
    start_phone_verification,
)
from apps.authn.tests.sms_provider import SMS_CODE, patch_sms_provider, sms_budget_used

PHONE = "+12025550123"
OTHER_PHONE = "+12025550199"
QUOTA_LOGGER = "apps.authn.send_verification"


class ReserveSmsDispatchTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=2)
    def test_units_are_counted_up_to_the_limit_then_refused(self):
        reserve_sms_dispatch(destination=PHONE)
        reserve_sms_dispatch(destination=OTHER_PHONE)
        self.assertEqual(sms_budget_used(), 2)

        with self.assertLogs(QUOTA_LOGGER, level="INFO") as logs, self.assertRaises(SendThrottled) as caught:
            reserve_sms_dispatch(destination=PHONE)

        self.assertEqual(sms_budget_used(), 2)
        self.assertEqual(
            (caught.exception.code, caught.exception.http_status, caught.exception.retry_after),
            ("send_throttled", 429, 3600),
        )
        self.assertEqual(caught.exception.detail, "The SMS sending budget for today has been reached.")
        (line,) = logs.output
        self.assertIn("send_verification.quota_sms_daily channel=sms destination_hash=", line)
        self.assertNotIn("2025550123", line)

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=1)
    def test_each_utc_day_has_its_own_budget(self):
        last_second = datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC)

        reserve_sms_dispatch(destination=PHONE, now=last_second)
        with self.assertLogs(QUOTA_LOGGER, level="INFO"), self.assertRaises(SendThrottled):
            reserve_sms_dispatch(destination=PHONE, now=last_second)
        reserve_sms_dispatch(destination=PHONE, now=last_second + timedelta(seconds=1))

        self.assertEqual(
            list(
                SendQuotaWindow.objects.order_by("window_started_at").values_list(
                    "kind", "scope_key", "window_started_at", "reserved_count"
                )
            ),
            [
                ("sms_daily", "sms:global", datetime(2026, 9, 30, tzinfo=UTC), 1),
                ("sms_daily", "sms:global", datetime(2026, 10, 1, tzinfo=UTC), 1),
            ],
        )

    @override_settings(SEND_VERIFICATION_MODE="observe")
    def test_without_a_limit_nothing_is_reserved_in_observe_mode(self):
        for limit in (None, 0):
            with self.subTest(limit=limit), override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=limit):
                reserve_sms_dispatch(destination=PHONE)

                self.assertFalse(SendQuotaWindow.objects.exists())

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=None, SEND_VERIFICATION_MODE="enforce")
    def test_enforce_mode_without_a_limit_refuses_to_send(self):
        with self.assertRaises(SendVerificationUnavailable):
            reserve_sms_dispatch(destination=PHONE)

        self.assertFalse(SendQuotaWindow.objects.exists())

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT="not-a-number")
    def test_an_unreadable_limit_refuses_to_send(self):
        with self.assertRaises(SendVerificationUnavailable):
            reserve_sms_dispatch(destination=PHONE)

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=2)
    def test_the_early_check_is_one_read_that_creates_nothing(self):
        config, now = load_settings(), timezone.now()

        with self.assertNumQueries(1):
            self.assertFalse(_sms_budget_spent(config, now))
        self.assertFalse(SendQuotaWindow.objects.exists())

        reserve_sms_dispatch(destination=PHONE, now=now)
        self.assertFalse(_sms_budget_spent(config, now))
        reserve_sms_dispatch(destination=PHONE, now=now)
        with self.assertNumQueries(1):
            self.assertTrue(_sms_budget_spent(config, now))
        self.assertFalse(_sms_budget_spent(config, now + timedelta(days=1)))  # tomorrow's budget is untouched


@override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=2)
class DestinationReservationTests(TestCase):
    """``reserve_send_quotas`` (every request) reserves the destination and never the SMS budget."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()

    @staticmethod
    def reserve(channel="sms", kind="phone", destination=PHONE, **kwargs):
        reserve_send_quotas(
            config=load_settings(), channel=channel, destination_kind=kind, destination_normalized=destination, **kwargs
        )

    @staticmethod
    def spend_budget():
        for _ in range(2):
            reserve_sms_dispatch(destination=OTHER_PHONE)

    def test_reserving_a_destination_does_not_touch_the_sms_budget(self):
        self.reserve()
        self.reserve(refuse_spent_sms_budget=True)

        self.assertFalse(SendQuotaWindow.objects.exists())
        self.assertIsNotNone(SendDestinationState.objects.get().last_reserved_at)

    def test_a_spent_budget_refuses_only_the_callers_that_ask_for_it(self):
        self.spend_budget()

        self.reserve()  # password reset: reserved as usual, the budget decides nothing here
        with self.assertLogs(QUOTA_LOGGER, level="INFO"), self.assertRaises(SendThrottled) as caught:
            self.reserve(destination=OTHER_PHONE, refuse_spent_sms_budget=True)

        self.assertEqual(caught.exception.detail, "The SMS sending budget for today has been reached.")
        self.assertEqual(caught.exception.retry_after, 3600)
        # The refused request did not reserve its destination's cooldown.
        self.assertIsNone(SendDestinationState.objects.get(destination_normalized=OTHER_PHONE).last_reserved_at)
        self.assertEqual(sms_budget_used(), 2)

    def test_the_sms_budget_never_refuses_an_email(self):
        self.spend_budget()

        self.reserve(channel="email", kind="email", destination="member@example.com", refuse_spent_sms_budget=True)

        self.assertIsNotNone(SendDestinationState.objects.get(destination_kind="email").last_reserved_at)

    @override_settings(SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=60)
    def test_the_cooldown_answers_before_the_budget(self):
        self.reserve()
        self.spend_budget()

        with self.assertLogs(QUOTA_LOGGER, level="INFO"), self.assertRaises(SendThrottled) as caught:
            self.reserve(refuse_spent_sms_budget=True)

        self.assertEqual(caught.exception.detail, "Please wait before requesting another code.")


@override_settings(
    SEND_VERIFICATION_SMS_DAILY_LIMIT=1, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class DispatchReservationTests(TestCase):
    """``start_phone_verification`` reserves the unit with the code it stores, right before the provider call."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.publish = patch_sms_provider(self)

    def test_one_unit_per_provider_call(self):
        with override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=5):
            for _ in range(3):
                start_phone_verification(PHONE)

        self.assertEqual(self.publish.call_count, 3)
        self.assertEqual(sms_budget_used(), 3)

    def test_a_spent_budget_stores_nothing_sends_nothing_and_keeps_the_earlier_code(self):
        first = start_phone_verification(PHONE)

        with self.assertLogs(QUOTA_LOGGER, level="INFO"), self.assertRaises(SendThrottled):
            start_phone_verification(PHONE)
        with self.assertLogs(QUOTA_LOGGER, level="INFO"), self.assertRaises(SendThrottled):
            start_phone_verification(OTHER_PHONE)

        self.publish.assert_called_once()
        self.assertEqual(sms_budget_used(), 1)
        # The refused sends rolled back with their reservation: no new row, and the code already sent was not
        # superseded, so it still verifies.
        self.assertEqual(
            list(PhoneVerificationChallenge.objects.values_list("phone_number", "status")), [(PHONE, "pending")]
        )
        self.assertEqual(
            str(check_phone_verification(PHONE, SMS_CODE, challenge_id=first["challenge_id"]).pk), first["challenge_id"]
        )

    def test_the_budget_is_reserved_after_the_code_is_stored_and_before_the_provider_is_called(self):
        statements_before_provider = []

        def provider(**_kwargs):
            statements_before_provider.append(len(queries.captured_queries))
            return "provider-message-id"

        self.publish.side_effect = provider

        with CaptureQueriesContext(connection) as queries:
            start_phone_verification(PHONE)

        statements = [query["sql"] for query in queries.captured_queries]
        stored = next(
            i for i, sql in enumerate(statements) if sql.startswith('INSERT INTO "authn_phoneverificationchallenge"')
        )
        reserved = next(i for i, sql in enumerate(statements) if sql.startswith('UPDATE "authn_sendquotawindow"'))
        self.assertLess(stored, reserved)
        # The budget UPDATE is the reservation transaction's last statement: next comes its commit (a savepoint
        # release inside a test), and only then the provider call.
        self.assertTrue(statements[reserved + 1].startswith("RELEASE SAVEPOINT"), statements[reserved + 1])
        self.assertLess(reserved + 1, statements_before_provider[0])

    def test_a_number_over_its_hourly_cap_is_refused_before_the_budget(self):
        now = timezone.now()
        PhoneVerificationChallenge.objects.bulk_create(
            PhoneVerificationChallenge(
                phone_number=PHONE,
                purpose=PhoneVerificationChallenge.Purpose.PHONE_AUTH,
                code_hash=make_password(None),
                status=PhoneVerificationChallenge.Status.EXPIRED,
                expires_at=now,
                send_reserved_at=now,
            )
            for _ in range(MAX_SENDS_PER_HOUR)
        )

        with self.assertRaises(PhoneVerificationThrottled):
            start_phone_verification(PHONE)

        self.publish.assert_not_called()
        self.assertFalse(SendQuotaWindow.objects.exists())

    def test_an_unconfigured_provider_is_refused_before_the_budget(self):
        unconfigured = PhoneVerificationDeliveryError("SMS is not configured.", outcome="permanent")

        with (
            patch("apps.authn.services.sms.sns_verify._assert_configured", side_effect=unconfigured),
            self.assertRaises(PhoneVerificationDeliveryError),
        ):
            start_phone_verification(PHONE)

        self.assertFalse(SendQuotaWindow.objects.exists())
        self.assertFalse(PhoneVerificationChallenge.objects.exists())

    def test_a_provider_failure_keeps_the_unit(self):
        self.publish.side_effect = PhoneVerificationDeliveryError("rejected", outcome="permanent")

        with self.assertRaises(PhoneVerificationDeliveryError):
            start_phone_verification(PHONE)

        self.assertEqual(sms_budget_used(), 1)
        self.assertEqual(PhoneVerificationChallenge.objects.get().status, PhoneVerificationChallenge.Status.EXPIRED)
