from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, Member, MemberImportBatch
from apps.authn.services.members.import_.review import apply_batch
from apps.authn.services.members.import_.review.analysis import Context
from apps.authn.tests.admin.members.import_.test_member_import_apply import _staff
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload


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
