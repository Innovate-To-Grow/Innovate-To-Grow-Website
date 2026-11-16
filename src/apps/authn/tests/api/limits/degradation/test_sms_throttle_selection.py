from unittest.mock import patch

from django.test import override_settings

from apps.authn.security.throttles import PhoneAuthCodeRequestThrottle, sms_request_throttles
from apps.authn.tests.api.limits.degradation.test_no_ip_throttle import NoIpThrottleTestCase


class SmsThrottleSelectionTests(NoIpThrottleTestCase):
    """``sms_request_throttles`` itself: the per-IP throttle exactly when no budget can be read."""

    def assert_ip_throttled(self, throttles):
        self.assertEqual([type(throttle) for throttle in throttles], [PhoneAuthCodeRequestThrottle])

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=500)
    def test_a_budget_from_settings_removes_the_ip_throttle(self):
        self.assertEqual(sms_request_throttles(), [])

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=None)
    def test_a_budget_from_the_active_database_config_removes_the_ip_throttle(self):
        from apps.core.models import SendVerificationConfig

        config = SendVerificationConfig.objects.create(name="Production", is_active=True, sms_daily_limit=300)
        self.assertEqual(sms_request_throttles(), [])

        config.sms_daily_limit = None
        config.save()
        self.assert_ip_throttled(sms_request_throttles())

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=0)
    def test_a_cleared_budget_keeps_the_ip_throttle(self):
        # Zero explicitly clears the cap (``load_settings``); it never means an unlimited budget.
        self.assert_ip_throttled(sms_request_throttles())

    def test_any_failure_to_read_the_budget_keeps_the_ip_throttle(self):
        with (
            patch(
                "apps.authn.services.send_verification.rules.config.load_settings",
                side_effect=RuntimeError("database down"),
            ),
            self.assertLogs("apps.authn.security.throttles", level="WARNING") as logs,
        ):
            throttles = sms_request_throttles()

        self.assert_ip_throttled(throttles)
        self.assertIn("RuntimeError", logs.output[0])
        self.assertNotIn("database down", logs.output[0])
