"""Which member a row is about: the conflicts C1 and C3–C5 (C2 is retired), the precedence of all conflicts, and their
default (Skip). An Admin account is matched like any other member.

Every row that needs a decision starts on "skip"; the choice the import plan suggests is only marked. A choice that is
not allowed stays listed, disabled, with the reason.
"""

import uuid

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.analysis import SKIP_EXISTING
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row

UUID_HEADERS = [*HEADERS, "Member UUID"]
NAME_DIFFERS = "The sheet's name differs from the member's; decide on this row alone"
SKIP_MODE = "The upload said to skip rows that match an existing member"


def uuid_row(primary, member_uuid, **cells):
    """A ``UUID_HEADERS`` row: ``row(primary, **cells)`` and its Member UUID cell."""
    return [*row(primary, **cells), str(member_uuid) if member_uuid else None]


def options(analysis) -> dict:
    return {item["value"]: item for item in analysis.options}


class ConflictCatalogueTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.grace = self.member("Grace", "Hopper", "grace@example.com")
        self.bob = self.member("Bob", "Babbage", "bob@example.com")
        self.sam = self.member("Sam", "Admin", "sam@example.com", is_staff=True)
        self.email(self.bob, "bob.work@example.com", verified=True)
        self.email(self.grace, "shared@example.com", "other")
        ContactEmail.objects.create(member=None, email_address="SHARED@example.com")
        self.loose = ContactEmail.objects.create(member=None, email_address="loose@example.com")

    def test_each_conflict_is_detected_and_every_one_starts_on_skip(self):
        rows = [
            uuid_row("twin@example.com", None),
            uuid_row("twin@example.com", None, Organization="Twin Corp"),
            uuid_row("sam@example.com", None, First_Name="Sam", Last_Name="Admin"),
            uuid_row("shared@example.com", None),
            uuid_row("bob@example.com", self.ada.pk, First_Name="Bob", Last_Name="Babbage"),
            uuid_row("ghost@example.com", uuid.uuid4()),
            uuid_row("grace@example.com", None, First_Name="Someone", Last_Name="Else"),
            uuid_row("bob.work@example.com", None, First_Name="Bob", Last_Name="Babbage"),
            uuid_row("loose@example.com", None, First_Name="Lin", Last_Name="Loose"),
            uuid_row("ada@example.com", None),
        ]

        analyses = self.analyse(rows, UUID_HEADERS, mode=SKIP_EXISTING)

        self.assertEqual(
            {a.row_number: a.conflict for a in analyses},
            {
                2: "duplicate_in_sheet",
                3: "duplicate_in_sheet",
                4: "exists_but_skip_mode",  # an Admin account, matched like any other member
                5: "ambiguous_address",
                6: "uuid_email_mismatch",
                7: "uuid_not_found",
                8: "name_differs",
                9: "address_not_primary",
                10: "unlinked_address",
                11: "exists_but_skip_mode",
            },
        )
        self.assertEqual({a.status for a in analyses}, {"needs_decision"})
        self.assertEqual({a.default for a in analyses}, {"skip"})
        for analysis in analyses:
            with self.subTest(row=analysis.row_number):
                self.assertTrue(options(analysis)["skip"]["enabled"])
        suggested = {(a.row_number, o["value"]) for a in analyses for o in a.options if o["suggested"]}
        self.assertEqual(suggested, {(9, "update"), (10, f"create_claim:{self.loose.pk}")})

    def test_ready_rows_default_to_their_action(self):
        analyses = self.analyse([row("new@example.com"), row("ada@example.com", Organization="Engines")])

        self.assertEqual(
            [(a.status, a.default) for a in analyses], [("ready_create", "create"), ("ready_update", "update")]
        )
        self.assertEqual([list(options(a)) for a in analyses], [["create", "skip"], ["update", "skip"]])
        self.assertEqual(analyses[1].options[0]["label"], f"Update Ada Lovelace (member {self.ada.pk})")
        self.assertEqual(analyses[1].facts["matched_by"], "primary")
