from datetime import timedelta

from django.utils import timezone

from apps.cli_admin.models import CliAccessToken
from apps.cli_admin.tests.helpers import (
    VALID_REDIRECT_URI,
    CliApiTestCase,
    challenge_for,
    issue_code,
    make_staff,
)

TOKEN = "/admin-api/oauth/token/"


class OAuthTokenTests(CliApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="token@example.com")
        self.verifier = "verifier-" + "a" * 40
        self.challenge = challenge_for(self.verifier)

    def _body(self, code, **overrides):
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": self.verifier,
            "redirect_uri": VALID_REDIRECT_URI,
            "client_id": "i2g-admin-cli",
        }
        body.update(overrides)
        return body

    def test_happy_path_mints_token(self):
        _, raw = issue_code(self.staff, challenge=self.challenge)
        response = self.client.post(TOKEN, self._body(raw), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token_type"], "Bearer")
        self.assertGreater(response.data["expires_in"], 0)
        access = response.data["access_token"]
        # Only the hash is stored; the raw token never is.
        self.assertFalse(CliAccessToken.objects.filter(token_hash=access).exists())
        self.assertTrue(CliAccessToken.objects.filter(token_hash=CliAccessToken.hash_token(access)).exists())

    def test_wrong_verifier_is_invalid_grant_and_consumes_code(self):
        code, raw = issue_code(self.staff, challenge=self.challenge)
        response = self.client.post(TOKEN, self._body(raw, code_verifier="totally-wrong"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_grant")
        code.refresh_from_db()
        self.assertTrue(code.is_used)

    def test_reused_code_is_invalid_grant(self):
        _, raw = issue_code(self.staff, challenge=self.challenge)
        self.assertEqual(self.client.post(TOKEN, self._body(raw), format="json").status_code, 200)
        again = self.client.post(TOKEN, self._body(raw), format="json")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.data["error"], "invalid_grant")

    def test_expired_code_is_invalid_grant(self):
        _, raw = issue_code(self.staff, challenge=self.challenge, expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post(TOKEN, self._body(raw), format="json").status_code, 400)

    def test_redirect_uri_mismatch_is_invalid_grant(self):
        _, raw = issue_code(self.staff, challenge=self.challenge)
        response = self.client.post(TOKEN, self._body(raw, redirect_uri="http://127.0.0.1:9/callback"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_grant")

    def test_unknown_code_is_invalid_grant(self):
        response = self.client.post(TOKEN, self._body("no-such-code"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_grant")

    def test_demoted_member_is_invalid_grant(self):
        _, raw = issue_code(self.staff, challenge=self.challenge)
        self.staff.is_staff = False
        self.staff.save(update_fields=["is_staff"])
        response = self.client.post(TOKEN, self._body(raw), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_grant")

    def test_missing_field_is_invalid_request(self):
        _, raw = issue_code(self.staff, challenge=self.challenge)
        body = self._body(raw)
        del body["code_verifier"]
        response = self.client.post(TOKEN, body, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_request")

    def test_unsupported_grant_type(self):
        _, raw = issue_code(self.staff, challenge=self.challenge)
        response = self.client.post(TOKEN, self._body(raw, grant_type="password"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "unsupported_grant_type")

    def test_invalid_client(self):
        _, raw = issue_code(self.staff, challenge=self.challenge)
        response = self.client.post(TOKEN, self._body(raw, client_id="rogue"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_client")


class OAuthTokenNoIpThrottleTests(CliApiTestCase):
    """Staff share the campus public IP, so the token endpoint must not be limited by client address."""

    CAMPUS_IP = "169.236.0.10"

    def setUp(self):
        super().setUp()
        self.verifier = "verifier-" + "b" * 40
        self.challenge = challenge_for(self.verifier)

    def _exchange(self, code):
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": self.verifier,
            "redirect_uri": VALID_REDIRECT_URI,
            "client_id": "i2g-admin-cli",
        }
        return self.client.post(
            TOKEN, body, format="json", REMOTE_ADDR=self.CAMPUS_IP, HTTP_X_FORWARDED_FOR=self.CAMPUS_IP
        )

    def test_many_exchanges_from_one_address_are_never_throttled(self):
        # The old per-IP rate was 30/minute: 40 failed exchanges followed by 40 staff logins must all be answered.
        for attempt in range(40):
            response = self._exchange(f"no-such-code-{attempt}")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["error"], "invalid_grant")

        for index in range(40):
            staff = make_staff(email=f"campus-staff-{index}@example.com")
            _, raw = issue_code(staff, challenge=self.challenge)
            response = self._exchange(raw)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["token_type"], "Bearer")

        self.assertEqual(CliAccessToken.objects.count(), 40)

    def test_a_failed_attempt_still_burns_the_code(self):
        # What replaces the throttle is the code itself: a wrong verifier consumes it, so it cannot be retried.
        staff = make_staff(email="burn@example.com")
        code, raw = issue_code(staff, challenge=challenge_for("another-verifier-" + "c" * 40))
        self.assertEqual(self._exchange(raw).data["error"], "invalid_grant")
        code.refresh_from_db()
        self.assertTrue(code.is_used)
        self.assertEqual(CliAccessToken.objects.count(), 0)
