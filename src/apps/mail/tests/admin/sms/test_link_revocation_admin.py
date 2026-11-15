"""Turning personal SMS sign-in links off in Mail → SMS Settings: what staff see before (the warning with the number
of links it would revoke, the revocation on the type-to-confirm page), what the save does and says, and the audit
(SMS link revocations, the last few on the settings page; "revoked" on SMS Links). AWS is never called."""

from datetime import timedelta

from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.event.tests.helpers import make_admin, make_member, make_superuser
from apps.mail.admin.sms_settings.config import REVOKED_FOR_GOOD
from apps.mail.models import SmsConfig, SmsLinkRevocation, SmsLinkToken
from apps.mail.services.sms import links

from ...services.sms.policy_helpers import add_phone, sms_settings
from .test_sms_settings_admin import settings_form

PHONE = "+12095550101"
SESSION_KEY = "_admin_pending_change_mail_smsconfig"
Reason = SmsLinkRevocation.Reason
Via = SmsLinkRevocation.Via


def issue(member):
    url = links.issue_personal_link(
        purpose=links.Purpose.LOGIN, member=member, phone=PHONE, redirect_path="/subscribe", validity_days=3
    )
    return url.rsplit("/l/", 1)[1]


def links_on(**values):
    """The settings form with links in SMS and personal sign-in links on, as the I2G Master posts it."""
    return settings_form(links_enabled="on", personal_links_enabled="on", **values)


class SwitchTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        sms_settings(links_enabled=True, personal_links_enabled=True)
        self.member = make_member(email="ada@example.com", first_name="Ada")
        add_phone(self.member, "2095550101")
        self.token = issue(self.member)
        self.change_url = reverse("admin:mail_smsconfig_change", args=[SmsConfig.load().pk])

    def assert_revoked(self):
        opened = links.open_link(self.token)
        self.assertEqual((opened.kind, opened.member), ("redirect", None))


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, FRONTEND_URL="https://i2g.example.edu")
class SwitchOffInTheAdminTests(SwitchTestCase):
    def test_the_i2g_master_turning_personal_links_off_revokes_them_and_is_told_how_many(self):
        admin = make_superuser()
        self.client.force_login(admin)

        response = self.client.post(self.change_url, settings_form(links_enabled="on"), follow=True)

        self.assertContains(response, "Personal sign-in links are off: 1 link(s) already texted were revoked for good.")
        revocation = SmsLinkRevocation.objects.get()
        self.assertEqual(
            (revocation.reason, revocation.via, revocation.actor, revocation.revoked_count),
            (Reason.PERSONAL_LINKS_OFF, Via.ADMIN, admin, 1),
        )
        self.assert_revoked()
        # Turned on again, the link texted before stays revoked.
        self.client.post(self.change_url, links_on())
        self.assertTrue(SmsConfig.load().personal_sign_in_on)
        self.assert_revoked()
        self.assertEqual(SmsLinkRevocation.objects.count(), 1)

    def test_mail_staff_turning_links_in_sms_off_revokes_them_too(self):
        staff = make_admin(apps=["mail"], email="mail@example.com")
        self.client.force_login(staff)

        self.client.post(self.change_url, settings_form())

        config = SmsConfig.load()
        self.assertFalse(config.links_enabled)
        self.assertTrue(config.personal_links_enabled)  # read only for them, unchanged
        revocation = SmsLinkRevocation.objects.get()
        self.assertEqual((revocation.reason, revocation.actor, revocation.revoked_count), (Reason.LINKS_OFF, staff, 1))
        self.assertIn("mail@example.com", revocation.actor_label)
        self.assert_revoked()

    def test_a_save_that_finds_links_left_live_while_off_says_so(self):
        self.client.force_login(make_superuser())
        with connection.cursor() as cursor:  # Turned off outside the app: nothing revoked then.
            cursor.execute("UPDATE mail_smsconfig SET personal_links_enabled = %s", [False])

        with self.assertLogs("apps.mail.models.sms_config", level="WARNING"):
            response = self.client.post(self.change_url, links_on(), follow=True)

        self.assertContains(response, "Revoked 1 personal sign-in link(s) that still worked although")
        self.assertEqual(SmsLinkRevocation.objects.get().reason, Reason.FOUND_OFF)
        self.assert_revoked()

    def test_a_save_that_keeps_them_on_says_nothing_about_links(self):
        self.client.force_login(make_superuser())
        response = self.client.post(self.change_url, links_on(quiet_hours_start="21:00"), follow=True)
        self.assertNotContains(response, "revoked for good")
        self.assertFalse(SmsLinkRevocation.objects.exists())
        self.assertEqual(links.open_link(self.token).kind, "sign_in")

    def test_the_settings_page_warns_with_the_number_it_would_revoke(self):
        self.client.force_login(make_superuser())
        response = self.client.get(self.change_url)
        self.assertContains(response, "revokes every personal sign-in link already texted, for good")
        self.assertContains(response, "Personal sign-in links that still work now: 1.")
        self.assertContains(response, 'id="sms-link-revocations"')
        self.assertContains(response, "None yet.")

    def test_the_settings_page_lists_the_last_revocations(self):
        admin = make_superuser()
        self.client.force_login(admin)
        self.client.post(self.change_url, settings_form(links_enabled="on"))

        response = self.client.get(self.change_url)

        self.assertContains(response, "Personal sign-in links turned off: <strong>1</strong> link revoked")
        self.assertContains(response, "Admin User &lt;admin@example.com&gt;")
        self.assertContains(response, reverse("admin:mail_smslinkrevocation_changelist"))


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True, FRONTEND_URL="https://i2g.example.edu")
class SwitchOffConfirmationTests(SwitchTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(make_superuser())
        self.confirm_url = reverse("admin:mail_smsconfig_confirm_change")

    def test_the_confirmation_page_lists_the_revocation_before_anything_is_revoked(self):
        response = self.client.post(self.change_url, settings_form(links_enabled="on"))
        self.assertEqual(response["Location"], self.confirm_url)

        page = self.client.get(self.confirm_url)

        self.assertContains(page, "Personal sign-in links already texted")
        self.assertContains(page, "1 still work")
        self.assertContains(page, REVOKED_FOR_GOOD)
        self.assertEqual(links.open_link(issue(self.member)).kind, "sign_in")  # nothing revoked yet

        confirmed = self.client.post(
            self.confirm_url,
            {"confirmation_word": "SMS settings", "token": self.client.session[SESSION_KEY]["token"]},
            follow=True,
        )

        self.assertContains(confirmed, "revoked for good")
        self.assertEqual(SmsLinkRevocation.objects.get().revoked_count, 1)
        self.assert_revoked()

    def test_a_change_that_keeps_them_on_lists_no_revocation(self):
        self.client.post(self.change_url, links_on(quiet_hours_start="21:00"))
        fields = [row["field"] for row in self.client.session[SESSION_KEY]["diff"]]
        self.assertIn("quiet_hours_start", fields)
        self.assertNotIn("personal_links_revoked", fields)
        self.assertNotContains(self.client.get(self.confirm_url), REVOKED_FOR_GOOD)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, FRONTEND_URL="https://i2g.example.edu")
class RevocationRecordsAdminTests(SwitchTestCase):
    def test_revocations_are_listed_read_only_with_who_when_and_how_many(self):
        admin = make_superuser()
        self.client.force_login(admin)
        self.client.post(self.change_url, settings_form(links_enabled="on"))
        sms_settings(personal_links_enabled=True)
        issue(self.member)
        SmsConfig.objects.update(links_enabled=False)  # one outside the admin: no one to name
        revocation = SmsLinkRevocation.objects.get(via=Via.ADMIN)

        listing = self.client.get(reverse("admin:mail_smslinkrevocation_changelist"))

        rows = [
            (row.reason, row.via, listing.context_data["cl"].model_admin.who(row), row.revoked_count)
            for row in listing.context_data["cl"].result_list
        ]
        self.assertEqual(
            rows,
            [
                (Reason.LINKS_OFF, Via.BULK_UPDATE, "Bulk update outside the admin", 1),
                (Reason.PERSONAL_LINKS_OFF, Via.ADMIN, "Admin User <admin@example.com>", 1),
            ],
        )
        self.assertContains(listing, "Admin User &lt;admin@example.com&gt;")
        detail = self.client.get(reverse("admin:mail_smslinkrevocation_change", args=[revocation.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'name="_save"')
        self.assertEqual(self.client.get(reverse("admin:mail_smslinkrevocation_add")).status_code, 403)

    def test_only_mail_staff_see_them(self):
        self.client.force_login(make_admin(apps=["cms"], email="cms@example.com"))
        self.assertEqual(self.client.get(reverse("admin:mail_smslinkrevocation_changelist")).status_code, 403)

    def test_sms_links_shows_revoked_links_including_one_stored_after_the_sweep(self):
        sms_settings(personal_links_enabled=False)
        swept = SmsLinkToken.objects.get()
        # Stored after the revocation by an issuer that read the switch as on: its row looks live, its epoch is stale.
        stale = SmsLinkToken.objects.create(
            token_hash="r" * 64,
            purpose="login",
            member=self.member,
            redirect_path="/",
            epoch=SmsConfig.load().personal_links_epoch - 1,
            expires_at=timezone.now() + timedelta(days=3),
        )
        shared = SmsLinkToken.objects.create(
            token_hash="s" * 64, purpose="event", redirect_path="/", expires_at=timezone.now() + timedelta(days=3)
        )
        model_admin = admin.site._registry[SmsLinkToken]
        request = RequestFactory().get("/admin/mail/smslinktoken/")
        request.user = make_superuser()

        statuses = {row.pk: model_admin.status_badge(row) for row in model_admin.get_queryset(request)}

        self.assertEqual(statuses, {swept.pk: "revoked", stale.pk: "revoked", shared.pk: "active"})
        self.client.force_login(request.user)
        self.assertContains(self.client.get(reverse("admin:mail_smslinktoken_change", args=[swept.pk])), "Revoked at")
