"""LoginLinkView token exchange: Authorization-header independence, error codes, rejection logs, input hardening."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.authn.tests.helpers import (
    MALFORMED_TOKEN_BODIES,
    UNUSABLE_TOKEN_BODIES,
    access_token_owner_id,
    bearer_header,
    stale_bearer_headers,
)
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, LoginLinkToken

URL = "/mail/login-link/"
LEGACY_URL = "/mail/magic-login/"
VIEW_LOGGER = "apps.mail.views.login_link"

INVALID_LINK = {"detail": "Invalid login link.", "code": "invalid_link"}
EXPIRED = {"detail": "This login link has expired.", "code": "expired"}
ALREADY_USED = {"detail": "This login link has already been used.", "code": "already_used"}
TOKEN_REQUIRED = {"detail": "Token is required.", "code": "token_required"}


def with_redirect(body, redirect_to):
    """A spent-link rejection body: ``detail`` and ``code`` plus the link's own landing path."""
    return {**body, "redirect_to": redirect_to}


class LoginLinkTestCase(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.member = make_member(email="owner@example.com")

    def issue_link(self, **kwargs):
        kwargs.setdefault("member", self.member)
        return LoginLinkToken.objects.create(token=LoginLinkToken.generate_token(), **kwargs)

    def post(self, payload, path=URL, **extra):
        return self.client.post(path, payload, format="json", **extra)

    def post_raw(self, body, path=URL):
        return self.client.post(path, body, content_type="application/json")


class LoginLinkAuthorizationHeaderTests(LoginLinkTestCase):
    """The emailed token is the credential; whatever Bearer the browser holds must never decide the outcome."""

    def test_stale_bearer_does_not_block_or_spare_the_token(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(bearer=label):
                link = self.issue_link()

                response = self.post({"token": link.token}, HTTP_AUTHORIZATION=header)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(access_token_owner_id(response.data["access"]), str(self.member.pk))
                link.refresh_from_db()
                self.assertTrue(link.is_used)
                self.assertIsNotNone(link.used_at)

    def test_legacy_magic_login_alias_ignores_stale_bearer_too(self):
        link = self.issue_link()

        response = self.post({"token": link.token}, path=LEGACY_URL, HTTP_AUTHORIZATION="Bearer not-a-jwt")

        self.assertEqual(response.status_code, 200)
        link.refresh_from_db()
        self.assertTrue(link.is_used)

    def test_bearer_of_another_member_logs_in_as_the_token_owner(self):
        other = make_member(email="other@example.com")
        link = self.issue_link()

        response = self.client.post(URL, {"token": link.token}, format="json", HTTP_AUTHORIZATION=bearer_header(other))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(access_token_owner_id(response.data["access"]), str(self.member.pk))


class LoginLinkErrorCodeTests(LoginLinkTestCase):
    """Every rejection carries a stable ``code`` next to the unchanged ``detail`` and status."""

    def assertRejected(self, response, expected):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, expected)

    def test_missing_or_blank_token_is_token_required(self):
        for label, payload in {"missing": {}, "empty": {"token": ""}, "blank": {"token": "   "}}.items():
            with self.subTest(token=label):
                self.assertRejected(self.post(payload), TOKEN_REQUIRED)

    def test_non_string_token_and_non_object_bodies_are_token_required_not_server_errors(self):
        for label, body in MALFORMED_TOKEN_BODIES.items():
            with self.subTest(body=label):
                self.assertRejected(self.post_raw(body), TOKEN_REQUIRED)

    def test_unusable_token_strings_are_token_required_on_both_urls_not_server_errors(self):
        """A lone surrogate can't be UTF-8 encoded and NUL is refused by PostgreSQL: neither may reach the ORM."""
        for path in (URL, LEGACY_URL):
            for label, body in UNUSABLE_TOKEN_BODIES.items():
                with self.subTest(path=path, body=label):
                    self.assertRejected(self.post_raw(body, path=path), TOKEN_REQUIRED)

    def test_unknown_token_is_invalid_link(self):
        self.assertRejected(self.post({"token": "does-not-exist"}), INVALID_LINK)

    def test_inactive_member_is_indistinguishable_from_unknown_token(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active", "updated_at"])
        # A link with its own landing path: none of it may show through for an inactive account.
        campaign = EmailCampaign.objects.create(subject="Promo", body="b", login_redirect_path="/schedule")
        link = self.issue_link(campaign=campaign)

        inactive = self.post({"token": link.token})
        unknown = self.post({"token": "does-not-exist"})

        self.assertRejected(inactive, INVALID_LINK)
        self.assertEqual(inactive.content, unknown.content)
        link.refresh_from_db()
        self.assertFalse(link.is_used)

    def test_expired_token_is_expired(self):
        link = self.issue_link(expires_at=timezone.now() - timedelta(seconds=1))

        self.assertRejected(self.post({"token": link.token}), with_redirect(EXPIRED, "/account"))

    def test_reusable_token_that_expires_mid_exchange_is_expired(self):
        campaign = EmailCampaign.objects.create(
            subject="Reusable", body="b", login_redirect_path="/schedule", login_link_reusable=True
        )
        link = self.issue_link(campaign=campaign)

        # The expiry check passed, then a concurrent revoke made the conditional UPDATE match nothing.
        with patch.object(LoginLinkToken, "record_reusable_use", return_value=False):
            response = self.post({"token": link.token})

        self.assertRejected(response, with_redirect(EXPIRED, "/schedule"))

    def test_used_token_is_already_used(self):
        link = self.issue_link()
        self.assertEqual(self.post({"token": link.token}).status_code, 200)

        self.assertRejected(self.post({"token": link.token}), with_redirect(ALREADY_USED, "/account"))

    def test_success_payload_is_unchanged(self):
        link = self.issue_link()

        response = self.post({"token": link.token})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data),
            {"message", "access", "refresh", "user", "next_step", "requires_profile_completion", "redirect_to"},
        )
        self.assertEqual(response.data["message"], "Login successful.")
