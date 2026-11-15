"""The maintenance bypass password cannot be brute-forced: after the policy's failures in a period every attempt is
refused (429) before any password is checked, a correct one included, until the period ends; one shared lockout,
never per IP."""

from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import SiteMaintenanceControl
from apps.core.tests.request_limits.helpers import isolate, view_limit
from apps.core.views.maintenance import BYPASS_FAILURES

URL = "/maintenance/bypass/"


@view_limit(**{BYPASS_FAILURES: (3, 60)})
class MaintenanceBypassLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = isolate(self)
        self.client = APIClient()
        SiteMaintenanceControl.objects.create(pk=1, is_maintenance=True, bypass_password="secret123")

    def attempt(self, password, ip="10.0.0.1"):
        return self.client.post(URL, {"password": password}, format="json", REMOTE_ADDR=ip)

    def test_wrong_passwords_lock_everyone_out_until_the_period_ends(self):
        statuses = [self.attempt("guess", ip=f"10.0.0.{i}").status_code for i in range(3)]
        self.assertEqual(statuses, [403, 403, 403])

        self.clock.advance(15)
        locked = self.attempt("secret123", ip="10.9.9.9")
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(
            locked.data,
            {
                "success": False,
                "error": "Too many incorrect passwords. Please try again later.",
                "code": "rate_limited",
                "retry_after": 45,
            },
        )
        self.assertEqual(locked["Retry-After"], "45")

        self.clock.advance(45)
        self.assertEqual(self.attempt("secret123").data, {"success": True})

    def test_a_locked_bypass_checks_no_password(self):
        for _ in range(3):
            self.attempt("guess")
        with patch.object(SiteMaintenanceControl, "check_bypass_password") as check:
            self.assertEqual(self.attempt("secret123").status_code, 429)
        check.assert_not_called()

    def test_correct_passwords_and_bad_requests_are_not_failures(self):
        for _ in range(5):
            self.assertEqual(self.attempt("secret123").status_code, 200)
            self.assertEqual(self.client.post(URL, {}, format="json").status_code, 400)
        self.assertEqual([self.attempt("guess").status_code for _ in range(3)], [403, 403, 403])

    def test_no_lockout_outside_maintenance(self):
        SiteMaintenanceControl.objects.filter(pk=1).update(is_maintenance=False)
        statuses = {self.attempt("guess").status_code for _ in range(6)}
        self.assertEqual(statuses, {400})

    @view_limit(**{BYPASS_FAILURES: None})
    def test_a_disabled_policy_never_locks(self):
        statuses = {self.attempt("guess").status_code for _ in range(6)}
        self.assertEqual(statuses, {403})


class MaintenanceBypassPolicyTests(TestCase):
    def test_the_default_is_twenty_failures_in_fifteen_minutes_in_the_sign_in_scope(self):
        spec = settings.REQUEST_RATE_LIMITS["scopes"][BYPASS_FAILURES]
        self.assertEqual((spec["requests"], spec["period_seconds"], spec["tier"]), (20, 900, "p0"))
        self.assertEqual(spec["parent"], "auth-sign-in")
