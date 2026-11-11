"""The SMS policy's models: the one SMS Settings row and its checks, a campaign's link checks, and the tables kept out
of reach of the assistant and the /admin-api/ CLI (the shared safe_orm layer)."""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.core.services.db_tools.safe_orm import is_model_denied
from apps.event.tests.helpers import make_event
from apps.mail.models import SmsCampaign, SmsConfig, SmsLinkToken, SmsOptOut, SmsOptOutSyncState, TicketSms
from apps.mail.models.sms_config import SETTINGS_PK


class SmsConfigTests(TestCase):
    def test_there_is_one_row_with_conservative_defaults(self):
        config = SmsConfig.load()
        self.assertEqual(config.pk, SETTINGS_PK)
        self.assertEqual(SmsConfig.load().pk, config.pk)
        stray = SmsConfig(footer_text="Reply STOP now")
        stray.save()
        self.assertEqual(SmsConfig.objects.count(), 1)
        self.assertEqual(SmsConfig.load().footer_text, "Reply STOP now")
        self.assertTrue(config.footer_enabled and config.quiet_hours_enabled and config.opt_out_sync_enabled)
        self.assertFalse(config.links_enabled or config.personal_links_enabled or config.ticket_sms_enabled)
        self.assertEqual(str(config), "SMS settings")

    def test_the_sync_state_is_one_row_too(self):
        state = SmsOptOutSyncState.load()
        self.assertEqual(SmsOptOutSyncState.load().pk, state.pk)
        self.assertEqual(str(state), "SMS opt-out sync (Not run yet)")

    def test_an_invalid_time_zone_is_refused(self):
        config = SmsConfig.load()
        config.quiet_hours_timezone = ""
        with self.assertRaises(ValidationError) as caught:
            config.full_clean()
        self.assertIn("quiet_hours_timezone", caught.exception.message_dict)


class SmsCampaignLinkCheckTests(TestCase):
    def setUp(self):
        config = SmsConfig.load()
        config.links_enabled = True
        config.save()

    def campaign(self, **fields):
        values = {"message": "Hi", "audience_type": "all_members", **fields}
        return SmsCampaign(**values)

    def test_an_event_link_needs_an_event(self):
        with self.assertRaises(ValidationError) as caught:
            self.campaign(message="{{event_link}}").full_clean()
        self.assertIn("event", caught.exception.message_dict)
        self.campaign(message="{{event_link}}", event=make_event()).full_clean()

    def test_the_sign_in_destination_must_be_on_this_site(self):
        for path in ("//evil.example", "/\\evil.example", "/%5Cevil.example"):
            with self.subTest(path=path), self.assertRaises(ValidationError) as caught:
                self.campaign(message="{{login_link}}", login_redirect_path=path).full_clean()
            self.assertIn("login_redirect_path", caught.exception.message_dict)

    def test_validity_is_bounded(self):
        for days in (0, 15):
            with self.subTest(days=days), self.assertRaises(ValidationError):
                self.campaign(link_validity_days=days).full_clean()


class SmsPolicyStringTests(SimpleTestCase):
    def test_rows_describe_themselves_without_secrets(self):
        self.assertEqual(str(SmsOptOut(phone_number="+12095550101")), "+12095550101 (opted out)")
        self.assertEqual(
            str(SmsLinkToken(purpose="event", token_hash="x" * 64)), "Event page ({{event_link}}) (shared)"
        )
        self.assertEqual(str(TicketSms(phone_number="+12095550101")), "Ticket SMS to +12095550101 (Waiting to send)")


class SafeOrmDenylistTests(SimpleTestCase):
    def test_the_sms_policy_tables_are_denied(self):
        for model in (SmsConfig, SmsOptOut, SmsOptOutSyncState, SmsLinkToken, TicketSms):
            with self.subTest(model=model.__name__):
                self.assertTrue(is_model_denied(model, write=False))
                self.assertTrue(is_model_denied(model, write=True))
