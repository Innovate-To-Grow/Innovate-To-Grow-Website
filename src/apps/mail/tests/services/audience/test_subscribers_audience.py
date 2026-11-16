"""The per-address ``ContactEmail.subscribe`` flag is authoritative for the "subscribers" audience."""

import importlib

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, Member
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign
from apps.mail.services.audience import get_recipients
from apps.mail.services.audience.resolvers import recipients_for_audience

_carry_primary_opt_out = importlib.import_module(
    "apps.mail.migrations.0019_carry_primary_opt_out_to_all_addresses"
).carry_primary_opt_out


def _subscriber_emails(*, send_all):
    recipients = recipients_for_audience(
        "subscribers",
        send_all=send_all,
        event=None,
        ticket_uuid_str="",
        selected_members=None,
        manual_emails_body="",
    )
    return [recipient["email"] for recipient in recipients]


def _add_email(member, address, email_type, *, subscribe, verified=True):
    return ContactEmail.objects.create(
        member=member, email_address=address, email_type=email_type, subscribe=subscribe, verified=verified
    )


class SubscribersPerAddressTests(TestCase):
    def setUp(self):
        cache.clear()
        # Primary subscribed, secondary unsubscribed, other subscribed.
        self.mixed = make_member(email="mixed@example.com", first_name="Mixed")
        _add_email(self.mixed, "mixed-2@example.com", "secondary", subscribe=False)
        _add_email(self.mixed, "mixed-3@example.com", "other", subscribe=True)
        # Primary unsubscribed (from /account), secondary still subscribed.
        self.secondary_only = make_member(email="sec-only@example.com", first_name="Secondary")
        ContactEmail.objects.filter(member=self.secondary_only).update(subscribe=False)
        _add_email(self.secondary_only, "sec-only-2@example.com", "secondary", subscribe=True)
        # Nothing subscribed.
        self.opted_out = make_member(email="out@example.com", first_name="Out")
        _add_email(self.opted_out, "out-2@example.com", "secondary", subscribe=False)
        ContactEmail.objects.filter(member=self.opted_out).update(subscribe=False)

    def test_scope_primary_mails_only_a_subscribed_primary(self):
        self.assertCountEqual(_subscriber_emails(send_all=False), ["mixed@example.com"])

    def test_scope_all_mails_every_subscribed_address_and_nothing_else(self):
        self.assertCountEqual(
            _subscriber_emails(send_all=True),
            ["mixed@example.com", "mixed-3@example.com", "sec-only-2@example.com"],
        )

    def test_inactive_members_are_excluded(self):
        Member.objects.filter(pk=self.mixed.pk).update(is_active=False)

        self.assertEqual(_subscriber_emails(send_all=False), [])
        self.assertCountEqual(_subscriber_emails(send_all=True), ["sec-only-2@example.com"])

    def test_unverified_addresses_are_included(self):
        """Excel import creates addresses with verified=False; they are still real subscribers."""
        imported = Member.objects.create_user(password="x", first_name="Imported")
        _add_email(imported, "imported@example.com", "primary", subscribe=True, verified=False)

        self.assertIn("imported@example.com", _subscriber_emails(send_all=False))

    def test_recipient_shape_is_unchanged(self):
        recipients = recipients_for_audience(
            "subscribers", send_all=False, event=None, ticket_uuid_str="", selected_members=None, manual_emails_body=""
        )

        self.assertEqual(
            recipients,
            [
                {
                    "member_id": self.mixed.pk,
                    "email": "mixed@example.com",
                    "first_name": "Mixed",
                    "last_name": "",
                    "full_name": "Mixed",
                }
            ],
        )

    def test_resolver_runs_a_fixed_number_of_queries(self):
        for index in range(5):
            member = make_member(email=f"bulk-{index}@example.com")
            _add_email(member, f"bulk-{index}-2@example.com", "secondary", subscribe=False)

        for send_all in (False, True):
            with self.subTest(send_all=send_all), self.assertNumQueries(2):  # members + contact_emails prefetch
                _subscriber_emails(send_all=send_all)

    def test_other_audiences_still_ignore_the_flag(self):
        emails = [
            recipient["email"]
            for recipient in recipients_for_audience(
                "all_members",
                send_all=True,
                event=None,
                ticket_uuid_str="",
                selected_members=None,
                manual_emails_body="",
            )
        ]

        self.assertIn("out@example.com", emails)
        self.assertIn("mixed-2@example.com", emails)


class SubscribersExclusionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member(email="excl@example.com")
        ContactEmail.objects.filter(member=self.member).update(subscribe=False)
        _add_email(self.member, "excl-2@example.com", "secondary", subscribe=True)
        self.subscriber = make_member(email="sub@example.com")

    def _campaign(self, **overrides):
        fields = {
            "subject": "Blast",
            "body": "Hello",
            "audience_type": "all_members",
            "member_email_scope": "all",
            "exclude_audience_type": "subscribers",
        }
        fields.update(overrides)
        return EmailCampaign.objects.create(**fields)

    def test_excluding_subscribers_with_scope_all_removes_only_subscribed_addresses(self):
        emails = {r["email"] for r in get_recipients(self._campaign(exclude_member_email_scope="all"))}

        self.assertEqual(emails, {"excl@example.com"})

    def test_excluding_subscribers_with_scope_primary_removes_only_subscribed_primaries(self):
        emails = {r["email"] for r in get_recipients(self._campaign(exclude_member_email_scope="primary"))}

        self.assertEqual(emails, {"excl@example.com", "excl-2@example.com"})

    def test_subscribers_minus_primary_subscribers_leaves_other_subscribed_addresses(self):
        campaign = self._campaign(audience_type="subscribers", exclude_member_email_scope="primary")

        self.assertEqual({r["email"] for r in get_recipients(campaign)}, {"excl-2@example.com"})
