from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.authn.models import PhoneVerificationChallenge, SendQuotaWindow
from apps.authn.services.send_verification.rules.exceptions import SendThrottled
from apps.authn.services.sms.sns_verify import (
    MAX_SENDS_PER_HOUR,
    PhoneVerificationDeliveryError,
    PhoneVerificationThrottled,
    check_phone_verification,
    start_phone_verification,
)
from apps.authn.tests.helpers.sms_provider import SMS_CODE, patch_sms_provider, sms_budget_used
from apps.authn.tests.services.sms.budget.test_sms_budget_reservation import OTHER_PHONE, PHONE, QUOTA_LOGGER


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
