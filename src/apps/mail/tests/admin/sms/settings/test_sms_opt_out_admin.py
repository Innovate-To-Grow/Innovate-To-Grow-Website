from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactPhone
from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket
from apps.mail.models import SmsLinkToken, SmsOptOut, TicketSms
from apps.mail.services.sms import links
from apps.mail.services.sms.policy.opt_out_sync import SyncResult
from apps.mail.tests.admin.sms.settings.test_sms_settings_admin import SYNC

from ....services.sms.policy.policy_helpers import add_phone, opt_out, sms_settings


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SmsOptOutAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.member = make_member(email="ada@example.com", first_name="Ada", last_name="Lovelace")
        self.phone = add_phone(self.member, "2095550101")

    def test_the_list_shows_each_number_its_members_and_the_sync(self):
        opt_out("+12095550101")
        response = self.client.get(reverse("admin:mail_smsoptout_changelist"))
        self.assertContains(response, "+12095550101")
        self.assertContains(response, "Ada Lovelace")
        self.assertContains(response, 'id="sms-opt-out-sync-now"')

    def test_staff_opt_a_number_out_and_its_phone_is_unsubscribed(self):
        response = self.client.post(
            reverse("admin:mail_smsoptout_add"), {"phone_number": "(209) 555-0101", "note": "Asked at the desk"}
        )
        self.assertEqual(response.status_code, 302)
        row = SmsOptOut.objects.get()
        self.assertEqual((row.phone_number, row.source, row.created_by), ("+12095550101", "staff", self.admin_user))
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.subscribe)
        self.assertTrue(LogEntry.objects.filter(object_id=str(row.pk), action_flag=ADDITION).exists())

        again = self.client.post(reverse("admin:mail_smsoptout_add"), {"phone_number": "+12095550101", "note": ""})
        self.assertContains(again, "already opted out")
        bad = self.client.post(reverse("admin:mail_smsoptout_add"), {"phone_number": "12345", "note": ""})
        self.assertContains(bad, "Enter a US phone number")

    def test_a_number_that_opted_back_in_can_be_opted_out_again(self):
        row = opt_out("+12095550101", source="staff")
        SmsOptOut.objects.filter(pk=row.pk).update(cleared_at=row.opted_out_at)
        response = self.client.post(reverse("admin:mail_smsoptout_add"), {"phone_number": "+12095550101", "note": "x"})
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertTrue(row.is_active)
        self.assertEqual(SmsOptOut.objects.count(), 1)

    def test_the_list_filters_by_status(self):
        opt_out("+12095550101")
        opt_out("+12095550102", cleared_at=timezone.now())
        url = reverse("admin:mail_smsoptout_changelist")
        active = self.client.get(url, {"status": "active"})
        self.assertContains(active, "+12095550101")
        self.assertNotContains(active, "+12095550102")
        cleared = self.client.get(url, {"status": "cleared"})
        self.assertContains(cleared, "+12095550102")
        self.assertNotContains(cleared, "+12095550101")

    def test_a_row_is_read_only_and_never_deleted(self):
        row = opt_out("+12095550101")
        response = self.client.get(reverse("admin:mail_smsoptout_change", args=[row.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_save"')
        self.assertEqual(self.client.get(reverse("admin:mail_smsoptout_delete", args=[row.pk])).status_code, 403)

    def test_lifting_ends_only_staff_opt_outs(self):
        staff_row = opt_out("+12095550101", source="staff")
        aws_row = opt_out("+12095550102")
        ContactPhone.objects.filter(pk=self.phone.pk).update(subscribe=False)  # as the staff opt-out left it
        response = self.client.post(
            reverse("admin:mail_smsoptout_changelist"),
            {"action": "lift_staff_opt_outs", "_selected_action": [str(staff_row.pk), str(aws_row.pk)]},
            follow=True,
        )
        self.assertContains(response, "Lifted 1 staff opt-out(s).")
        self.assertContains(response, "replies START")
        staff_row.refresh_from_db()
        aws_row.refresh_from_db()
        self.assertFalse(staff_row.is_active)
        self.assertTrue(aws_row.is_active)
        self.assertTrue(LogEntry.objects.filter(object_id=str(staff_row.pk), action_flag=CHANGE).exists())
        # Lifting never subscribes the phone again.
        self.assertFalse(ContactPhone.objects.get(pk=self.phone.pk).subscribe)

    @patch(SYNC, return_value=SyncResult("ok", listed=3, added=1, cleared=0))
    def test_sync_now_reads_aws_and_returns_to_a_page_of_this_site(self, sync):
        sync_url = reverse("admin:mail_smsoptout_sync")
        self.assertEqual(self.client.get(sync_url).status_code, 405)

        response = self.client.post(sync_url, {"next": "/admin/mail/smsconfig/"})
        self.assertEqual(response.url, "/admin/mail/smsconfig/")
        sync.assert_called_once_with()
        for unsafe in ("https://evil.example/admin/mail/", "//evil.example", "/admin/core/"):
            with self.subTest(unsafe=unsafe):
                self.assertEqual(
                    self.client.post(sync_url, {"next": unsafe}).url, reverse("admin:mail_smsoptout_changelist")
                )
        followed = self.client.post(sync_url, follow=True)
        self.assertContains(followed, "AWS opt-out sync: ok. Listed 3, added 1, cleared 0.")
        self.assertTrue(LogEntry.objects.filter(change_message__contains="Synced SMS opt-outs").exists())

    @patch(SYNC, return_value=SyncResult("failed", message="AWS refused to read the opted-out list. (AccessDenied)"))
    def test_a_failed_sync_is_reported_as_an_error(self, _sync):
        response = self.client.post(reverse("admin:mail_smsoptout_sync"), follow=True)
        self.assertContains(response, "AccessDenied")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, FRONTEND_URL="https://i2g.example.edu")
class SmsRecordsAdminTests(TestCase):
    def setUp(self):
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_sms_links_are_listed_without_their_tokens_and_can_be_revoked(self):
        sms_settings(links_enabled=True, personal_links_enabled=True)
        member = make_member(email="ada@example.com")
        add_phone(member, "2095550101")
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=member, phone="+12095550101", redirect_path="/", validity_days=1
        )
        token = url.rsplit("/", 1)[1]
        response = self.client.get(reverse("admin:mail_smslinktoken_changelist"))
        self.assertContains(response, "Personal sign-in")
        self.assertNotContains(response, token)
        row = SmsLinkToken.objects.get()
        self.client.post(
            reverse("admin:mail_smslinktoken_changelist"),
            {"action": "revoke_selected_action", "_selected_action": [str(row.pk)]},
        )
        # Revoked, it opens the sign-in page (returning to its page) and signs nobody in.
        opened = links.open_link(token)
        self.assertEqual((opened.kind, opened.member, opened.redirect_to), ("redirect", None, "/login?returnTo=/"))
        self.assertContains(self.client.get(reverse("admin:mail_smslinktoken_changelist")), "revoked")

    def test_a_links_status_follows_its_use_and_expiry(self):
        sms_settings(links_enabled=True, personal_links_enabled=True)
        member = make_member(email="ada@example.com")
        add_phone(member, "2095550101")
        used = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=member, phone="+12095550101", redirect_path="/", validity_days=1
        )
        links.open_link(used.rsplit("/", 1)[1])
        expired = SmsLinkToken.objects.create(
            token_hash="e" * 64, purpose="event", redirect_path="/", expires_at=timezone.now() - timedelta(days=1)
        )
        response = self.client.get(reverse("admin:mail_smslinktoken_changelist"))
        self.assertContains(response, "used")
        self.assertContains(response, "expired")
        self.assertContains(response, "Shared")
        self.assertTrue(expired.is_expired)

    def test_ticket_texts_are_listed_with_their_status(self):
        event = make_event()
        member = make_member(email="pho@example.com")
        registration = make_registration(member, event, make_ticket(event))
        TicketSms.objects.create(registration=registration, phone_number="+12095550101", status="opted_out")
        response = self.client.get(reverse("admin:mail_ticketsms_changelist"))
        self.assertContains(response, "+12095550101")
        self.assertContains(response, "Opted out")
