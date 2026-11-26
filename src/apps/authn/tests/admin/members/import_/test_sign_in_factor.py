from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail, Member, MemberImportBatch
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.review import purge_member_imports
from apps.authn.services.members.import_.review.analysis.risky import PENDING
from apps.authn.services.members.import_.workbook.reader import read_upload
from apps.authn.tests.admin.members.import_.test_member_import_security import _FlowCase
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, workbook_bytes


class SignInFactorTests(_FlowCase):
    def test_marking_an_address_verified_needs_its_tick_and_is_listed_on_confirm(self):
        work = self.email(self.ada, "ada.work@example.com", verified=False)
        cells = {"Secondary_Email": "ada.work@example.com", "Secondary_Verified": "TRUE"}
        batch = self.upload_as(self.admin_user, [row("ada@example.com", **cells)])
        staged = batch.rows.get()
        r9 = next(item for item in staged.risky[str(self.ada.pk)] if item["code"] == "R9")
        self.assertTrue(r9["enabled"])

        self.confirm_as(self.admin_user, batch)
        work.refresh_from_db()
        self.assertFalse(work.verified)
        self.assertIn(
            "Secondary Verified is TRUE, but ada.work@example.com is unverified; left unverified",
            staged.__class__.objects.get(pk=staged.pk).outcome_detail,
        )

        again = self.upload_as(self.admin_user, [row("ada@example.com", **cells)])
        review = reverse("admin:authn_member_import_review", args=[again.pk])
        self.client.post(
            review, {"version": 0, "ready-2": "update", "ticks-2": "1", "tick-2": r9["id"], "action": "save"}
        )
        page = self.client.get(reverse("admin:authn_member_import_confirm", args=[again.pk]))
        self.assertContains(page, "Email addresses marked verified (each becomes a sign-in factor) (1)")

        self.confirm_as(self.admin_user, again)
        work.refresh_from_db()
        self.assertTrue(work.verified)

    def test_every_change_to_an_admin_account_is_listed_on_confirm(self):
        sam = self.member("Sam", "Admin", "sam@example.com", is_staff=True)
        batch = self.upload_as(
            self.admin_user, [row("sam@example.com", First_Name="Sam", Last_Name="Admin", Organization="New")]
        )

        page = self.client.get(reverse("admin:authn_member_import_confirm", args=[batch.pk]))

        self.assertContains(page, "Changes to Admin accounts (1)")
        self.assertContains(page, f"Sam Admin (member {sam.pk}): Organization")

    def test_an_unfinished_sign_up_cannot_be_activated_or_verified(self):
        squatter = self.member("Vic", "Tim", "vic@example.com", verified=False)
        Member.objects.filter(pk=squatter.pk).update(is_active=False, registration_pending=True)
        batch = self.upload_as(
            self.admin_user,
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
        self.confirm_as(self.admin_user, batch)

        squatter.refresh_from_db()
        self.assertEqual((squatter.is_active, squatter.registration_pending), (False, True))
        self.assertFalse(ContactEmail.objects.get(email_address="vic@example.com").verified)


class RetentionTests(_FlowCase):
    def test_the_purge_blanks_everything_that_names_a_person(self):
        batch = self.upload_as(self.admin_user, [row("ada@example.com", Organization="Acme")])
        self.confirm_as(self.admin_user, batch)
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
        batch = self.upload_as(self.admin_user, [row("ada@example.com", Organization="Acme")])

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

    def test_the_import_without_a_review_updates_an_admin_but_never_their_admin_access(self):
        sam = self.member("Sam", "Admin", "sam@example.com", is_staff=True)
        cells = {"First_Name": "Sam", "Last_Name": "Admin", "Organization": "X", "Staff": "No", "Active": "No"}
        sheet = workbook_bytes(HEADERS, [row("sam@example.com", **cells)])

        result = import_members_from_excel(BytesIO(sheet), update_existing=True)

        sam.refresh_from_db()
        self.assertEqual((result.updated_count, sam.organization), (1, "X"))
        self.assertEqual((sam.is_staff, sam.is_superuser, sam.is_active), (True, True, True))
