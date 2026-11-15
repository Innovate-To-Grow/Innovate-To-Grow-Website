from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactPhone
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.review.lookup import load_snapshot
from apps.authn.tests.services.members.excel_import.test_import_members_messages import HEADERS, _member

from ..import_sheets import build_sheet


class EdgeCaseTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_over_long_addresses_are_refused_before_they_reach_the_database(self):
        """PostgreSQL rejects an address over the column limit, which would roll back every creation."""
        long_address = f"{'a' * 250}@example.com"

        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    [long_address, "Ada", "Lovelace", None, None, None],
                    ["grace@example.com", "Grace", "Hopper", long_address, None, None],
                ],
            )
        )

        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.errors, [f"Row 2: Primary Email {long_address!r} is not a valid email address"])
        self.assertEqual(
            result.warnings, [f"Row 3: Secondary Email {long_address!r} is not a valid email address; ignored"]
        )

    def test_phone_cell_that_is_not_a_us_number_is_ignored(self):
        neil = _member("Neil", "Parkhi", "neil@home.example")

        result = import_members_from_excel(
            build_sheet(
                HEADERS,
                [
                    ["ada@example.com", "Ada", "Lovelace", None, "+1", None],
                    ["neil@home.example", "Neil", "Parkhi", None, "+44 20 7946 0958", None],
                ],
            ),
            update_existing=True,
        )

        self.assertEqual((result.created_count, result.updated_count, result.unchanged_count), (1, 1, 1))
        self.assertFalse(ContactPhone.objects.exists())
        self.assertEqual(
            result.warnings,
            [
                "Row 2: Phone Number +1 is not a 10-digit US number; ignored",
                "Row 3: Phone Number +442079460958 is not a 10-digit US number; ignored",
            ],
        )
        self.assertEqual(result.warnings[1].member_id, str(neil.pk))

    def test_lookups_of_nothing_query_nothing(self):
        with self.assertNumQueries(0):
            snapshot = load_snapshot([{"primary_email": None, "secondary_email": "", "phone_number": None}])
        self.assertEqual((snapshot.emails, snapshot.phones, snapshot.members), ({}, {}, {}))
