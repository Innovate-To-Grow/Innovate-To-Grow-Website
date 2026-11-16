from datetime import timedelta

from django.utils import timezone

from apps.authn.tests.helpers import (
    UNUSABLE_TOKEN_BODIES,
)
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.mail.models import EmailCampaign
from apps.mail.tests.services.tokens.login_links.test_login_link_exchange import (
    ALREADY_USED,
    EXPIRED,
    URL,
    VIEW_LOGGER,
    LoginLinkTestCase,
    with_redirect,
)


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
