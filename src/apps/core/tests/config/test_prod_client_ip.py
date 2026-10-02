"""Production must key DRF throttles on the real client, not on the client-supplied ``X-Forwarded-For``.

DRF's ``get_ident()`` reads ``REST_FRAMEWORK["NUM_PROXIES"]`` (``api_settings``), not the top-level Django
setting. Without it the whole header is the throttle identity and a forged leading entry gets a fresh bucket.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework.request import Request
from rest_framework.test import APITestCase
from rest_framework.throttling import BaseThrottle

from apps.core.tests.config.test_prod_cache import PROD_ENV, reload_prod_settings

ALB_ADDRESS = "10.0.5.7"  # REMOTE_ADDR behind the ALB: the load balancer, never the client
REAL_CLIENT = "203.0.113.9"  # what the ALB appended to X-Forwarded-For
LOGIN_URL = "/authn/login/"  # LoginRateThrottle: 10/minute per IP


def production_rest_framework():
    with patch.dict("os.environ", PROD_ENV, clear=True):
        return reload_prod_settings().REST_FRAMEWORK


class ProductionNumProxiesSettingsTests(SimpleTestCase):
    def test_rest_framework_trusts_one_proxy_hop_by_default(self):
        with patch.dict("os.environ", PROD_ENV, clear=True):
            prod_settings = reload_prod_settings()

        self.assertEqual(prod_settings.REST_FRAMEWORK["NUM_PROXIES"], 1)
        self.assertEqual(prod_settings.NUM_PROXIES, 1)

    def test_rest_framework_and_top_level_setting_share_one_env_value(self):
        with patch.dict("os.environ", {**PROD_ENV, "NUM_PROXIES": "2"}, clear=True):
            prod_settings = reload_prod_settings()

        self.assertEqual(prod_settings.REST_FRAMEWORK["NUM_PROXIES"], 2)
        self.assertEqual(prod_settings.NUM_PROXIES, 2)

    def test_throttle_rates_are_untouched(self):
        from config.settings.base import REST_FRAMEWORK as base_rest_framework

        rest_framework = production_rest_framework()

        self.assertEqual(rest_framework["DEFAULT_THROTTLE_RATES"], base_rest_framework["DEFAULT_THROTTLE_RATES"])

    def test_production_does_not_mutate_the_dict_shared_with_local_and_test(self):
        from config.settings.base import REST_FRAMEWORK as base_rest_framework

        production_rest_framework()

        self.assertNotIn("NUM_PROXIES", base_rest_framework)

    def test_rejects_zero_negative_and_non_integer_values(self):
        for value in ("0", "-1", "one"):
            with self.subTest(value=value), patch.dict("os.environ", {**PROD_ENV, "NUM_PROXIES": value}, clear=True):
                with self.assertRaises(ImproperlyConfigured):
                    reload_prod_settings()


class ForgedForwardedForThrottleIdentityTests(SimpleTestCase):
    def _ident(self, forwarded_for):
        request = Request(RequestFactory().get("/", HTTP_X_FORWARDED_FOR=forwarded_for, REMOTE_ADDR=ALB_ADDRESS))
        return BaseThrottle().get_ident(request)

    def test_forged_leading_entry_does_not_change_the_identity(self):
        with override_settings(REST_FRAMEWORK=production_rest_framework()):
            baseline = self._ident(REAL_CLIENT)

            for forged in ("1.2.3.4", "5.6.7.8", "1.2.3.4, 5.6.7.8", "9.9.9.9,   "):
                with self.subTest(forged=forged):
                    self.assertEqual(self._ident(f"{forged}, {REAL_CLIENT}"), baseline)

        self.assertEqual(baseline, REAL_CLIENT)

    def test_without_xff_the_identity_is_remote_addr(self):
        with override_settings(REST_FRAMEWORK=production_rest_framework()):
            request = Request(RequestFactory().get("/", REMOTE_ADDR=ALB_ADDRESS))
            self.assertEqual(BaseThrottle().get_ident(request), ALB_ADDRESS)


class ForgedForwardedForThrottleLimitTests(APITestCase):
    """End to end through a real per-IP throttle (login, 10/minute)."""

    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _login(self, forwarded_for):
        return self.client.post(
            LOGIN_URL, {}, format="json", HTTP_X_FORWARDED_FOR=forwarded_for, REMOTE_ADDR=ALB_ADDRESS
        )

    def test_rotating_a_forged_leading_entry_still_hits_the_limit(self):
        with override_settings(REST_FRAMEWORK=production_rest_framework()):
            for attempt in range(10):
                response = self._login(f"198.51.100.{attempt}, {REAL_CLIENT}")
                self.assertNotEqual(response.status_code, 429, f"attempt {attempt} throttled early")

            blocked = self._login(f"198.51.100.200, {REAL_CLIENT}")
            other_client = self._login("198.51.100.201, 203.0.113.10")

        self.assertEqual(blocked.status_code, 429)
        self.assertNotEqual(other_client.status_code, 429)
