"""Tests for campaign audience exclusion (primary minus exclude group)."""

from django.test import TestCase

from event.tests.helpers import make_event, make_member, make_registration, make_ticket
from mail.models import EmailCampaign
from mail.services.audience import get_recipients


class AudienceExclusionTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Spring Gala")
        self.ticket = make_ticket(self.event)
        self.subscriber = make_member(email="subscribed@example.com", first_name="Sub", last_name="One")
        self.subscriber.contact_emails.filter(email_type="primary").update(subscribe=True)
        self.registrant = make_member(email="registered@example.com", first_name="Reg", last_name="Two")
        self.registrant.contact_emails.filter(email_type="primary").update(subscribe=True)
        make_registration(self.registrant, self.event, self.ticket)

    def test_subscribers_minus_event_registrants(self):
        campaign = EmailCampaign.objects.create(
            subject="Second blast",
            body="Hello",
            audience_type="subscribers",
            exclude_audience_type="event_registrants",
            exclude_event=self.event,
        )
        emails = {r["email"] for r in get_recipients(campaign)}
        self.assertIn("subscribed@example.com", emails)
        self.assertNotIn("registered@example.com", emails)

    def test_no_exclusion_returns_all_subscribers(self):
        campaign = EmailCampaign.objects.create(
            subject="Blast",
            body="Hello",
            audience_type="subscribers",
        )
        emails = {r["email"] for r in get_recipients(campaign)}
        self.assertIn("subscribed@example.com", emails)
        self.assertIn("registered@example.com", emails)

    def test_excludes_selected_members_case_insensitively(self):
        mixed = make_member(email="CamelCase@Example.com")
        mixed.contact_emails.filter(email_type="primary").update(subscribe=True)
        campaign = EmailCampaign.objects.create(
            subject="Blast",
            body="Hello",
            audience_type="subscribers",
            exclude_audience_type="selected_members",
        )
        campaign.exclude_members.add(mixed)
        emails = {r["email"] for r in get_recipients(campaign)}
        self.assertNotIn("CamelCase@Example.com", emails)
