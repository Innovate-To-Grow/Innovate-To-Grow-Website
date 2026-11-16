from apps.authn.services.security import login_guard
from apps.authn.tests.api.login.lockout.test_login_lockout import EMAIL, PASSWORD, PHONE, LoginLockoutTestCase


class SprayDetectionTests(LoginLockoutTestCase):
    """Everyone on campus shares one address: a spray is logged for an alarm, never answered with a lock."""

    def test_a_password_spray_is_logged_once_and_nobody_is_refused(self):
        count = login_guard.SPRAY_ALERT_THRESHOLD + 20
        with self.assertLogs("apps.authn.services.login_guard", "WARNING") as logs:
            statuses = [self.login(f"sprayed{index}@example.com").status_code for index in range(count)]

        self.assertEqual(set(statuses), {400})
        self.assertEqual(len(logs.records), 1)
        message = logs.records[0].getMessage()
        self.assertTrue(message.startswith("login_guard.failure_spike "), message)
        for fragment in ("sprayed", "example", "127.0.0.1"):
            self.assertNotIn(fragment, message)

        # Same address, same minute: members still sign in, and still get their own ten failures.
        self.assertEqual(self.login(EMAIL, PASSWORD).status_code, 200)
        self.assertEqual(self.login(PHONE, PASSWORD).status_code, 200)
        self.assertEqual(self.fail_times(10), [400] * 10)
        self.assertLocked(self.login(EMAIL, PASSWORD))
