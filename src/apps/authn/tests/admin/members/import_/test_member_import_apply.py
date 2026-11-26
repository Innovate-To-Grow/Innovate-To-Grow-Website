"""Members → Import: what the apply guarantees, through the admin views.

The review is the plan: if a record it read changed, nothing is applied and those rows go back to review; a double
submit applies once; an outdated page can't confirm; a failing row writes nothing; any Admin may change or apply a
batch, whoever uploaded it.
"""

from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, ContactPhone, Member, MemberImportBatch
from apps.authn.services.members.export.excel import export_members_to_excel
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload


def _admin(first):
    """An Admin (an active member with ``is_staff``) named ``<first> Admin``."""
    return Member.objects.create_user(
        password="StrongPass123!", first_name=first, last_name="Admin", is_staff=True, is_active=True
    )


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ApplyGuaranteeTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = Member.objects.create_superuser(
            password="StrongPass123!", first_name="I2G", last_name="Admin"
        )
        self.client.force_login(self.admin_user)

    def _upload(self, rows, headers=HEADERS):
        response = self.client.post(
            reverse("admin:authn_member_import_excel"),
            {"excel_file": upload(headers, rows), "mode": "update_existing"},
        )
        self.assertEqual(response.status_code, 302)
        return MemberImportBatch.objects.order_by("-created_at").first()

    def _confirm(self, batch, version=None):
        batch.refresh_from_db()
        return self.client.post(
            reverse("admin:authn_member_import_confirm", args=[batch.pk]),
            {"confirmation_text": "import", "version": batch.choices_version if version is None else version},
        )

    def test_a_record_changed_by_queryset_update_sends_the_row_back_to_review(self):
        batch = self._upload([row("ada@example.com", Organization="Acme")])
        # "Mark verified"-style change that does not touch updated_at.
        ContactEmail.objects.filter(email_address="ada@example.com").update(subscribe=False)

        response = self._confirm(batch)

        self.assertRedirects(response, reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)
        batch.refresh_from_db()
        staged = batch.rows.get()
        self.assertEqual(batch.status, "review")
        self.assertTrue(staged.changed_since_review)
        self.assertEqual(batch.choices_version, 1)
        self.assertIn("changed since you reviewed them (rows 2)", batch.last_error)
        page = self.client.get(reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.assertContains(page, "Changed since you reviewed it")

    def test_applying_twice_has_one_effect(self):
        batch = self._upload([row("new@example.com", First_Name="New", Last_Name="Person")])

        first = self._confirm(batch, version=0)
        second = self._confirm(batch, version=0)

        result = reverse("admin:authn_member_import_result", args=[batch.pk])
        self.assertRedirects(first, result)
        self.assertRedirects(second, result)
        self.assertEqual(ContactEmail.objects.filter(email_address="new@example.com").count(), 1)
        self.assertEqual(LogEntry.objects.filter(change_message__startswith="Created by member import").count(), 1)

    def test_an_outdated_page_cannot_confirm(self):
        batch = self._upload([row("new@example.com", First_Name="New", Last_Name="Person")])
        self.client.post(
            reverse("admin:authn_member_import_review", args=[batch.pk]),
            {"version": 0, "ready-2": "create", "skip-2": "1", "action": "save"},
        )

        response = self._confirm(batch, version=0)

        self.assertRedirects(response, reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.assertFalse(ContactEmail.objects.filter(email_address="new@example.com").exists())
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.choices_version), ("review", 1))

    def test_a_failing_row_writes_nothing_and_names_the_row(self):
        batch = self._upload(
            [
                row("new@example.com", First_Name="New", Last_Name="Person"),
                row("ada@example.com", Organization="Acme", Phone_Number="+12095550001"),
            ]
        )

        with patch(
            "apps.authn.services.members.import_.contacts.create_contact_phone", side_effect=RuntimeError("boom")
        ):
            response = self._confirm(batch)

        self.assertRedirects(response, reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.assertFalse(ContactEmail.objects.filter(email_address="new@example.com").exists())
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "review")
        self.assertEqual(batch.last_error, "Nothing was imported. Row 3: boom")

    def test_the_result_page_lists_every_row_and_the_history_is_written(self):
        batch = self._upload(
            [
                row("new@example.com", First_Name="New", Last_Name="Person", Phone_Number="+12095550099"),
                row("ada@example.com", Organization="Acme"),
                row("", First_Name="No", Last_Name="Address"),
            ]
        )

        self._confirm(batch)

        batch.refresh_from_db()
        self.assertEqual(batch.status, "applied")
        self.assertEqual(batch.default_password_hash, "")
        self.assertEqual(batch.summary["outcomes"], {"created": 1, "updated": 1, "not_imported": 1})
        page = self.client.get(reverse("admin:authn_member_import_result", args=[batch.pk]))
        self.assertContains(page, "Creates the member New Person")
        self.assertContains(page, "Organization: &#x27;&#x27; → &#x27;Acme&#x27;")
        self.assertContains(page, "Missing primary email")
        created = Member.objects.get(first_name="New")
        self.assertTrue(LogEntry.objects.filter(object_id=str(created.pk), change_message__contains="row 2").exists())
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.ada.pk), change_message__contains="row 3").exists())
        self.assertTrue(LogEntry.objects.filter(object_id=str(batch.pk), change_message__startswith="Applied").exists())
        self.assertEqual(mail.outbox, [])

    def test_an_unchanged_export_round_trip_writes_nothing(self):
        self.email(self.ada, "one@example.com", verified=True)
        self.email(self.ada, "two@example.com")
        self.phone(self.ada, "2095550001", verified=True)
        phone_only = self.member("Phone", "Only")
        self.phone(phone_only, "2095550099", verified=True)
        Member.objects.filter(pk=self.ada.pk).update(organization="+Plus Corp")
        export = export_members_to_excel(Member.objects.exclude(pk=self.admin_user.pk).order_by("first_name"))
        before = (
            sorted(Member.objects.values_list("pk", "updated_at")),
            sorted(ContactEmail.objects.values_list("pk", "updated_at", "email_type", "verified", "subscribe")),
            sorted(ContactPhone.objects.values_list("pk", "updated_at", "verified", "subscribe")),
        )
        response = self.client.post(
            reverse("admin:authn_member_import_excel"),
            {
                "excel_file": upload_bytes(export),
                "mode": "update_existing",
            },
        )
        batch = MemberImportBatch.objects.get()
        self.assertEqual(response.status_code, 302)
        statuses = sorted(batch.rows.values_list("status", flat=True))
        self.assertEqual(statuses, ["invalid", "no_change"])

        with patch("apps.authn.services.sms.sns_verify._publish_sms") as sms:
            self._confirm(batch)

        after = (
            sorted(Member.objects.values_list("pk", "updated_at")),
            sorted(ContactEmail.objects.values_list("pk", "updated_at", "email_type", "verified", "subscribe")),
            sorted(ContactPhone.objects.values_list("pk", "updated_at", "verified", "subscribe")),
        )
        self.assertEqual(after, before)
        self.assertFalse(LogEntry.objects.filter(content_type__model="member").exists())
        self.assertEqual(mail.outbox, [])
        sms.assert_not_called()


def upload_bytes(content: bytes):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        "export.xlsx", content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
