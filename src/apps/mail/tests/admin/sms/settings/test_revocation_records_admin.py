from datetime import timedelta

from django.contrib import admin
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import SmsConfig, SmsLinkRevocation, SmsLinkToken
from apps.mail.tests.admin.sms.settings.test_link_revocation_admin import Reason, SwitchTestCase, Via, issue

from ....services.sms.policy.policy_helpers import sms_settings
from .test_sms_settings_admin import settings_form


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
