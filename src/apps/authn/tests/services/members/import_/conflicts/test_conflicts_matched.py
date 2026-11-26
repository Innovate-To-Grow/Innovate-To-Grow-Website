"""A row whose member was found, but which still needs a decision: C6 (name), C7 (Row 5), C8 (unlinked), C9 (mode).

Each conflict starts on "skip"; its options say what a choice would do, and are disabled (with the reason) when the
actor may not change that member. The apply tests check what each choice writes.
"""

from apps.authn.services.members.import_.review.analysis.choices import NO_CHANGE_PERMISSION
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row

UUID_HEADERS = [*HEADERS, "Member UUID"]
UNVERIFIED = (
    "Not verified. The member can verify it on /account, or an admin can mark it verified in Contact Emails first."
)


def uuid_row(primary, member_uuid, **cells):
    return [*row(primary, **cells), str(member_uuid) if member_uuid else None]


def options(analysis) -> dict:
    return {item["value"]: item for item in analysis.options}


def roles(member) -> dict:
    return dict(member.contact_emails.values_list("email_address", "email_type"))


class NameDiffersTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.label = f"Ada Lovelace (member {self.ada.pk})"
        self.renamed = row("ada@example.com", First_Name="Augusta", Last_Name="King", Organization="Engines")

    def test_found_by_email_with_another_name(self):
        analysis = self.analyse_one(self.renamed)

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "name_differs", "skip")
        )
        self.assertEqual((analysis.target, analysis.facts["matched_by"]), (str(self.ada.pk), "primary"))
        self.assertEqual(list(options(analysis)), ["update_same_person", "update_keep_name", "skip"])
        self.assertEqual(
            [item["label"] for item in analysis.options[:2]],
            [
                f"Same person: update {self.label}, including the name",
                f"Same person: update {self.label}, keep their name",
            ],
        )
        self.assertEqual(
            options(analysis)["skip"]["hint"], "Not the same person, or not sure. The address stays with the member."
        )
        self.assertTrue(all(item["enabled"] and not item["suggested"] for item in analysis.options))

    def test_updating_needs_permission(self):
        analysis = self.analyse_one(self.renamed, can_update=False)

        self.assertEqual(
            [item["reason"] for item in analysis.options], [NO_CHANGE_PERMISSION, NO_CHANGE_PERMISSION, ""]
        )

    def test_found_through_a_secondary_address(self):
        self.email(self.ada, "ada.work@example.com")

        analysis = self.analyse_one(row("ada.work@example.com", First_Name="Augusta", Last_Name="King"))

        self.assertEqual((analysis.conflict, analysis.facts["matched_by"]), ("name_differs", "secondary"))

    def test_same_person_including_the_name(self):
        (outcome,) = self.apply([self.renamed], {2: ("update_same_person", [])})

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.assertEqual(
            (self.ada.first_name, self.ada.last_name, self.ada.organization), ("Augusta", "King", "Engines")
        )

    def test_same_person_keeping_their_name(self):
        (outcome,) = self.apply([self.renamed], {2: ("update_keep_name", [])})

        self.ada.refresh_from_db()
        self.assertEqual(
            (self.ada.first_name, self.ada.last_name, self.ada.organization), ("Ada", "Lovelace", "Engines")
        )
        self.assertIn("The sheet's name is not applied; Ada Lovelace is kept", outcome.notes)

    def test_skipped_by_default(self):
        (outcome,) = self.apply([self.renamed])

        self.assertEqual(outcome.outcome, "skipped")
        self.ada.refresh_from_db()
        self.assertEqual((self.ada.first_name, self.ada.organization), ("Ada", None))
