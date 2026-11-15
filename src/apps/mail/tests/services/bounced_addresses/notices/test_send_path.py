"""A suppressed (or undeliverable) address stops receiving campaigns: every audience type skips it when it is
resolved, and a campaign queued or running before the address was suppressed skips it just before sending.
Transactional mail (sign-in codes, notifications) still goes."""

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import AWSCredentialConfig
from apps.event.models import CheckIn, CheckInRecord
from apps.event.tests.helpers import make_event, make_registration, make_ticket
from apps.mail.models import BouncedAddress, EmailCampaign
from apps.mail.services.audience import get_recipients
from apps.mail.services.audience.suppression import is_suppressed, split_suppressed, suppressed_addresses

from ..helpers import add_email, make_person, make_row

Suppression = BouncedAddress.Suppression


def suppress(address, kind=Suppression.UNDELIVERABLE):
    row = BouncedAddress.objects.filter(address=address).first() or make_row(address)
    BouncedAddress.objects.filter(pk=row.pk).update(suppressed_at=timezone.now(), suppression=kind)
    return row


def campaign(**values) -> EmailCampaign:
    defaults = {"name": "News", "subject": "News", "body": "<p>Hi</p>", "status": "draft"}
    return EmailCampaign.objects.create(**{**defaults, **values})


class SuppressionListTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_addresses_compare_in_their_bare_lower_case_form(self):
        suppress("person@example.org")

        self.assertTrue(is_suppressed("Person@Example.org"))
        self.assertTrue(is_suppressed("Pat Doe <PERSON@example.org>"))
        self.assertFalse(is_suppressed("other@example.org"))
        self.assertFalse(is_suppressed(""))
        self.assertEqual(suppressed_addresses(), frozenset({"person@example.org"}))

    def test_an_address_that_only_bounced_is_not_suppressed(self):
        make_row("bounced@example.org")

        self.assertFalse(is_suppressed("bounced@example.org"))
        self.assertEqual(split_suppressed([{"email": "bounced@example.org"}]), ([{"email": "bounced@example.org"}], []))


class AudienceTests(TestCase):
    """Every bulk audience type skips the suppressed addresses."""

    def setUp(self):
        cache.clear()
        self.kept = make_person("kept@example.org", first="Kept")
        self.blocked = make_person("Blocked@Example.org", first="Blocked")
        add_email(self.kept, "kept-old@example.org", email_type="secondary")
        self.staff = make_person("staffer@example.org", first="Staff", is_staff=True)
        suppress("blocked@example.org")
        suppress("kept-old@example.org", Suppression.SUPPRESSED)
        suppress("staffer@example.org")

    def emails(self, recipients):
        return sorted(recipient["email"].lower() for recipient in recipients)

    def test_member_audiences(self):
        selected = campaign(audience_type="selected_members", member_email_scope="all")
        selected.selected_members.set([self.kept, self.blocked])
        cases = {
            "subscribers primary": (campaign(audience_type="subscribers"), ["kept@example.org"]),
            "subscribers all": (campaign(audience_type="subscribers", member_email_scope="all"), ["kept@example.org"]),
            "all members": (campaign(audience_type="all_members"), ["kept@example.org"]),
            "staff": (campaign(audience_type="staff"), []),
            "selected, all emails": (selected, ["kept@example.org"]),
        }
        for name, (item, expected) in cases.items():
            with self.subTest(audience=name):
                recipients = get_recipients(item)
                self.assertEqual(self.emails(recipients), expected)
                self.assertTrue(recipients.skipped)

    def test_event_audiences_compare_the_attendee_email_snapshot(self):
        event = make_event()
        ticket = make_ticket(event)
        kept = make_registration(self.kept, event, ticket)
        blocked = make_registration(self.blocked, event, ticket, attendee_email="BLOCKED@example.org")
        check_in = CheckIn.objects.create(event=event, name="Door")
        CheckInRecord.objects.create(check_in=check_in, registration=blocked)
        cases = {
            "event_registrants": campaign(audience_type="event_registrants", event=event),
            "ticket_type": campaign(audience_type="ticket_type", event=event, manual_emails=str(ticket.pk)),
            "checked_in": campaign(audience_type="checked_in", event=event),
            "not_checked_in": campaign(audience_type="not_checked_in", event=event),
        }
        for name, item in cases.items():
            with self.subTest(audience=name):
                self.assertNotIn("blocked@example.org", self.emails(get_recipients(item)))
        self.assertEqual(self.emails(get_recipients(cases["not_checked_in"])), [kept.attendee_email])

    def test_manual_lists_skip_suppressed_addresses_that_belong_to_no_member(self):
        suppress("stranger@example.org", Suppression.SUPPRESSED)
        item = campaign(
            audience_type="manual", manual_emails="Stranger@Example.org\nfriend@example.org\nkept@example.org"
        )

        recipients = get_recipients(item)

        self.assertEqual(self.emails(recipients), ["friend@example.org", "kept@example.org"])
        self.assertEqual([row["email"] for row in recipients.skipped], ["Stranger@Example.org"])

    def test_clearing_the_suppression_brings_the_address_back(self):
        BouncedAddress.objects.filter(address="blocked@example.org").update(suppressed_at=None, suppression="")

        self.assertIn("blocked@example.org", self.emails(get_recipients(campaign(audience_type="all_members"))))


def _make_active_aws():
    AWSCredentialConfig.objects.all().delete()
    return AWSCredentialConfig.objects.create(
        name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
    )
