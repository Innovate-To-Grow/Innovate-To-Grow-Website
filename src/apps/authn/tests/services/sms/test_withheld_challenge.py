"""Withheld phone challenges (``start_phone_verification(..., deliver=False)``), their timing and budget check.

A withheld challenge is what a phone sign-in for a number saved on an account but not verified gets: reserved and
counted exactly like a sent code, never sent, never approvable. The API-level behaviour is in
``apps.authn.tests.api.phone_code.test_phone_code_verified_only``.
"""

from datetime import UTC, datetime
from unittest.mock import patch

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from apps.authn.models import PhoneVerificationChallenge, SendQuotaWindow
from apps.authn.services.send_verification import quotas
from apps.authn.services.send_verification.exceptions import SendThrottled, SendVerificationUnavailable
from apps.authn.services.send_verification.quotas import check_sms_dispatch
from apps.authn.services.sms import latency
from apps.authn.services.sms.sns_verify import (
    MAX_SENDS_PER_HOUR,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
    check_phone_verification,
    start_phone_verification,
)
from apps.authn.tests.sms_provider import SMS_CODE, patch_sms_provider, sms_budget_used

PHONE = "+12025550123"
# The budget window is the UTC day; pinning it keeps a run that straddles midnight on one window.
BUDGET_DAY = datetime(2026, 9, 30, tzinfo=UTC)


def pin_budget_day(test_case):
    patcher = patch.object(quotas, "_day_window_start", side_effect=lambda _now: BUDGET_DAY)
    patcher.start()
    test_case.addCleanup(patcher.stop)


class WithheldChallengeTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.publish = patch_sms_provider(self)
        pin_budget_day(self)
        latency.reset()
        self.addCleanup(latency.reset)

    def withhold(self, **kwargs):
        return start_phone_verification(PHONE, purpose="phone_auth", context_identifier="1-US", deliver=False, **kwargs)

    def test_is_reserved_like_a_sent_code_but_never_sent(self):
        result = self.withhold()

        challenge = PhoneVerificationChallenge.objects.get()
        self.assertEqual(result, {"status": "pending", "challenge_id": str(challenge.pk)})
        self.assertEqual(
            (challenge.phone_number, challenge.purpose, challenge.context_identifier, challenge.status),
            (PHONE, "phone_auth", "1-US", PhoneVerificationChallenge.Status.PENDING),
        )
        self.assertIsNone(challenge.sent_at)
        self.assertIsNotNone(challenge.send_reserved_at)
        self.publish.assert_not_called()
        self.assertEqual(sms_budget_used(), 0)

    def test_no_code_matches_it(self):
        self.withhold()
        challenge = PhoneVerificationChallenge.objects.get()

        self.assertFalse(check_password(SMS_CODE, challenge.code_hash))
        # Hashed like a real code, so checking a guess against it costs the same.
        self.assertEqual(
            identify_hasher(challenge.code_hash).algorithm, identify_hasher(make_password(SMS_CODE)).algorithm
        )
        with self.assertRaises(PhoneVerificationInvalid):
            check_phone_verification(
                PHONE, SMS_CODE, challenge_id=challenge.pk, purpose="phone_auth", context_identifier="1-US"
            )
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, 1)  # counted like any wrong guess

    def test_it_replaces_an_earlier_code_for_the_number_like_a_send_does(self):
        start_phone_verification(PHONE, purpose="phone_auth", context_identifier="1-US")
        earlier = PhoneVerificationChallenge.objects.get()

        self.withhold()

        earlier.refresh_from_db()
        self.assertEqual(earlier.status, PhoneVerificationChallenge.Status.EXPIRED)

    def test_it_counts_toward_the_hourly_cap(self):
        for _ in range(MAX_SENDS_PER_HOUR):
            self.withhold()

        with self.assertRaises(PhoneVerificationThrottled):
            start_phone_verification(PHONE, purpose="phone_auth", context_identifier="1-US")
        self.publish.assert_not_called()

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=1)
    def test_a_spent_budget_is_refused_and_nothing_is_kept(self):
        start_phone_verification("+12025550199", purpose="phone_auth", context_identifier="1-US")

        with self.assertRaises(SendThrottled):
            self.withhold()

        self.assertFalse(PhoneVerificationChallenge.objects.filter(phone_number=PHONE).exists())
        self.assertEqual(sms_budget_used(), 1)

    def test_it_waits_like_a_send_after_giving_the_slot_back(self):
        order = []
        with (
            patch("apps.authn.services.sms.provider.release", side_effect=lambda _a: order.append("release")),
            patch.object(latency, "wait_like_a_send", side_effect=lambda: order.append("wait")),
        ):
            self.withhold()

        self.assertEqual(order, ["release", "wait"])

    def test_a_sent_code_records_how_long_the_provider_took(self):
        start_phone_verification(PHONE, purpose="phone_auth", context_identifier="1-US")

        self.assertEqual(len(latency._samples), 1)

    def test_a_failed_send_records_nothing(self):
        self.publish.side_effect = PhoneVerificationInvalid("Invalid phone number.")

        with self.assertRaises(PhoneVerificationInvalid):
            start_phone_verification(PHONE, purpose="phone_auth", context_identifier="1-US")

        self.assertEqual(len(latency._samples), 0)


class CheckSmsDispatchTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        pin_budget_day(self)

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=1)
    def test_reserves_nothing_while_the_budget_lasts(self):
        check_sms_dispatch(destination=PHONE)
        check_sms_dispatch(destination=PHONE)

        self.assertFalse(SendQuotaWindow.objects.exists())

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=1)
    def test_refuses_a_spent_budget_like_a_reservation(self):
        SendQuotaWindow.objects.create(
            kind=SendQuotaWindow.Kind.SMS_DAILY,
            scope_key="sms:global",
            window_started_at=BUDGET_DAY,
            reserved_count=1,
        )

        with self.assertRaises(SendThrottled) as caught:
            check_sms_dispatch(destination=PHONE)

        self.assertEqual((caught.exception.code, caught.exception.retry_after), ("send_throttled", 3600))
        self.assertEqual(SendQuotaWindow.objects.get().reserved_count, 1)

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=None, SEND_VERIFICATION_MODE="enforce")
    def test_enforce_mode_without_a_budget_refuses_like_a_reservation(self):
        with self.assertRaises(SendVerificationUnavailable):
            check_sms_dispatch(destination=PHONE)

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=None, SEND_VERIFICATION_MODE="observe")
    def test_no_budget_configured_refuses_nothing(self):
        check_sms_dispatch(destination=PHONE)


class LatencyTests(SimpleTestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        latency.reset()
        self.addCleanup(latency.reset)

    @override_settings(SMS_WITHHELD_SEND_DELAY_SECONDS=(0.4, 0.4))
    def test_without_sends_the_delay_comes_from_the_setting(self):
        self.assertEqual(latency.send_delay(), 0.4)

    @override_settings(SMS_WITHHELD_SEND_DELAY_SECONDS=(0.1, 0.3))
    def test_the_fallback_delay_stays_in_its_range(self):
        delays = {latency.send_delay() for _ in range(50)}

        self.assertTrue(all(0.1 <= delay <= 0.3 for delay in delays))

    def test_a_malformed_setting_falls_back_to_the_default_range(self):
        low, high = latency.DEFAULT_DELAY_RANGE
        for value in (None, "fast", (0.5,), (-1, 2), (2, 1)):
            with self.subTest(value=value), override_settings(SMS_WITHHELD_SEND_DELAY_SECONDS=value):
                self.assertTrue(low <= latency.send_delay() <= high)

    def test_recorded_sends_are_what_the_delay_is_drawn_from(self):
        for seconds in (0.11, 0.22, -1):
            latency.observe_send(seconds)

        self.assertEqual(list(latency._samples), [0.11, 0.22])  # a negative duration is not a duration
        self.assertTrue({latency.send_delay() for _ in range(50)} <= {0.11, 0.22})

    def test_only_the_latest_sends_are_kept(self):
        for index in range(latency.SAMPLE_SIZE + 5):
            latency.observe_send(index)

        self.assertEqual(len(latency._samples), latency.SAMPLE_SIZE)
        self.assertEqual(latency._samples[0], 5)

    def test_waiting_goes_through_the_limiter_sleep(self):
        latency.observe_send(0.25)

        with patch.object(latency.context, "sleep") as sleep:
            latency.wait_like_a_send()

        sleep.assert_called_once_with(0.25)
