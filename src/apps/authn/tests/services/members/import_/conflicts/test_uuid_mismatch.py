import uuid

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.analysis import SKIP_EXISTING
from apps.authn.services.members.import_.review.analysis.choices import PRIVILEGED
from apps.authn.tests.services.members.import_.conflicts.test_conflicts import (
    NAME_DIFFERS,
    SKIP_MODE,
    UUID_HEADERS,
    not_privileged,
    options,
    uuid_row,
)
from apps.authn.tests.services.members.import_.helpers import ImportTestCase


class UuidMismatchTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.grace = self.member("Grace", "Hopper", "grace@example.com")

    def test_the_member_uuid_and_the_primary_email_name_different_members(self):
        analysis = self.analyse_one(uuid_row("grace@example.com", self.ada.pk), UUID_HEADERS)

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "uuid_email_mismatch", "skip")
        )
        self.assertEqual(
            (analysis.facts["uuid_member"], analysis.facts["email_member"]), (str(self.ada.pk), str(self.grace.pk))
        )
        self.assertIsNone(analysis.target)
        self.assertEqual(list(options(analysis)), [f"use_member:{self.ada.pk}", f"use_member:{self.grace.pk}", "skip"])
        self.assertEqual(
            [item["label"] for item in analysis.options[:2]],
            [
                f"Use Ada Lovelace (member {self.ada.pk}) (by Member UUID); don't give them the address",
                f"Use Grace Hopper (member {self.grace.pk}) (by email)",
            ],
        )
        self.assertTrue(all(item["enabled"] for item in analysis.options))
        self.assertEqual(
            analysis.facts["why"],
            f"The Member UUID names Ada Lovelace (member {self.ada.pk}), but grace@example.com is the primary email of "
            f"Grace Hopper (member {self.grace.pk}).",
        )

    def test_the_address_may_have_any_role(self):
        self.email(self.grace, "grace.work@example.com")

        analysis = self.analyse_one(uuid_row("grace.work@example.com", self.ada.pk), UUID_HEADERS)

        self.assertEqual(analysis.conflict, "uuid_email_mismatch")
        self.assertIn("the secondary email of Grace Hopper", analysis.facts["why"])

    def test_each_member_is_offered_only_with_permission(self):
        sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)

        analysis = self.analyse_one(uuid_row("sam@example.com", self.ada.pk), UUID_HEADERS, can_manage=not_privileged)

        self.assertEqual(options(analysis)[f"use_member:{sam.pk}"]["reason"], PRIVILEGED)
        self.assertTrue(options(analysis)[f"use_member:{self.ada.pk}"]["enabled"])

    def test_using_the_uuid_member_never_gives_them_the_address(self):
        cells_row = uuid_row("grace@example.com", self.ada.pk, Organization="Engines", Primary_Verified="TRUE")

        (outcome,) = self.apply([cells_row], {2: (f"use_member:{self.ada.pk}", [])}, UUID_HEADERS)

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Engines")
        self.assertEqual(ContactEmail.objects.get(email_address="grace@example.com").member, self.grace)
        self.assertIn(
            f"Primary Email grace@example.com belongs to Grace Hopper (member {self.grace.pk}); it is not added to Ada "
            f"Lovelace (member {self.ada.pk}), and its Verified/Subscribed cells are ignored",
            outcome.notes,
        )


class UuidNotFoundTests(ImportTestCase):
    def test_a_member_uuid_that_matches_nobody(self):
        unknown = uuid.uuid4()

        analysis = self.analyse_one(uuid_row("ada@example.com", unknown, Organization="X"), UUID_HEADERS)

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "uuid_not_found", "skip")
        )
        self.assertEqual(list(options(analysis)), ["ignore_uuid", "skip"])
        ignore = options(analysis)["ignore_uuid"]
        self.assertTrue(ignore["enabled"])
        self.assertEqual(ignore["hint"], f"The row would update Ada Lovelace (member {self.ada.pk})")
        self.assertEqual(
            (analysis.facts["fallback"]["kind"], analysis.facts["fallback"]["target"]), ("update", str(self.ada.pk))
        )
        self.assertEqual(
            analysis.facts["why"],
            f"No member has the Member UUID {unknown}: it may be a deleted member, a typo, or a sheet exported from "
            "another site (such as staging).",
        )

    def test_matched_by_email_the_row_would_create_a_member(self):
        analysis = self.analyse_one(uuid_row("ghost@example.com", uuid.uuid4()), UUID_HEADERS)

        self.assertEqual(
            options(analysis)["ignore_uuid"]["hint"], "The row would create a new member with ghost@example.com"
        )

    def test_ignoring_the_uuid_is_disabled_when_the_email_match_would_be_skipped(self):
        cases = [
            (uuid_row("ada@example.com", uuid.uuid4(), First_Name="Grace", Last_Name="Hopper"), {}, NAME_DIFFERS),
            (uuid_row("ghost@example.com", uuid.uuid4(), Last_Name=None), {}, "Missing last name"),
            (uuid_row("ada@example.com", uuid.uuid4()), {"mode": SKIP_EXISTING}, SKIP_MODE),
        ]
        for cells_row, context, reason in cases:
            with self.subTest(reason=reason):
                analysis = self.analyse_one(cells_row, UUID_HEADERS, **context)
                self.assertEqual(analysis.conflict, "uuid_not_found")
                self.assertEqual(
                    (options(analysis)["ignore_uuid"]["enabled"], options(analysis)["ignore_uuid"]["reason"]),
                    (False, reason),
                )

    def test_text_that_is_not_a_uuid(self):
        analysis = self.analyse_one(uuid_row("ada@example.com", "abc-123"), UUID_HEADERS)

        self.assertEqual(analysis.conflict, "uuid_not_found")
        self.assertEqual(analysis.facts["why"], "The Member UUID cell 'abc-123' is not a UUID.")

    def test_ignoring_the_uuid_applies_the_email_match(self):
        cells_row = uuid_row("ada@example.com", uuid.uuid4(), Organization="Engines")

        (outcome,) = self.apply([cells_row], {2: ("ignore_uuid", [])}, UUID_HEADERS)

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Engines")

    def test_a_member_uuid_match_skips_the_name_check(self):
        analysis = self.analyse_one(
            uuid_row("ada@example.com", self.ada.pk, First_Name="Augusta", Last_Name="King"), UUID_HEADERS
        )

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.facts["matched_by"]), ("ready_update", "", "uuid")
        )
