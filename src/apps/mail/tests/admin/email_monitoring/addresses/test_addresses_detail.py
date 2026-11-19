from io import BytesIO
from urllib.parse import urlencode

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.authn.models import ContactEmail
from apps.core.tests.services.email_monitoring.helpers import make_email, monitoring_settings
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BouncedAddress, BouncedAddressAction
from apps.mail.tests.admin.email_monitoring.addresses.test_addresses_admin import DETAIL, EXPORT
from apps.mail.tests.services.bounced_addresses.helpers import (
    add_email,
    count_now,
    make_bounce,
    make_campaign,
    make_person,
    make_row,
    make_ses_log,
)


class DetailTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_the_page_shows_reports_member_campaigns_actions_and_history(self):
        member = make_person("detail@example.org", first="Dina")
        add_email(member, "alt@example.org", verified=True)
        blast = make_campaign("Blast")
        email = make_email(recipient="detail@example.org", campaign_id=blast.pk)
        make_bounce(recipient="detail@example.org", email=email, campaign_id=blast.pk, remote_mta="mx.example.org")
        make_ses_log(blast, "detail@example.org", bounce_type="Transient")
        count_now()
        row = BouncedAddress.objects.get(address="detail@example.org")
        BouncedAddressAction.objects.create(bounced_address=row, address=row.address, action="dismiss", note="checked")

        response = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(response, "mx.example.org")
        self.assertContains(response, "Amazon SES events")
        self.assertContains(response, "Blast")
        self.assertContains(response, "Dina Doe")
        self.assertContains(response, "alt@example.org")
        self.assertContains(response, "checked")
        allowed = {item["action"]: item["allowed"] for item in response.context["actions"]}
        self.assertTrue(allowed["mark_undeliverable"])
        self.assertTrue(allowed["make_primary"])
        self.assertFalse(allowed["suppress"])

    def test_retry_link_only_appears_for_an_eligible_campaign_recipient(self):
        from apps.mail.models import BouncedAddressCampaign, RecipientLog

        campaign = make_campaign("Retry campaign")
        recipient = "retry@example.org"
        member = make_person(recipient)
        RecipientLog.objects.create(
            campaign=campaign, member=member, email_address=recipient, status="bounced", sent_at=timezone.now()
        )
        row = make_row(recipient, hard_count=0, soft_count=1, last_category="transient")
        BouncedAddressCampaign.objects.create(
            bounced_address=row,
            campaign_id=campaign.pk,
            source="graph",
            match="exact",
            bounce_count=1,
            graph_category_counts={"transient": 1},
        )

        response = self.client.get(reverse(DETAIL, args=[row.pk]))
        url = reverse("admin:mail_emailcampaign_duplicate_campaign_action", args=[campaign.pk])
        self.assertContains(response, url + "?" + urlencode({"retry_address": recipient}))

        row.suppressed_at = row.last_bounce_at
        row.save(update_fields=["suppressed_at"])
        self.assertNotContains(self.client.get(reverse(DETAIL, args=[row.pk])), "Prepare one-address draft")

    def test_a_members_other_addresses_are_shown_only_with_the_members_app(self):
        member = make_person("card@example.org", first="Cara")
        add_email(member, "hidden-alt@example.org", verified=True)
        row = make_row("card@example.org")
        self.client.force_login(make_admin(apps=["mail"], email="mailstaff@example.org"))

        response = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(response, "Cara Doe")
        self.assertNotContains(response, "hidden-alt@example.org")
        self.assertContains(response, "shown to staff who also hold the Members app")
        self.client.force_login(make_admin(apps=["mail", "authn"], email="memberstaff@example.org"))
        self.assertContains(self.client.get(reverse(DETAIL, args=[row.pk])), "hidden-alt@example.org")

    def test_disabled_actions_say_why(self):
        make_person("why@example.org")
        row = make_row("why@example.org")
        self.client.force_login(make_admin(apps=["mail"], email="mailstaff@example.org"))

        response = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(response, "Needs the Members (authn) app as well as Mail.")
        self.assertContains(response, "disabled aria-disabled")

    def test_an_ambiguous_address_lists_every_contact_record(self):
        make_person("Dup@Example.org", first="Ann")
        make_person("dup@example.org", first="Bob")
        row = make_row("dup@example.org")

        response = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(response, "saved 2 times in different letter cases")
        for contact in ContactEmail.objects.filter(email_address__iexact="dup@example.org"):
            self.assertContains(response, reverse("admin:authn_contactemail_change", args=[contact.pk]))


class ExportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_the_filtered_list_is_exported_formula_safe(self):
        make_person("formula@example.org", first="=HYPERLINK(1)", last="X")
        make_row("formula@example.org")
        make_row("other@example.org", status=BouncedAddress.Status.DISMISSED)

        response = self.client.get(reverse(EXPORT), {"status": "open"})

        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn('attachment; filename="bounced_addresses_', response["Content-Disposition"])
        sheet = load_workbook(BytesIO(response.content)).active
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(rows[0][0], "Address")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "formula@example.org")
        self.assertEqual(rows[1][4], "'=HYPERLINK(1) X")
        self.assertEqual(rows[1][3], "Primary")

    def test_control_characters_in_a_name_never_break_the_export(self):
        make_person("ctrl@example.org", first="Pat\x0b", last="\x01Doe")
        make_row("ctrl@example.org")

        response = self.client.get(reverse(EXPORT))

        self.assertEqual(response.status_code, 200)
        rows = list(load_workbook(BytesIO(response.content)).active.iter_rows(values_only=True))
        self.assertEqual(rows[1][4], "Pat Doe")

    def test_the_export_is_capped(self):
        for index in range(3):
            make_row(f"cap{index}@example.org")

        with monitoring_settings(address_export_max_rows=2):
            response = self.client.get(reverse(EXPORT))

        self.assertEqual(len(list(load_workbook(BytesIO(response.content)).active.iter_rows())), 3)
