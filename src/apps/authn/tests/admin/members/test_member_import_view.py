"""The Members -> Import admin page reports why rows were skipped and links each line to its member."""

from django.contrib import messages as message_levels
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.authn.admin.members.forms import MemberImportForm
from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_.parsing import PHONE_VERIFIED_IGNORED
from apps.authn.tests.services.members.import_sheets import build_sheet

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADERS = ["Primary Email", "First Name", "Last Name", "Phone Number"]


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

    def test_get_explains_that_updates_never_delete(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Updates never delete anything:")
        self.assertContains(response, "Nothing is deleted: blank cells keep the stored values.")

    def test_skipped_rows_and_notes_are_listed_with_a_link_to_the_member(self):
        response = self.client.post(
            self.url,
            {
                "excel_file": _upload(
                    [
                        ["neil@work.example", "Neil", "Parkhi", None],
                        ["neil@home.example", "Neil", "Parkhi", "+12095550002"],
                    ]
                ),
                "update_existing": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        change_url = reverse("admin:authn_member_change", args=[self.neil.pk])
        self.assertContains(response, "Not imported, and why")
        self.assertContains(response, "Row 2: no member has neil@work.example as their primary email")
        self.assertContains(response, "Imported, with notes")
        self.assertContains(response, "Row 3: Added +12095550002 as an additional phone number; kept +12095550001")
        self.assertContains(response, f'href="{change_url}"', count=2)
        self.assertEqual(
            [str(message) for message in get_messages(response.wsgi_request)],
            ["Import complete: 0 created, 1 updated, 1 skipped, 1 error(s), 1 note(s)"],
        )
        self.assertTrue(ContactPhone.objects.filter(member=self.neil, phone_number="2095550001").exists())
        self.assertTrue(ContactEmail.objects.filter(member=self.neil, email_address="neil@work.example").exists())

    def test_clean_import_is_reported_as_a_success(self):
        response = self.client.post(self.url, {"excel_file": _upload([["new@example.com", "New", "Person", None]])})

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual([str(message) for message in messages], ["Import complete: 1 created, 0 updated, 0 skipped"])
        self.assertEqual(messages[0].level, message_levels.SUCCESS)
        self.assertNotContains(response, "Not imported, and why")
        self.assertNotContains(response, PHONE_VERIFIED_IGNORED)


class MemberImportPhoneVerifiedPageTests(TestCase):
    """The page says, before and after an upload, that the Phone Verified column is ignored."""

    def setUp(self):
        cache.clear()
        self.admin = Member.objects.create_superuser(
            password="StrongPass123!", first_name="I2G", last_name="Master", is_active=True
        )
        self.client.force_login(self.admin)
        self.url = reverse("admin:authn_member_import_excel")

    def tearDown(self):
        cache.clear()

    def test_the_upload_page_lists_phone_verified_as_ignored(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Phone Verified</code> <span")
        self.assertContains(response, "(ignored)")
        self.assertContains(response, "<strong>Phone Verified</strong> is ignored: imported phone numbers are saved")

    def test_a_sheet_with_the_column_is_imported_with_one_note_and_unverified_numbers(self):
        headers = ["Primary Email", "First Name", "Last Name", "Phone Number", "Phone Verified"]
        rows = [
            ["ada@example.com", "Ada", "Lovelace", "+12095550001", "TRUE"],
            ["bob@example.com", "Bob", "Ross", "+12095550002", "Yes"],
        ]
        upload = SimpleUploadedFile("members.xlsx", build_sheet(headers, rows).getvalue(), content_type=XLSX)

        response = self.client.post(self.url, {"excel_file": upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Imported, with notes")
        self.assertContains(response, PHONE_VERIFIED_IGNORED, count=1)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(
            [str(message) for message in messages], ["Import complete: 2 created, 0 updated, 0 skipped, 1 note(s)"]
        )
        self.assertEqual(messages[0].level, message_levels.WARNING)
        self.assertEqual(ContactPhone.objects.count(), 2)
        self.assertFalse(ContactPhone.objects.filter(verified=True).exists())


class MemberImportFormFileTypeTests(TestCase):
    def _form(self, name):
        upload = SimpleUploadedFile(name, build_sheet(HEADERS, []).getvalue(), content_type=XLSX)
        return MemberImportForm(data={}, files={"excel_file": upload})

    def test_old_xls_workbooks_are_refused_up_front(self):
        form = self._form("members.xls")

        self.assertFalse(form.is_valid())
        self.assertIn("Older .xls workbooks can't be read", form.errors["excel_file"][0])

    def test_xlsx_extension_is_matched_in_any_letter_case(self):
        self.assertTrue(self._form("MEMBERS.XLSX").is_valid())
