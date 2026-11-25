"""Members → Import: regressions for the security review of the import review flow.

- Any Admin may apply another Admin's import, rows naming an Admin account included; rows that changed go back to
  review on Skip. An import never grants or removes Admin access (the Admin or Staff column is ignored).
- Nobody deactivates their own Admin account through an import, and the last active Admin is never deactivated: the
  tick is disabled with the reason, and the apply checks again for the Admin who applies.
- Marking an address verified makes it a sign-in factor, so it needs its own tick (R9) and is listed on Confirm, like
  every change to an Admin account. A phone number is never marked verified (Phone Verified is ignored).
- An unfinished self-service sign-up can't be activated or verified by an import.
- Retention blanks everything that names a person; reading a sheet stops at the caps; over-long names can't be
  imported.
"""

from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactPhone, Member, MemberImportBatch
from apps.authn.tests.admin.members.import_.test_member_import_apply import _admin
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload

OWN_ACCOUNT = "You cannot deactivate your own Admin account. Ask another Admin to do it."


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class _FlowCase(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = Member.objects.create_superuser(
            password="StrongPass123!", first_name="I2G", last_name="Admin"
        )

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
        self.deputy = _admin("Deputy")
        self.sam = self.member("Sam", "Admin", "sam@example.com", is_staff=True)
        self.pat = self.member("Pat", "Puppet", "pat@example.com")

    def test_any_admin_may_apply_another_admins_import_and_it_never_grants_admin_access(self):
        sam_row = row(
            "sam@example.com", First_Name="Sam", Last_Name="Admin", Phone_Number="2025550123", Organization="New"
        )
        batch = self.upload_as(
            self.deputy, [sam_row, row("pat@example.com", First_Name="Pat", Last_Name="Puppet", Staff="TRUE")]
        )
        staged_sam, staged_pat = batch.rows.order_by("row_number")
        self.assertEqual((staged_sam.status, staged_sam.conflict, staged_sam.choice), ("ready_update", "", "update"))
        self.assertEqual(staged_pat.risky, {})

        response = self.confirm_as(self.admin_user, batch)

        self.assertRedirects(response, reverse("admin:authn_member_import_result", args=[batch.pk]))
        self.sam.refresh_from_db()
        self.pat.refresh_from_db()
        self.assertEqual(self.sam.organization, "New")
        self.assertEqual(list(ContactPhone.objects.filter(member=self.sam).values_list("verified", flat=True)), [False])
        self.assertEqual((self.pat.is_staff, self.pat.is_superuser), (False, False))
        batch.refresh_from_db()
        self.assertEqual(batch.summary["risky"], {"privileged_changes": 1})


class DeactivationLockoutTests(_FlowCase):
    def setUp(self):
        super().setUp()
        self.deputy = self.member("Deputy", "Admin", "deputy@example.com", is_staff=True)
        self.deactivate = row("deputy@example.com", First_Name="Deputy", Last_Name="Admin", Active="No")

    def r7(self, batch):
        return next(item for item in batch.rows.get().risky[str(self.deputy.pk)] if item["code"] == "R7")

    def test_your_own_admin_account_cannot_be_ticked(self):
        batch = self.upload_as(self.deputy, [self.deactivate])
        r7 = self.r7(batch)
        self.assertEqual((r7["enabled"], r7["reason"]), (False, OWN_ACCOUNT))

        self.client.post(
            reverse("admin:authn_member_import_review", args=[batch.pk]),
            {"version": 0, "ready-2": "update", "ticks-2": "1", "tick-2": r7["id"], "action": "save"},
        )

        self.assertEqual(batch.rows.get().ticks, [])

    def test_another_admins_tick_is_checked_again_for_the_admin_who_applies(self):
        batch = self.upload_as(self.admin_user, [self.deactivate])
        r7 = self.r7(batch)
        self.assertTrue(r7["enabled"])
        self.client.post(
            reverse("admin:authn_member_import_review", args=[batch.pk]),
            {"version": 0, "ready-2": "update", "ticks-2": "1", "tick-2": r7["id"], "action": "save"},
        )
        self.assertEqual(batch.rows.get().ticks, [r7["id"]])

        response = self.confirm_as(self.deputy, batch)

        self.assertRedirects(response, reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.deputy.refresh_from_db()
        self.assertTrue(self.deputy.is_active)
        staged = batch.rows.get()
        self.assertEqual((staged.ticks, staged.changed_since_review), ([], True))
        self.assertEqual(self.r7(batch)["reason"], OWN_ACCOUNT)

        self.confirm_as(self.admin_user, batch)  # nothing ticked any more: the row only stays as it is
        self.deputy.refresh_from_db()
        self.assertTrue(self.deputy.is_active)
