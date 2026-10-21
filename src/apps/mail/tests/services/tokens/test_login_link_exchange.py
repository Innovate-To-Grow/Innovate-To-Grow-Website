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
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
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


class LoginLinkSpentRedirectTests(LoginLinkTestCase):
    """A genuine link that can no longer be used names its own landing path; no other rejection does."""

    LINK_KINDS = ["campaign", "ticket", "default", "unsafe token path", "unsafe campaign path"]

    def make_link(self, kind, **kwargs):
        """Return ``(link, landing path)`` for the shapes of link the mail app issues."""
        if kind == "campaign":
            campaign = EmailCampaign.objects.create(subject="Promo", body="b", login_redirect_path="/schedule")
            return self.issue_link(campaign=campaign, **kwargs), "/schedule"
        if kind == "ticket":
            event = make_event(ticket_login_reusable=False)  # one-time, so "already used" is reachable
            registration = make_registration(self.member, event, make_ticket(event))
            path = f"/event-registration?event={event.slug}"
            return self.issue_link(registration=registration, redirect_path=path, **kwargs), path
        if kind == "unsafe token path":  # stored values are re-validated: an external URL never comes back out
            return self.issue_link(redirect_path="//evil.example", **kwargs), "/account"
        if kind == "unsafe campaign path":
            campaign = EmailCampaign.objects.create(subject="Odd", body="b", login_redirect_path="https://evil.example")
            return self.issue_link(campaign=campaign, **kwargs), "/account"
        return self.issue_link(**kwargs), "/account"

    def test_expired_link_includes_its_landing_path(self):
        for kind in self.LINK_KINDS:
            with self.subTest(link=kind):
                link, path = self.make_link(kind, expires_at=timezone.now() - timedelta(seconds=1))

                response = self.post({"token": link.token})

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, with_redirect(EXPIRED, path))

    def test_already_used_link_includes_the_path_its_first_use_returned(self):
        for kind in self.LINK_KINDS:
            with self.subTest(link=kind):
                link, path = self.make_link(kind)
                first = self.post({"token": link.token})
                self.assertEqual(first.status_code, 200)
                self.assertEqual(first.data["redirect_to"], path)

                second = self.post({"token": link.token})

                self.assertEqual(second.status_code, 400)
                self.assertEqual(second.data, with_redirect(ALREADY_USED, path))

    def test_reusable_link_keeps_working_until_it_is_switched_off(self):
        campaign = EmailCampaign.objects.create(
            subject="Reusable", body="b", login_redirect_path="/schedule", login_link_reusable=True
        )
        link = self.issue_link(campaign=campaign)

        for attempt in (1, 2, 3):
            with self.subTest(attempt=attempt):
                response = self.post({"token": link.token})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["redirect_to"], "/schedule")
                self.assertNotIn("code", response.data)

        # The kill switch: the already-used link is now refused like any one-time link.
        campaign.login_link_reusable = False
        campaign.save(update_fields=["login_link_reusable", "updated_at"])

        self.assertEqual(self.post({"token": link.token}).data, with_redirect(ALREADY_USED, "/schedule"))

    def test_expired_reusable_link_includes_its_landing_path(self):
        campaign = EmailCampaign.objects.create(
            subject="Reusable", body="b", login_redirect_path="/schedule", login_link_reusable=True
        )
        link = self.issue_link(campaign=campaign, expires_at=timezone.now() - timedelta(seconds=1))

        response = self.post({"token": link.token})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, with_redirect(EXPIRED, "/schedule"))

    def test_rejections_that_must_not_reveal_a_link_carry_no_landing_path(self):
        inactive = make_member(email="inactive@example.com")
        inactive.is_active = False
        inactive.save(update_fields=["is_active", "updated_at"])
        campaign = EmailCampaign.objects.create(subject="Promo", body="b", login_redirect_path="/schedule")
        past = timezone.now() - timedelta(seconds=1)
        unknown = self.post({"token": "does-not-exist"})

        # An inactive account looks like an unknown token whatever state its link is in.
        for state, kwargs in {
            "unused": {},
            "expired": {"expires_at": past},
            "used": {"is_used": True, "used_at": timezone.now()},
        }.items():
            with self.subTest(inactive=state):
                link = self.issue_link(member=inactive, campaign=campaign, **kwargs)

                response = self.post({"token": link.token})

                self.assertEqual(response.content, unknown.content)
                self.assertNotIn("redirect_to", response.data)

        responses = {
            "unknown token": unknown,
            "missing token": self.post({}),
            "blank token": self.post({"token": "  "}),
            "malformed body": self.post_raw("null"),
            "unusable token": self.post_raw(UNUSABLE_TOKEN_BODIES["NUL"]),
        }
        for label, response in responses.items():
            with self.subTest(rejection=label):
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("redirect_to", response.data)


class LoginLinkRejectionLoggingTests(LoginLinkTestCase):
    """Rejections are logged with the reason, member id and header presence; never the token."""

    def post_and_capture(self, payload, **extra):
        with self.assertLogs(VIEW_LOGGER, level="INFO") as captured:
            response = self.client.post(URL, payload, format="json", **extra)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(captured.records), 1)
        return captured.records[0].getMessage()

    def test_each_rejection_logs_reason_and_member_id_without_the_token(self):
        expired = self.issue_link(expires_at=timezone.now() - timedelta(seconds=1))
        used = self.issue_link(is_used=True, used_at=timezone.now())
        other = make_member(email="inactive@example.com")
        other.is_active = False
        other.save(update_fields=["is_active", "updated_at"])
        inactive = self.issue_link(member=other)
        unknown_token = "unknown-token-that-must-not-be-logged"

        cases = [
            ("token_required", {}, None, None),
            ("unknown_token", {"token": unknown_token}, unknown_token, None),
            ("inactive_member", {"token": inactive.token}, inactive.token, other.pk),
            ("expired", {"token": expired.token}, expired.token, self.member.pk),
            ("already_used", {"token": used.token}, used.token, self.member.pk),
        ]
        for reason, payload, token, member_id in cases:
            with self.subTest(reason=reason):
                message = self.post_and_capture(payload)

                self.assertIn(f"reason={reason}", message)
                self.assertIn(f"member_id={member_id}", message)
                if token:
                    self.assertNotIn(token, message)

    def test_log_records_whether_an_authorization_header_was_present(self):
        without = self.post_and_capture({"token": "nope"})
        with_stale = self.post_and_capture({"token": "nope"}, HTTP_AUTHORIZATION="Bearer not-a-jwt")

        self.assertIn("authorization_header=False", without)
        self.assertIn("authorization_header=True", with_stale)
        self.assertNotIn("not-a-jwt", with_stale)

    def test_successful_exchange_logs_no_rejection(self):
        link = self.issue_link()

        with self.assertNoLogs(VIEW_LOGGER, level="INFO"):
            response = self.client.post(URL, {"token": link.token}, format="json")

        self.assertEqual(response.status_code, 200)
