"""Members → Import, step 1: the upload page stages a review and writes no member data."""

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.admin.members.import_forms import MemberImportForm
from apps.authn.models import ContactEmail, ContactPhone, Member, MemberImportBatch
from apps.authn.tests.services.members.import_sheets import build_sheet

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADERS = ["Primary Email", "First Name", "Last Name", "Phone Number"]
# A test value only (low entropy on purpose, so secret scanners don't flag it).
SHEET_DEFAULT = "sheet" * 3


def _upload(rows, name="members.xlsx"):
    return SimpleUploadedFile(name, build_sheet(HEADERS, rows).getvalue(), content_type=XLSX)


class MemberImportPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = Member.objects.create_superuser(
            password="StrongPass123!", first_name="I2G", last_name="Master", is_active=True
        )
        self.client.force_login(self.admin)
        self.neil = Member.objects.create_user(
            password="StrongPass123!", first_name="Neil", last_name="Parkhi", is_active=True
        )
        ContactEmail.objects.create(member=self.neil, email_address="neil@home.example", email_type="primary")
        ContactEmail.objects.create(member=self.neil, email_address="neil@work.example", email_type="secondary")
        ContactPhone.objects.create(member=self.neil, phone_number="2095550001", region="1-US", verified=True)
        self.url = reverse("admin:authn_member_import_excel")

    def tearDown(self):
        cache.clear()

    def test_get_explains_the_review_step(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How an import works")
        self.assertContains(response, "Review import")
        self.assertContains(response, "A blank cell, or a missing column, keeps the stored value.")
        self.assertContains(response, "Rows that match an existing member")

    def test_upload_stages_a_batch_and_writes_no_member_data(self):
        before = (Member.objects.count(), ContactEmail.objects.count(), ContactPhone.objects.count())

        response = self.client.post(
            self.url,
            {
                "excel_file": _upload(
                    [
                        ["neil@work.example", "Neil", "Parkhi", None],
                        ["neil@home.example", "Neil", "Parkhi", "+12095550002"],
                        ["new@example.com", "New", "Person", None],
                    ]
                ),
                "mode": "update_existing",
                "set_password": SHEET_DEFAULT,
            },
        )

        batch = MemberImportBatch.objects.get()
        self.assertRedirects(response, reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.assertEqual((Member.objects.count(), ContactEmail.objects.count(), ContactPhone.objects.count()), before)
        self.assertEqual(
            (batch.created_by, batch.status, batch.row_count, batch.sheet_name), (self.admin, "review", 3, "Sheet")
        )
        self.assertTrue(batch.default_password_hash.startswith(("pbkdf2", "argon2", "md5", "bcrypt")))
        self.assertNotIn(SHEET_DEFAULT, batch.default_password_hash)
        statuses = dict(batch.rows.values_list("row_number", "status"))
        self.assertEqual(statuses, {2: "needs_decision", 3: "needs_decision", 4: "ready_create"})

    def test_the_review_lists_the_staged_rows(self):
        self.client.post(
            self.url, {"excel_file": _upload([["new@example.com", "New", "Person", None]]), "mode": "update_existing"}
        )
        batch = MemberImportBatch.objects.get()

        response = self.client.get(reverse("admin:authn_member_import_review", args=[batch.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 row(s) will be created or updated unless you tick Skip")
        self.assertContains(response, "Creates the member New Person")

    def test_a_sheet_without_member_rows_is_reported_on_the_form(self):
        response = self.client.post(self.url, {"excel_file": _upload([]), "mode": "update_existing"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The sheet has no member rows below its header row.")
        self.assertFalse(MemberImportBatch.objects.exists())

    def test_an_unreadable_file_is_reported_on_the_form(self):
        bad = SimpleUploadedFile("members.xlsx", b"not a workbook", content_type=XLSX)

        response = self.client.post(self.url, {"excel_file": bad, "mode": "update_existing"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The file could not be read as an .xlsx workbook")
        self.assertFalse(MemberImportBatch.objects.exists())

    @override_settings(MEMBER_IMPORT={**settings.MEMBER_IMPORT, "max_rows": 2})
    def test_a_sheet_over_the_row_cap_is_refused(self):
        rows = [[f"p{i}@example.com", "P", f"Person{i}", None] for i in range(3)]

        response = self.client.post(self.url, {"excel_file": _upload(rows), "mode": "update_existing"})

        self.assertContains(response, "The sheet has more than 2 member rows; one import takes at most 2.")
        self.assertFalse(MemberImportBatch.objects.exists())

    def test_the_same_file_twice_warns_before_a_second_batch_is_made(self):
        rows = [["new@example.com", "New", "Person", None]]
        # Reuse the exact bytes: separately saved workbooks can have different timestamps.
        content = build_sheet(HEADERS, rows).getvalue()
        uploads = [SimpleUploadedFile("members.xlsx", content, content_type=XLSX) for _ in range(3)]
        self.client.post(self.url, {"excel_file": uploads[0], "mode": "update_existing"})

        response = self.client.post(self.url, {"excel_file": uploads[1], "mode": "update_existing"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This file was uploaded before:")
        self.assertContains(response, "continue that one")
        self.assertEqual(MemberImportBatch.objects.count(), 1)
        again = self.client.post(self.url, {"excel_file": uploads[2], "mode": "update_existing", "upload_anyway": "on"})
        self.assertEqual(again.status_code, 302)
        self.assertEqual(MemberImportBatch.objects.count(), 2)

    def test_an_expired_unapplied_batch_is_purged_on_the_next_visit(self):
        self.client.post(
            self.url, {"excel_file": _upload([["new@example.com", "New", "Person", None]]), "mode": "update_existing"}
        )
        MemberImportBatch.objects.update(expires_at=timezone.now())

        self.client.get(self.url)

        self.assertFalse(MemberImportBatch.objects.exists())

    def test_imports_in_review_are_listed_with_resume_and_discard(self):
        self.client.post(
            self.url, {"excel_file": _upload([["new@example.com", "New", "Person", None]]), "mode": "update_existing"}
        )
        batch = MemberImportBatch.objects.get()

        response = self.client.get(self.url)

        self.assertContains(response, "Imports in review")
        self.assertContains(response, reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.assertContains(response, reverse("admin:authn_member_import_discard", args=[batch.pk]))


class MemberImportFormFileTypeTests(TestCase):
    def _form(self, name, **data):
        upload = SimpleUploadedFile(name, build_sheet(HEADERS, []).getvalue(), content_type=XLSX)
        return MemberImportForm(data={"mode": "update_existing", **data}, files={"excel_file": upload})

    def test_old_xls_workbooks_are_refused_up_front(self):
        form = self._form("members.xls")

        self.assertFalse(form.is_valid())
        self.assertIn("Older .xls workbooks can't be read", form.errors["excel_file"][0])

    def test_xlsx_extension_is_matched_in_any_letter_case(self):
        self.assertTrue(self._form("MEMBERS.XLSX").is_valid())

    def test_update_mode_needs_change_permission(self):
        upload = SimpleUploadedFile("m.xlsx", build_sheet(HEADERS, []).getvalue(), content_type=XLSX)
        form = MemberImportForm(data={"mode": "update_existing"}, files={"excel_file": upload}, can_update=False)

        self.assertFalse(form.is_valid())
        self.assertIn("You do not have permission to update existing members.", form.errors["mode"])
