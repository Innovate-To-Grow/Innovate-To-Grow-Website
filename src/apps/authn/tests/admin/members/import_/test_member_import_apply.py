"""Members → Import: what the apply guarantees, through the admin views.

The review is the plan: if a record it read changed, nothing is applied and those rows go back to review; a double
submit applies once; an outdated page can't confirm; a failing row writes nothing; only the uploader (or an I2G
Master) may change or apply a batch.
"""

from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, ContactPhone, Member, MemberImportBatch
from apps.authn.services.members.export_excel import export_members_to_excel
from apps.authn.services.members.import_.review import apply_batch
from apps.authn.services.members.import_.review.analysis import Context
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload


def _staff(first, admin_apps=("authn",)):
    member = Member.objects.create_user(
        password="StrongPass123!", first_name=first, last_name="Admin", is_staff=True, is_active=True
    )
    member.admin_apps = list(admin_apps)
    member.save(update_fields=["admin_apps"])
    return member


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ApplyGuaranteeTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.master = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Master")
        self.client.force_login(self.master)

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
        export = export_members_to_excel(Member.objects.exclude(pk=self.master.pk).order_by("first_name"))
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


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class OwnershipAndPermissionTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.owner = _staff("Owner")
        self.other = _staff("Other")
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("admin:authn_member_import_excel"),
            {"excel_file": upload(HEADERS, [row("ada@example.com", Organization="Acme")]), "mode": "update_existing"},
        )
        self.assertEqual(response.status_code, 302)
        self.batch = MemberImportBatch.objects.get()

    def test_another_authn_admin_sees_the_batch_read_only(self):
        self.client.force_login(self.other)
        review = reverse("admin:authn_member_import_review", args=[self.batch.pk])

        page = self.client.get(review)

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "You can look at it; only they or an I2G Master can change it.")
        self.assertNotContains(page, "Continue to confirm")
        self.assertEqual(self.client.post(review, {"version": 0, "action": "save"}).status_code, 403)
        confirm = reverse("admin:authn_member_import_confirm", args=[self.batch.pk])
        self.assertEqual(self.client.post(confirm, {"confirmation_text": "import", "version": 0}).status_code, 403)
        discard = reverse("admin:authn_member_import_discard", args=[self.batch.pk])
        self.assertEqual(self.client.post(discard).status_code, 403)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, "review")

    def test_an_i2g_master_may_apply_someone_elses_batch(self):
        master = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Master")
        self.client.force_login(master)

        self.client.post(
            reverse("admin:authn_member_import_confirm", args=[self.batch.pk]),
            {"confirmation_text": "import", "version": 0},
        )

        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Acme")

    def test_a_grant_revoked_before_the_apply_gets_403_and_writes_nothing(self):
        self.owner.admin_apps = ["event"]
        self.owner.save(update_fields=["admin_apps"])

        response = self.client.post(
            reverse("admin:authn_member_import_confirm", args=[self.batch.pk]),
            {"confirmation_text": "import", "version": 0},
        )

        self.assertEqual(response.status_code, 403)
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)

    def test_a_member_made_staff_after_the_review_is_not_changed_by_a_non_master(self):
        Member.objects.filter(pk=self.ada.pk).update(is_staff=True)

        response = self.client.post(
            reverse("admin:authn_member_import_confirm", args=[self.batch.pk]),
            {"confirmation_text": "import", "version": 0},
        )

        self.assertRedirects(response, reverse("admin:authn_member_import_review", args=[self.batch.pk]))
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)
        staged = self.batch.rows.get()
        self.assertEqual(
            (staged.conflict, staged.choice, staged.changed_since_review), ("privileged_target", "skip", True)
        )

    def test_the_uploader_may_discard(self):
        response = self.client.post(reverse("admin:authn_member_import_discard", args=[self.batch.pk]))

        self.assertRedirects(response, reverse("admin:authn_member_import_excel"))
        self.batch.refresh_from_db()
        self.assertEqual((self.batch.status, self.batch.default_password_hash), ("discarded", ""))
        result = self.client.get(reverse("admin:authn_member_import_review", args=[self.batch.pk]))
        self.assertRedirects(result, reverse("admin:authn_member_import_result", args=[self.batch.pk]))

    def test_discard_is_post_only(self):
        url = reverse("admin:authn_member_import_discard", args=[self.batch.pk])
        self.assertEqual(self.client.get(url).status_code, 405)


class HistoryAdminTests(ImportTestCase):
    def test_the_history_is_read_only_and_offers_no_export(self):
        master = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Master")
        self.client.force_login(master)
        batch = self.stage([row("new@example.com", First_Name="New", Last_Name="Person")], master)

        listing = self.client.get(reverse("admin:authn_memberimportbatch_changelist"))
        detail = self.client.get(reverse("admin:authn_memberimportbatch_change", args=[batch.pk]))

        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Open the review")
        self.assertNotContains(listing, "export_data")
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'name="_save"')
        self.assertEqual(self.client.get(reverse("admin:authn_memberimportbatch_add")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("admin:authn_memberimportbatch_delete", args=[batch.pk]), {"post": "yes"}
            ).status_code,
            403,
        )


class PlatformWiringTests(ImportTestCase):
    def test_the_ai_and_cli_layers_cannot_reach_the_staged_imports(self):
        from apps.core.services.db_tools.safe_orm.constants import DENIED_MODEL_LABELS

        self.assertIn("authn.memberimportbatch", DENIED_MODEL_LABELS)
        self.assertIn("authn.memberimportrow", DENIED_MODEL_LABELS)

    def test_the_worker_purges_member_imports(self):
        from apps.core.management.commands.run_background_worker import MAINTENANCE_TASKS, run_maintenance

        self.assertIn("Member import purge", [name for name, _task in MAINTENANCE_TASKS])
        batch = self.stage([row("new@example.com", First_Name="New", Last_Name="Person")], self.ada)
        MemberImportBatch.objects.filter(pk=batch.pk).update(expires_at="2000-01-01T00:00:00Z")

        run_maintenance([task for task in MAINTENANCE_TASKS if task[0] == "Member import purge"])

        self.assertFalse(MemberImportBatch.objects.exists())

    def test_apply_batch_refuses_an_expired_review(self):
        batch = self.stage([row("new@example.com", First_Name="New", Last_Name="Person")], self.ada)
        MemberImportBatch.objects.filter(pk=batch.pk).update(expires_at="2000-01-01T00:00:00Z")

        result = apply_batch(batch.pk, user=self.ada, version=0, ctx=Context())

        self.assertEqual(result.status, "refused")
        self.assertIn("expired", result.message)
        self.assertFalse(ContactEmail.objects.filter(email_address="new@example.com").exists())
