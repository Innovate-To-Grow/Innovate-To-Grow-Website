from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.event.tests.helpers import make_event, make_ticket
from apps.mail.models import EmailCampaign, SmsCampaign
from apps.mail.models.email.campaign import EmailCampaign as CampaignModel
from apps.mail.models.email.recipient_log import RecipientLog as RecipientLogModel
from apps.mail.models.sms.campaign import SmsCampaign as SmsModel


class ModelStrAndCleanTests(TestCase):
    def test_recipient_log_str(self):
        campaign = EmailCampaign.objects.create(subject="s", body="b")
        log = RecipientLogModel(campaign=campaign, email_address="x@example.com", status="delivered")
        self.assertIn("x@example.com", str(log))
        self.assertIn("Delivered", str(log))

    def test_email_campaign_clean_rejects_unsafe_redirect(self):
        campaign = CampaignModel(subject="s", body="b", login_redirect_path="//evil.com")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("login_redirect_path", ctx.exception.message_dict)

    def test_email_campaign_clean_requires_event_for_event_audience(self):
        campaign = CampaignModel(
            subject="s", body="b", login_redirect_path="/account", audience_type="event_registrants"
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("event", ctx.exception.message_dict)

    def test_email_campaign_clean_requires_ticket_for_ticket_audience(self):
        event = make_event()
        campaign = CampaignModel(
            subject="s",
            body="b",
            login_redirect_path="/account",
            audience_type="ticket_type",
            event=event,
            manual_emails="",
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("manual_emails", ctx.exception.message_dict)

    def test_email_campaign_clean_requires_manual_emails(self):
        campaign = CampaignModel(
            subject="s", body="b", login_redirect_path="/account", audience_type="manual", manual_emails=""
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("manual_emails", ctx.exception.message_dict)

    def test_email_campaign_clean_requires_exclude_event(self):
        campaign = CampaignModel(
            subject="s",
            body="b",
            login_redirect_path="/account",
            audience_type="subscribers",
            exclude_audience_type="event_registrants",
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("exclude_event", ctx.exception.message_dict)

    def test_sms_campaign_clean_requires_event(self):
        campaign = SmsModel(message="m", audience_type="event_registrants")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("event", ctx.exception.message_dict)

    def test_sms_campaign_clean_requires_ticket(self):
        event = make_event()
        campaign = SmsModel(message="m", audience_type="ticket_type", event=event, ticket_id="")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("ticket_id", ctx.exception.message_dict)

    def test_sms_campaign_clean_manual_requires_phones(self):
        campaign = SmsModel(message="m", audience_type="manual", manual_phones="")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("manual_phones", ctx.exception.message_dict)

    def test_sms_campaign_clean_manual_rejects_invalid_phone(self):
        campaign = SmsModel(message="m", audience_type="manual", manual_phones="12345")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("manual_phones", ctx.exception.message_dict)

    def test_sms_campaign_clean_manual_accepts_valid_phone(self):
        campaign = SmsModel(message="m", audience_type="manual", manual_phones="+12095551234")
        campaign.clean()  # should not raise

    def test_sms_campaign_clean_requires_exclude_event(self):
        campaign = SmsModel(message="m", audience_type="subscribers", exclude_audience_type="event_registrants")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("exclude_event", ctx.exception.message_dict)

    def test_sms_campaign_clean_requires_exclude_ticket(self):
        event = make_event()
        campaign = SmsModel(
            message="m",
            audience_type="subscribers",
            exclude_audience_type="ticket_type",
            exclude_event=event,
            exclude_ticket_id="",
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("exclude_ticket_id", ctx.exception.message_dict)

    def test_sms_campaign_str_uses_message_fallback(self):
        campaign = SmsModel(name="", message="Hi there friends", status="draft")
        self.assertIn("Hi there friends", str(campaign))

    def test_sms_recipient_log_str(self):
        from apps.mail.models import SmsRecipientLog

        campaign = SmsCampaign.objects.create(name="A", message="m")
        log = SmsRecipientLog(campaign=campaign, phone_number="+12095551234", status="sent")
        self.assertEqual(str(log), "+12095551234 - Sent")


class TicketSelectWidgetTests(TestCase):
    def test_create_option_adds_data_event_attribute(self):
        from apps.event.models import Ticket
        from apps.mail.admin.campaign.forms.widgets import ManualEmailsWidget, TicketSelectWidget

        event = make_event()
        ticket = make_ticket(event, name="VIP")
        widget = TicketSelectWidget()
        widget.choices = SimpleNamespace(queryset=Ticket.objects.filter(pk=ticket.pk))

        option = widget.create_option("ticket", str(ticket.pk), "VIP", False, 0)

        self.assertEqual(option["attrs"]["data-event"], str(event.pk))

        # An empty value yields no data-event attribute.
        empty_option = widget.create_option("ticket", "", "----", False, 1)
        self.assertNotIn("data-event", empty_option["attrs"])

        # ManualEmailsWidget merges custom attrs over defaults.
        manual = ManualEmailsWidget(attrs={"rows": 12})
        self.assertEqual(manual.attrs["rows"], 12)

    def test_get_event_map_handles_non_queryset_choices(self):
        from apps.mail.admin.campaign.forms.widgets import TicketSelectWidget

        widget = TicketSelectWidget()
        widget.choices = [("", "----")]  # plain list, no .queryset

        self.assertEqual(widget._get_event_map(), {})
