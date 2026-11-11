"""Members → Import end to end: Upload → Review → Confirm → Result, through the admin.

The Row 5 case: the sheet's Primary Email is Neil's *secondary* address. The review shows it as a decision (C7),
skipped until the admin chooses; "update, keep the email roles" and "make this the primary" both keep every address.
"""

from django.contrib.admin.models import LogEntry
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, Member, MemberImportBatch
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class Row5FlowTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.admin = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Master")
        self.client.force_login(self.admin)
        self.neil = self.member("Neil", "Parkhi", "neil@home.example")
        self.work = self.email(self.neil, "neil.r.parkhi@spiritaero.example", verified=True, subscribe=True)

    def _upload(self, rows):
        response = self.client.post(
            reverse("admin:authn_member_import_excel"),
            {"excel_file": upload(HEADERS, rows), "mode": "update_existing"},
        )
        self.assertEqual(
            response.status_code, 302, getattr(response, "context", None) and response.context["form"].errors
        )
        return MemberImportBatch.objects.get()

    def _row5(self):
        return row(
            "neil.r.parkhi@spiritaero.example",
            First_Name="Neil",
            Last_Name="Parkhi",
            Primary_Verified="TRUE",
            Primary_Subscribed="TRUE",
            Secondary_Email="",
            Phone_Number="",
            Organization="Spirit AeroSystems",
        )

    def _confirm(self, batch):
        batch.refresh_from_db()
        return self.client.post(
            reverse("admin:authn_member_import_confirm", args=[batch.pk]),
            {"confirmation_text": "import", "version": batch.choices_version},
        )

    def test_upload_writes_no_member_data_and_shows_the_decision(self):
        before = (Member.objects.count(), ContactEmail.objects.count())

        batch = self._upload([self._row5()])

        self.assertEqual((Member.objects.count(), ContactEmail.objects.count()), before)
        row5 = batch.rows.get()
        self.assertEqual((row5.status, row5.conflict, row5.choice), ("needs_decision", "address_not_primary", "skip"))
        response = self.client.get(reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.assertContains(response, "C7 · The address is a member&#x27;s secondary or other email")
        self.assertContains(response, "is the secondary email of Neil Parkhi")
        self.assertContains(response, "Update Neil Parkhi (member")
        self.assertContains(response, "(the Secondary Email cell is blank)")
        self.assertContains(response, "This is the address the row was matched on")

    def test_skipped_by_default_changes_nothing(self):
        batch = self._upload([self._row5()])

        response = self._confirm(batch)

        self.assertRedirects(response, reverse("admin:authn_member_import_result", args=[batch.pk]))
        self.neil.refresh_from_db()
        self.assertIsNone(self.neil.organization)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "applied")
        self.assertEqual(batch.rows.get().outcome, "skipped")

    def test_update_keeping_the_roles(self):
        batch = self._upload([self._row5()])
        review = reverse("admin:authn_member_import_review", args=[batch.pk])
        self.client.post(review, {"version": 0, "choice-2": "update", "ticks-2": "1", "action": "save"})

        response = self._confirm(batch)

        self.assertEqual(response.status_code, 302)
        self.neil.refresh_from_db()
        self.assertEqual(self.neil.organization, "Spirit AeroSystems")
        roles = dict(self.neil.contact_emails.values_list("email_address", "email_type"))
        self.assertEqual(roles, {"neil@home.example": "primary", "neil.r.parkhi@spiritaero.example": "secondary"})
        row5 = MemberImportBatch.objects.get().rows.get()
        self.assertEqual((row5.outcome, row5.chosen_by, row5.result_member), ("updated", self.admin, self.neil))
        entry = LogEntry.objects.get(object_id=str(self.neil.pk))
        self.assertIn(
            "row 2: matched by secondary email; Organization: '' → 'Spirit AeroSystems'", entry.change_message
        )
        self.assertEqual(mail.outbox, [])

    def test_make_the_address_primary(self):
        batch = self._upload([self._row5()])
        review = reverse("admin:authn_member_import_review", args=[batch.pk])
        self.client.post(review, {"version": 0, "choice-2": "update_make_primary", "action": "continue"})

        self._confirm(batch)

        roles = dict(self.neil.contact_emails.values_list("email_address", "email_type"))
        self.assertEqual(roles, {"neil@home.example": "secondary", "neil.r.parkhi@spiritaero.example": "primary"})

    def test_make_primary_is_refused_for_an_unverified_address(self):
        ContactEmail.objects.filter(pk=self.work.pk).update(verified=False)
        batch = self._upload([self._row5()])
        review = reverse("admin:authn_member_import_review", args=[batch.pk])

        response = self.client.post(review, {"version": 0, "choice-2": "update_make_primary", "action": "save"})

        self.assertRedirects(response, review)
        self.assertEqual(batch.rows.get().choice, "skip")
        page = self.client.get(review)
        self.assertContains(page, "Not verified. The member can verify it on /account")

    def test_typed_confirmation_is_required(self):
        batch = self._upload([self._row5()])
        response = self.client.post(
            reverse("admin:authn_member_import_confirm", args=[batch.pk]), {"confirmation_text": "yes", "version": 0}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Type &quot;import&quot; to confirm.")
        batch.refresh_from_db()
        self.assertEqual(batch.status, "review")
