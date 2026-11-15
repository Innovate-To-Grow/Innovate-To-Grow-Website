"""Members → Import pages and the Phone Verified column (decided on 2026-11-12, #726).

The column is accepted and ignored: the upload page says so, the review lists it as "Not imported" with a note, and the
confirm and result pages repeat the note. No row offers to verify or un-verify a number, a forged tick for one is
refused, and every number the import writes is unverified while stored numbers keep their status.
"""

from django.contrib.messages import get_messages
from django.test import override_settings
from django.urls import reverse

from apps.authn.admin.members.import_context import review_sections
from apps.authn.models import ContactPhone, Member, MemberImportBatch
from apps.authn.services.members.import_.parsing import PHONE_VERIFIED_IGNORED
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row, upload


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class PhoneVerifiedPagesTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.master = Member.objects.create_superuser(password="StrongPass123!", first_name="I2G", last_name="Master")
        self.client.force_login(self.master)
        self.verified = self.phone(self.ada, "2095550101", verified=True)
        self.unverified = self.phone(self.ada, "2095550102", verified=False)

    def _stage(self, rows, headers=HEADERS):
        response = self.client.post(
            reverse("admin:authn_member_import_excel"),
            {"excel_file": upload(headers, rows), "mode": "update_existing", "upload_anyway": "on"},
        )
        self.assertEqual(response.status_code, 302)
        return MemberImportBatch.objects.order_by("-created_at").first()

    def _confirm(self, batch):
        batch.refresh_from_db()
        return self.client.post(
            reverse("admin:authn_member_import_confirm", args=[batch.pk]),
            {"confirmation_text": "import", "version": batch.choices_version},
        )

    def _rows(self):
        return [
            row("ada@example.com", Phone_Number="2095550101", Phone_Verified="FALSE"),
            row(
                "nina@example.com", First_Name="Nina", Last_Name="New", Phone_Number="2095550177", Phone_Verified="TRUE"
            ),
        ]

    def test_the_upload_page_says_the_column_is_ignored(self):
        response = self.client.get(reverse("admin:authn_member_import_excel"))

        self.assertContains(response, "<strong>Phone Verified</strong> is ignored: imported phone numbers are saved")
        self.assertContains(response, "verifying or un-verifying an email address")

    def test_review_confirm_and_result_pages_show_the_note_and_numbers_stay_as_they_were(self):
        batch = self._stage(self._rows())

        self.assertEqual(batch.columns["notes"], [PHONE_VERIFIED_IGNORED])
        self.assertIn("Phone Verified", batch.columns["informational"])
        review = self.client.get(reverse("admin:authn_member_import_review", args=[batch.pk]))
        self.assertContains(review, PHONE_VERIFIED_IGNORED, count=1)
        self.assertContains(review, "Not imported: Phone Verified.")
        confirm = self.client.get(reverse("admin:authn_member_import_confirm", args=[batch.pk]))
        self.assertContains(confirm, PHONE_VERIFIED_IGNORED, count=1)

        response = self._confirm(batch)

        self.assertRedirects(response, reverse("admin:authn_member_import_result", args=[batch.pk]))
        result = self.client.get(reverse("admin:authn_member_import_result", args=[batch.pk]))
        self.assertContains(result, PHONE_VERIFIED_IGNORED, count=1)
        self.assertEqual(
            sorted(ContactPhone.objects.values_list("phone_number", "verified")),
            [("2095550101", True), ("2095550102", False), ("2095550177", False)],
        )
        self.assertEqual(ContactPhone.objects.get(phone_number="2095550177").member.first_name, "Nina")

    def test_the_review_shows_no_phone_verified_cell_and_no_tick_for_a_number(self):
        batch = self._stage(self._rows())

        sections = review_sections(batch)

        labels = {cell["label"] for view in sections["ready"] + sections["no_change"] for cell in view["cells"]}
        self.assertIn("Phone Number", labels)
        self.assertNotIn("Phone Verified", labels)
        self.assertEqual(sections["counts"]["risky"], 0)
        self.assertEqual(sections["risky"], [])

    def test_a_posted_tick_to_verify_a_number_is_refused(self):
        batch = self._stage([row("ada@example.com", Phone_Number="2095550102", Phone_Verified="TRUE")])
        review = reverse("admin:authn_member_import_review", args=[batch.pk])

        response = self.client.post(
            review,
            {"version": 0, "ready-2": "update", "ticks-2": "1", "tick-2": f"R9:{self.unverified.pk}", "action": "save"},
        )

        self.assertRedirects(response, review)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(
            messages, [f"Nothing was saved: Row 2: 'R9:{self.unverified.pk}' is not one of this row's risky changes."]
        )
        staged = batch.rows.get()
        self.assertEqual(staged.ticks, [])
        self._confirm(batch)
        self.unverified.refresh_from_db()
        self.assertFalse(self.unverified.verified)

    def test_a_posted_tick_to_unverify_a_number_is_refused(self):
        batch = self._stage([row("ada@example.com", Phone_Number="2095550101", Phone_Verified="FALSE")])

        self.client.post(
            reverse("admin:authn_member_import_review", args=[batch.pk]),
            {"version": 0, "ready-2": "update", "ticks-2": "1", "tick-2": f"R6:{self.verified.pk}", "action": "save"},
        )

        self.assertEqual(batch.rows.get().ticks, [])
        self._confirm(batch)
        self.verified.refresh_from_db()
        self.assertTrue(self.verified.verified)

    def test_without_the_column_no_page_shows_the_note(self):
        headers = [header for header in HEADERS if header != "Phone Verified"]
        cells = row("nina@example.com", First_Name="Nina", Last_Name="New", Phone_Number="2095550177")
        batch = self._stage([[cells[HEADERS.index(header)] for header in headers]], headers)

        self.assertEqual(batch.columns["notes"], [])
        for name in ("review", "confirm"):
            page = self.client.get(reverse(f"admin:authn_member_import_{name}", args=[batch.pk]))
            self.assertNotContains(page, PHONE_VERIFIED_IGNORED)
        self._confirm(batch)
        result = self.client.get(reverse("admin:authn_member_import_result", args=[batch.pk]))
        self.assertNotContains(result, PHONE_VERIFIED_IGNORED)
        self.assertFalse(ContactPhone.objects.get(phone_number="2095550177").verified)
