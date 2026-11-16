"""Members → Import: regressions for the security review of the import review flow.

- An I2G Master who applies another admin's import never lends it master rights (rights are the uploader's and the
  applier's together), and rows that changed go back to review on Skip.
- Marking an address verified makes it a sign-in factor, so it needs its own tick (R9) and is listed on Confirm, like
  every change to a staff or superuser account. A phone number is never marked verified (Phone Verified is ignored).
- An unfinished self-service sign-up can't be activated or verified by an import.
- Retention blanks everything that names a person; reading a sheet stops at the caps; over-long names can't be
  imported; the import without a review leaves staff accounts alone unless the caller is an I2G Master.
"""

from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactPhone, Member, MemberImportBatch
from apps.authn.services.members.import_.review.analysis.risky import MASTER_ONLY
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload


def _authn_admin(first):
    admin = Member.objects.create_user(
        password="StrongPass123!", first_name=first, last_name="Admin", is_staff=True, is_active=True
    )
    admin.admin_apps = ["authn"]
    admin.save(update_fields=["admin_apps"])
    return admin


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class _FlowCase(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.master = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Master")

    def upload_as(self, user, rows):
        self.client.force_login(user)
        response = self.client.post(
            reverse("admin:authn_member_import_excel"),
            {"excel_file": upload(HEADERS, rows), "mode": "update_existing", "upload_anyway": "on"},
        )
        self.assertEqual(response.status_code, 302)
        return MemberImportBatch.objects.order_by("-created_at").first()

    def confirm_as(self, user, batch):
        self.client.force_login(user)
        batch.refresh_from_db()
        return self.client.post(
            reverse("admin:authn_member_import_confirm", args=[batch.pk]),
            {"confirmation_text": "import", "version": batch.choices_version},
        )


class AppliedByAnotherAdminTests(_FlowCase):
    def setUp(self):
        super().setUp()
        self.deputy = _authn_admin("Deputy")
        self.staff = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        self.puppet = self.member("Pat", "Puppet", "pat@example.com")

    def test_a_masters_apply_never_lends_master_rights_to_a_non_masters_import(self):
        batch = self.upload_as(
            self.deputy,
            [
                row(
                    "sam@example.com",
                    First_Name="Sam",
                    Last_Name="Staff",
                    Phone_Number="2025550123",
                    Organization="Evil",
                ),
                row("pat@example.com", First_Name="Pat", Last_Name="Puppet", Staff="TRUE"),
            ],
        )
        staff_row, puppet_row = batch.rows.order_by("row_number")
        self.assertEqual((staff_row.conflict, staff_row.choice), ("privileged_target", "skip"))
        r8 = next(item for item in puppet_row.risky[str(self.puppet.pk)] if item["code"] == "R8")
        self.assertEqual((r8["enabled"], r8["reason"]), (False, MASTER_ONLY))

        # The puppet changes, so the master's first confirm sends that row back to review.
        Member.objects.filter(pk=self.puppet.pk).update(title="touched")
        self.assertRedirects(
            self.confirm_as(self.master, batch), reverse("admin:authn_member_import_review", args=[batch.pk])
        )
        puppet_row.refresh_from_db()
        r8 = next(item for item in puppet_row.risky[str(self.puppet.pk)] if item["code"] == "R8")
        self.assertEqual((puppet_row.choice, puppet_row.changed_since_review, r8["enabled"]), ("skip", True, False))

        # The deputy can't tick what only a master may change.
        batch.refresh_from_db()
        self.client.force_login(self.deputy)
        self.client.post(
            reverse("admin:authn_member_import_review", args=[batch.pk]),
            {
                "version": batch.choices_version,
                "ready-3": "update",
                "ticks-3": "1",
                "tick-3": r8["id"],
                "action": "save",
            },
        )
        puppet_row.refresh_from_db()
        self.assertEqual((puppet_row.choice, puppet_row.ticks), ("skip", []))

        self.confirm_as(self.master, batch)

        self.staff.refresh_from_db()
        self.puppet.refresh_from_db()
        self.assertIsNone(self.staff.organization)
        self.assertFalse(ContactPhone.objects.filter(member=self.staff).exists())
        self.assertFalse(self.puppet.is_staff)

    def test_an_import_whose_uploader_was_deleted_cannot_be_applied(self):
        batch = self.upload_as(
            self.deputy, [row("pat@example.com", First_Name="Pat", Last_Name="Puppet", Organization="X")]
        )
        self.deputy.delete()

        response = self.confirm_as(self.master, batch)

        self.assertRedirects(response, reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.puppet.refresh_from_db()
        self.assertIsNone(self.puppet.organization)
