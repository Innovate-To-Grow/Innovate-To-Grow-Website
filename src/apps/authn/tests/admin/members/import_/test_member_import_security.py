"""Members → Import: regressions for the security review of the import review flow.

- An I2G Master who applies another admin's import never lends it master rights (rights are the uploader's and the
  applier's together), and rows that changed go back to review on Skip.
- Marking an address verified makes it a sign-in factor, so it needs its own tick (R9) and is listed on Confirm, like
  every change to a staff or superuser account. A phone number is never marked verified (Phone Verified is ignored).
- An unfinished self-service sign-up can't be activated or verified by an import.
- Retention blanks everything that names a person; reading a sheet stops at the caps; over-long names can't be
  imported; the import without a review leaves staff accounts alone unless the caller is an I2G Master.
"""

from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone, Member, MemberImportBatch
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.reader import read_upload
from apps.authn.services.members.import_.review import purge_member_imports
from apps.authn.services.members.import_.review.risky import MASTER_ONLY, PENDING
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload, workbook_bytes


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


class SignInFactorTests(_FlowCase):
    def test_marking_an_address_verified_needs_its_tick_and_is_listed_on_confirm(self):
        work = self.email(self.ada, "ada.work@example.com", verified=False)
        cells = {"Secondary_Email": "ada.work@example.com", "Secondary_Verified": "TRUE"}
        batch = self.upload_as(self.master, [row("ada@example.com", **cells)])
        staged = batch.rows.get()
        r9 = next(item for item in staged.risky[str(self.ada.pk)] if item["code"] == "R9")
        self.assertTrue(r9["enabled"])

        self.confirm_as(self.master, batch)
        work.refresh_from_db()
        self.assertFalse(work.verified)
        self.assertIn(
            "Secondary Verified is TRUE, but ada.work@example.com is unverified; left unverified",
            staged.__class__.objects.get(pk=staged.pk).outcome_detail,
        )

        again = self.upload_as(self.master, [row("ada@example.com", **cells)])
        review = reverse("admin:authn_member_import_review", args=[again.pk])
        self.client.post(
            review, {"version": 0, "ready-2": "update", "ticks-2": "1", "tick-2": r9["id"], "action": "save"}
        )
        page = self.client.get(reverse("admin:authn_member_import_confirm", args=[again.pk]))
        self.assertContains(page, "Email addresses marked verified (each becomes a sign-in factor) (1)")

        self.confirm_as(self.master, again)
        work.refresh_from_db()
        self.assertTrue(work.verified)

    def test_every_change_to_a_staff_account_is_listed_on_confirm(self):
        staff = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        batch = self.upload_as(
            self.master, [row("sam@example.com", First_Name="Sam", Last_Name="Staff", Organization="New")]
        )

        page = self.client.get(reverse("admin:authn_member_import_confirm", args=[batch.pk]))

        self.assertContains(page, "Changes to staff or superuser accounts (1)")
        self.assertContains(page, f"Sam Staff (member {staff.pk}): Organization")

    def test_an_unfinished_sign_up_cannot_be_activated_or_verified(self):
        squatter = self.member("Vic", "Tim", "vic@example.com", verified=False)
        Member.objects.filter(pk=squatter.pk).update(is_active=False, registration_pending=True)
        batch = self.upload_as(
            self.master,
            [row("vic@example.com", First_Name="Vic", Last_Name="Tim", Active="TRUE", Primary_Verified="TRUE")],
        )
        staged = batch.rows.get()
        items = {item["code"]: item for item in staged.risky[str(squatter.pk)]}
        self.assertEqual((items["R7"]["enabled"], items["R7"]["reason"]), (False, PENDING))
        self.assertEqual((items["R9"]["enabled"], items["R9"]["reason"]), (False, PENDING))

        review = reverse("admin:authn_member_import_review", args=[batch.pk])
        self.client.post(review, {"version": 0, "ready-2": "update", "action": "tickall:R7"})
        self.client.post(
            review, {"version": 0, "ready-2": "update", "ticks-2": "1", "tick-2": items["R9"]["id"], "action": "save"}
        )
        staged.refresh_from_db()
        self.assertEqual(staged.ticks, [])
        self.confirm_as(self.master, batch)

        squatter.refresh_from_db()
        self.assertEqual((squatter.is_active, squatter.registration_pending), (False, True))
        self.assertFalse(ContactEmail.objects.get(email_address="vic@example.com").verified)


class RetentionTests(_FlowCase):
    def test_the_purge_blanks_everything_that_names_a_person(self):
        batch = self.upload_as(self.master, [row("ada@example.com", Organization="Acme")])
        self.confirm_as(self.master, batch)
        batch.refresh_from_db()
        MemberImportBatch.objects.filter(pk=batch.pk).update(last_error="Row 2: ada@example.com")
        self.assertTrue(batch.rows.get().outcome_detail)

        purge_member_imports(now=batch.applied_at + timedelta(days=settings.MEMBER_IMPORT["values_retention_days"] + 1))

        batch.refresh_from_db()
        staged = batch.rows.get()
        self.assertEqual((staged.values, staged.candidates, staged.analysis, staged.outcome_detail), ({}, {}, {}, ""))
        self.assertEqual((staged.outcome, staged.choice), ("updated", "update"))
        self.assertEqual((batch.last_error, batch.file_warnings), ("", []))
        self.assertTrue(all("detail" not in event for event in batch.activity))
        self.assertIsNotNone(batch.values_purged_at)
        page = self.client.get(reverse("admin:authn_member_import_result", args=[batch.pk]))
        self.assertContains(page, "were removed on")

    def test_an_unapplied_batch_is_gone_after_its_lifetime(self):
        batch = self.upload_as(self.master, [row("ada@example.com", Organization="Acme")])

        purge_member_imports(now=timezone.now() + timedelta(hours=settings.MEMBER_IMPORT["batch_lifetime_hours"]))

        self.assertFalse(MemberImportBatch.objects.filter(pk=batch.pk).exists())


class UploadLimitTests(ImportTestCase):
    def test_reading_stops_once_the_row_read_cap_is_passed(self):
        rows = [row(f"p{i}@example.com") for i in range(3)] + [[None] * len(HEADERS)] * 5
        read = read_upload(BytesIO(workbook_bytes(HEADERS, rows)), max_rows=100, max_rows_read=5)

        self.assertEqual(read.rows, [])
        self.assertIn("The sheet has more than 5 rows, counting blank ones.", read.error)

    def test_an_over_long_name_cannot_be_imported(self):
        analysis = self.analyse_one(row("new@example.com", First_Name="A" * 151, Last_Name="Long"))

        self.assertEqual(analysis.status, "invalid")
        self.assertEqual(analysis.facts["invalid"], "First Name is longer than 150 characters")

    def test_the_import_without_a_review_skips_staff_accounts_unless_the_caller_is_a_master(self):
        staff = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        sheet = workbook_bytes(HEADERS, [row("sam@example.com", First_Name="Sam", Last_Name="Staff", Organization="X")])

        refused = import_members_from_excel(BytesIO(sheet), update_existing=True)
        staff.refresh_from_db()
        self.assertEqual((refused.updated_count, refused.skipped_count, staff.organization), (0, 1, None))

        allowed = import_members_from_excel(BytesIO(sheet), update_existing=True, allow_privilege_fields=True)
        staff.refresh_from_db()
        self.assertEqual((allowed.updated_count, staff.organization), (1, "X"))
