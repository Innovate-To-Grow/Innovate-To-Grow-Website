"""Members → Import: who may use a batch. Any Admin may save its choices, apply it or discard it, whoever uploaded it
(an Admin who uploaded one may have left); a member who is no longer an Admin is sent to the admin login."""

from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, MemberImportBatch
from apps.authn.services.members.import_.review import apply_batch
from apps.authn.services.members.import_.review.analysis import Context
from apps.authn.tests.admin.members.import_.test_member_import_apply import _admin
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class OwnershipAndPermissionTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.owner = _admin("Owner")
        self.other = _admin("Other")
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("admin:authn_member_import_excel"),
            {"excel_file": upload(HEADERS, [row("ada@example.com", Organization="Acme")]), "mode": "update_existing"},
        )
        self.assertEqual(response.status_code, 302)
        self.batch = MemberImportBatch.objects.get()

    def confirm(self):
        return self.client.post(
            reverse("admin:authn_member_import_confirm", args=[self.batch.pk]),
            {"confirmation_text": "import", "version": self.batch.choices_version},
        )

    def test_another_admin_may_change_and_apply_the_batch(self):
        self.client.force_login(self.other)
        review = reverse("admin:authn_member_import_review", args=[self.batch.pk])

        page = self.client.get(review)
        saved = self.client.post(review, {"version": 0, "ready-2": "update", "action": "save"})
        self.batch.refresh_from_db()
        applied = self.confirm()

        self.assertContains(page, "Continue to confirm")
        self.assertContains(page, "Discard this import")
        self.assertRedirects(saved, review, fetch_redirect_response=False)
        self.assertRedirects(applied, reverse("admin:authn_member_import_result", args=[self.batch.pk]))
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Acme")
        self.batch.refresh_from_db()
        self.assertEqual((self.batch.status, self.batch.applied_by), ("applied", self.other))

    def test_another_admin_may_discard_the_batch(self):
        self.client.force_login(self.other)

        response = self.client.post(reverse("admin:authn_member_import_discard", args=[self.batch.pk]))

        self.assertRedirects(response, reverse("admin:authn_member_import_excel"))
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, "discarded")

    def test_the_upload_page_lists_every_admins_imports_in_review(self):
        self.client.force_login(self.other)

        page = self.client.get(reverse("admin:authn_member_import_excel"))

        self.assertContains(page, reverse("admin:authn_member_import_review", args=[self.batch.pk]))

    def test_an_import_whose_uploader_was_deleted_can_still_be_applied(self):
        self.owner.delete()
        self.client.force_login(self.other)
        self.batch.refresh_from_db()

        response = self.confirm()

        self.assertRedirects(response, reverse("admin:authn_member_import_result", args=[self.batch.pk]))
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Acme")

    def test_a_member_who_is_no_longer_an_admin_is_sent_to_the_login_and_writes_nothing(self):
        self.owner.is_staff = False
        self.owner.save()

        response = self.confirm()

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)

    def test_a_member_made_an_admin_after_the_review_goes_back_to_the_review(self):
        """Any Admin may update an Admin, but the record the review showed changed: the row is reviewed again."""
        self.ada.is_staff = True
        self.ada.save()

        response = self.confirm()

        self.assertRedirects(response, reverse("admin:authn_member_import_review", args=[self.batch.pk]))
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)
        staged = self.batch.rows.get()
        self.assertEqual((staged.conflict, staged.choice, staged.changed_since_review), ("", "skip", True))

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
        admin = _admin("History")
        self.client.force_login(admin)
        batch = self.stage([row("new@example.com", First_Name="New", Last_Name="Person")], admin)

        listing = self.client.get(reverse("admin:authn_memberimportbatch_changelist"))
        detail = self.client.get(reverse("admin:authn_memberimportbatch_change", args=[batch.pk]))

        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Open the review")
        self.assertNotContains(listing, "export_data")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Member import rows")  # every Admin sees the staged rows inline
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
