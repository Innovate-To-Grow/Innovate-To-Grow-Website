from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.tests.services.members.excel_import.test_import_members_messages import C7, HEADERS, _member

from ..import_sheets import build_sheet


class CreateOnlySkipReasonTests(TestCase):
    def setUp(self):
        cache.clear()
        self.neil = _member("Neil", "Parkhi", "neil@home.example")

    def _import(self, address):
        return import_members_from_excel(build_sheet(HEADERS, [[address, "Neil", "Parkhi", None, None, None]]))

    def test_existing_primary(self):
        result = self._import("NEIL@home.example")

        self.assertEqual(
            result.errors,
            [
                "Row 2: needs a decision (C9: Matches an existing member, and the upload said to skip those). "
                f"NEIL@home.example is the primary email of Neil Parkhi (member {self.neil.pk}), and the upload said "
                "to skip rows that match an existing member."
            ],
        )
        self.assertEqual(result.errors[0].member_id, str(self.neil.pk))

    def test_existing_secondary(self):
        ContactEmail.objects.create(member=self.neil, email_address="work@example.com", email_type="secondary")

        result = self._import("work@example.com")

        self.assertIn(
            f"{C7}. work@example.com is the secondary email of Neil Parkhi (member {self.neil.pk}), whose primary "
            "email is neil@home.example.",
            result.errors[0],
        )

    def test_existing_unlinked(self):
        ContactEmail.objects.create(member=None, email_address="orphan@example.com")

        result = self._import("orphan@example.com")

        self.assertIn("orphan@example.com is a contact email with no member", result.errors[0])

    def test_existing_case_only_duplicates(self):
        ContactEmail.objects.create(member=None, email_address="Twin@example.com")
        ContactEmail.objects.create(member=None, email_address="twin@example.com")

        result = self._import("twin@example.com")

        self.assertIn("twin@example.com matches 2 contact emails that differ only in letter case", result.errors[0])
