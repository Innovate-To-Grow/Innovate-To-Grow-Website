"""Duplicating a campaign copies its message and audience into a draft, and nothing of its send."""

from django.test import TestCase
from django.utils import timezone

from apps.authn.models import Member
from apps.event.tests.helpers import make_event, make_superuser, make_ticket
from apps.mail.models import EmailCampaign, LoginLinkToken, RecipientLog
from apps.mail.services.campaign.duplicate import NAME_MAX_LENGTH, copy_name, duplicate_campaign


def sent_campaign(**overrides):
    event = make_event(name="Spring 2026")
    ticket = make_ticket(event, name="GA", order=1)
    values = {
        "name": "Spring invitation",
        "subject": "You're invited {{first_name}}",
        "body": "<!-- raw-html -->\n<p>Hello</p>",
        "login_redirect_path": "/events",
        "login_link_validity_days": 30,
        "login_link_reusable": True,
        "include_unsubscribe_header": False,
        "audience_type": "selected_members",
        "event": event,
        "member_email_scope": "all",
        "manual_emails": "",
        "exclude_audience_type": "ticket_type",
        "exclude_member_email_scope": "all",
        "exclude_event": event,
        "exclude_ticket_id": str(ticket.pk),
        "status": "sent",
        "total_recipients": 12,
        "sent_count": 11,
        "failed_count": 1,
        "sent_at": timezone.now(),
        "sent_by": make_superuser(email="sender@example.com"),
        "error_message": "one bounce",
    }
    values.update(overrides)
    campaign = EmailCampaign.objects.create(**values)
    members = [Member.objects.create_user(email=f"member{i}@example.com", password="x") for i in range(3)]
    campaign.selected_members.set(members[:2])
    campaign.exclude_members.set(members[2:])
    RecipientLog.objects.create(campaign=campaign, email_address="member0@example.com", status="sent")
    LoginLinkToken.objects.create(token="t" * 20, member=members[0], campaign=campaign)
    return campaign


class DuplicateCampaignTests(TestCase):
    def test_copies_message_settings_and_audience_but_not_the_send(self):
        original = sent_campaign()

        copy = duplicate_campaign(original)

        self.assertNotEqual(copy.pk, original.pk)
        self.assertEqual(copy.name, "Copy of Spring invitation")
        for field in (
            "subject",
            "body",
            "login_redirect_path",
            "login_link_validity_days",
            "login_link_reusable",
            "include_unsubscribe_header",
            "audience_type",
            "event_id",
            "member_email_scope",
            "manual_emails",
            "exclude_audience_type",
            "exclude_member_email_scope",
            "exclude_event_id",
            "exclude_ticket_id",
        ):
            with self.subTest(field=field):
                self.assertEqual(getattr(copy, field), getattr(original, field))
        self.assertEqual(set(copy.selected_members.all()), set(original.selected_members.all()))
        self.assertEqual(set(copy.exclude_members.all()), set(original.exclude_members.all()))

        self.assertEqual(copy.status, "draft")
        self.assertEqual((copy.total_recipients, copy.sent_count, copy.failed_count), (0, 0, 0))
        self.assertIsNone(copy.sent_at)
        self.assertIsNone(copy.sent_by)
        self.assertEqual(copy.error_message, "")
        self.assertFalse(copy.recipient_logs.exists())
        self.assertFalse(copy.login_tokens.exists())
        # The original is untouched.
        original.refresh_from_db()
        self.assertEqual((original.status, original.sent_count), ("sent", 11))

    def test_new_manual_audience_starts_empty_and_without_exclusions(self):
        original = sent_campaign()

        copy = duplicate_campaign(original, name="  Spring invitation, more people  ", new_manual_audience=True)

        self.assertEqual(copy.name, "Spring invitation, more people")
        self.assertEqual(copy.subject, original.subject)
        self.assertEqual(copy.body, original.body)
        self.assertEqual(copy.audience_type, "manual")
        self.assertEqual(copy.manual_emails, "")
        self.assertIsNone(copy.event_id)
        self.assertEqual(copy.exclude_audience_type, "")
        self.assertIsNone(copy.exclude_event_id)
        self.assertEqual(copy.exclude_ticket_id, "")
        self.assertFalse(copy.selected_members.exists())
        self.assertFalse(copy.exclude_members.exists())

    def test_names_are_cut_to_the_field_length(self):
        original = sent_campaign(name="n" * NAME_MAX_LENGTH)

        self.assertEqual(len(copy_name(original.name)), NAME_MAX_LENGTH)
        self.assertTrue(copy_name(original.name).startswith("Copy of nnn"))
        self.assertEqual(copy_name(""), "Copy of Untitled")
        self.assertEqual(len(duplicate_campaign(original, name="x" * 300).name), NAME_MAX_LENGTH)
