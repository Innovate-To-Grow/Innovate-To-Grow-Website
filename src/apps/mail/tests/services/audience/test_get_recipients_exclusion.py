from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign
from apps.mail.services.audience import get_recipients


class GetRecipientsExclusionTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="keep@example.com", first_name="Keep", last_name="Me")
        self.m2 = make_member(email="exclude@example.com", first_name="Exclude", last_name="Me")
        self.m2.is_staff = True
        self.m2.save()

    def test_exclusion_removes_matching_emails(self):
        campaign = EmailCampaign.objects.create(
            subject="Test",
            body="body",
            audience_type="all_members",
            member_email_scope="primary",
            exclude_audience_type="staff",
            exclude_member_email_scope="primary",
        )
        result = get_recipients(campaign)
        emails = [r["email"] for r in result]
        self.assertIn("keep@example.com", emails)
        self.assertNotIn("exclude@example.com", emails)

    def test_no_exclusion_returns_all(self):
        campaign = EmailCampaign.objects.create(
            subject="Test",
            body="body",
            audience_type="all_members",
            member_email_scope="primary",
            exclude_audience_type="",
        )
        result = get_recipients(campaign)
        emails = [r["email"] for r in result]
        self.assertIn("keep@example.com", emails)
        self.assertIn("exclude@example.com", emails)

    def test_exclusion_is_case_insensitive(self):
        ContactEmail.objects.filter(member=self.m2).update(email_address="EXCLUDE@EXAMPLE.COM")
        campaign = EmailCampaign.objects.create(
            subject="Test",
            body="body",
            audience_type="manual",
            manual_emails="exclude@example.com\nkeep@example.com",
            exclude_audience_type="staff",
            exclude_member_email_scope="primary",
        )
        result = get_recipients(campaign)
        emails = [r["email"] for r in result]
        self.assertNotIn("exclude@example.com", emails)
        self.assertIn("keep@example.com", emails)
