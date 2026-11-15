from apps.authn.services.members.import_.review.analysis import SKIP_EXISTING
from apps.authn.services.members.import_.review.analysis.choices import NO_CHANGE_PERMISSION
from apps.authn.tests.services.members.import_.conflicts.test_conflicts_matched import UUID_HEADERS, options, uuid_row
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


class SkipModeTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.label = f"Ada Lovelace (member {self.ada.pk})"

    def test_an_existing_member_when_the_upload_said_to_skip_them(self):
        analysis = self.analyse_one(row("ada@example.com", Organization="Engines"), mode=SKIP_EXISTING)

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "exists_but_skip_mode", "skip")
        )
        self.assertEqual(list(options(analysis)), ["skip", "update"])
        self.assertEqual(
            options(analysis)["skip"]["hint"], "The upload said to skip rows that match an existing member."
        )
        update = options(analysis)["update"]
        self.assertEqual(
            (update["label"], update["enabled"], update["suggested"]), (f"Update {self.label} instead", True, False)
        )
        self.assertEqual(
            analysis.facts["why"],
            f"ada@example.com is the primary email of {self.label}, and the upload said to skip rows that match an "
            "existing member.",
        )

    def test_updating_instead_needs_permission(self):
        analysis = self.analyse_one(row("ada@example.com"), mode=SKIP_EXISTING, can_update=False)

        self.assertEqual(options(analysis)["update"]["reason"], NO_CHANGE_PERMISSION)

    def test_matched_by_member_uuid(self):
        analysis = self.analyse_one(uuid_row("ada@example.com", self.ada.pk), UUID_HEADERS, mode=SKIP_EXISTING)

        self.assertEqual(analysis.conflict, "exists_but_skip_mode")
        self.assertEqual(
            analysis.facts["why"],
            f"The Member UUID names {self.label}, and the upload said to skip rows that match an existing member.",
        )

    def test_new_members_are_still_ready_to_create(self):
        analysis = self.analyse_one(row("new@example.com"), mode=SKIP_EXISTING)

        self.assertEqual((analysis.status, analysis.default), ("ready_create", "create"))

    def test_skipped_by_default_or_updated_when_chosen(self):
        cells_row = row("ada@example.com", Organization="Engines")

        (skipped,) = self.apply([cells_row], mode=SKIP_EXISTING)
        self.ada.refresh_from_db()
        self.assertEqual((skipped.outcome, self.ada.organization), ("skipped", None))

        (updated,) = self.apply([cells_row], {2: ("update", [])}, mode=SKIP_EXISTING)
        self.ada.refresh_from_db()
        self.assertEqual((updated.outcome, self.ada.organization), ("updated", "Engines"))
