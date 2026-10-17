import importlib
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.projects.models import PastProjectShare

migration = importlib.import_module("apps.projects.migrations.0010_rename_auto_named_past_project_shares")

AFTER_AUTO_NAMING = datetime(2026, 10, 16, 23, 18, tzinfo=UTC)
# Names were still required (typed) until PR #335 merged on 2026-06-19 22:48:45 UTC.
BEFORE_AUTO_NAMING = datetime(2026, 6, 19, 12, tzinfo=UTC)
# created_at and updated_at differ by microseconds on a share nobody edited after creating it.
UNEDITED = AFTER_AUTO_NAMING + timedelta(microseconds=40)
EDITED = AFTER_AUTO_NAMING + timedelta(days=2)
PROJECT_SUMMARY_BLOCK = (
    '<div data-past-project-note-curation="project-summary"><div data-past-project-key="k1">'
    "<div><strong>Project 1</strong></div><div><strong>Year-Semester:</strong> 2026 Spring</div></div></div>"
)
# The same details after "Clear formatting": plain text lines ending in <br>.
FLATTENED_DETAILS = "Project 1<br>Year-Semester: 2026 Spring<br>Project Title: Alpha Project<br>"


def _rows(*titles):
    return [{"project_title": title, "team_number": str(index)} for index, title in enumerate(titles)]


def renamed_share_name(name, note, rows, created_at=AFTER_AUTO_NAMING, updated_at=EDITED):
    return migration.renamed_share_name(name, note, rows, created_at, updated_at)


class RenamedShareNameTests(SimpleTestCase):
    def test_renames_a_share_named_after_its_first_project(self):
        # The reported share: blank name and note, 14 rows, named after rows[0].
        rows = _rows("Upgrading Advanced Image Analysis Platform", *[f"Project {n}" for n in range(13)])
        for updated_at in (UNEDITED, EDITED):
            with self.subTest(updated_at=updated_at):
                self.assertEqual(
                    renamed_share_name("Upgrading Advanced Image Analysis Platform", "", rows, updated_at=updated_at),
                    "Past Project Curation",
                )

    def test_renames_a_name_built_from_inserted_project_details(self):
        note = "<div>Hi Bob,</div><br><br>" + PROJECT_SUMMARY_BLOCK
        old_name = migration.old_default_name(note, _rows("A", "B"))
        self.assertTrue(old_name.startswith("Hi Bob, Project 1"))
        self.assertEqual(renamed_share_name(old_name, note, _rows("A", "B")), "Hi Bob,")

    def test_renames_a_name_built_from_details_whose_formatting_was_cleared(self):
        for note, new_name in [
            (FLATTENED_DETAILS, "Past Project Curation"),
            ("Spring picks<br>" + FLATTENED_DETAILS, "Spring picks"),
        ]:
            with self.subTest(note=note):
                old_name = migration.old_default_name(note, _rows("A", "B"))
                self.assertIn("Year-Semester: 2026 Spring", old_name)
                self.assertEqual(renamed_share_name(old_name, note, _rows("A", "B")), new_name)

    def test_renames_a_project_title_name_after_a_note_was_added_later(self):
        # Adding a note on the shared page never re-derived the name, so the stored name is still rows[0]'s title.
        rows = _rows("Upgrading Advanced Image Analysis Platform", "Other")
        for note in ["<div>For the Keysight meeting</div>", PROJECT_SUMMARY_BLOCK]:
            with self.subTest(note=note):
                self.assertEqual(
                    renamed_share_name("Upgrading Advanced Image Analysis Platform", note, rows),
                    "Past Project Curation",
                )

    def test_renames_a_heading_typed_inside_the_inserted_block_to_that_heading(self):
        note = PROJECT_SUMMARY_BLOCK.replace(
            '<div data-past-project-key="k1">',
            '<div data-past-project-key="k1"><div><strong>My CSE list</strong></div>',
        )
        old_name = migration.old_default_name(note, _rows("A", "B"))
        self.assertTrue(old_name.startswith("My CSE list Project 1"))
        self.assertEqual(renamed_share_name(old_name, note, _rows("A", "B")), "My CSE list")

    def test_keeps_typed_names_and_names_from_the_owners_own_note(self):
        rows = _rows("A", "B")
        self.assertIsNone(renamed_share_name("Keysight picks", "", rows))
        note = "<div>Spring 2026 finalists</div><div>Please review by Friday</div>"
        self.assertIsNone(renamed_share_name("Spring 2026 finalists Please review by Friday", note, rows))
        separated = "Spring picks<br>-----<br>More text"
        self.assertIsNone(renamed_share_name(migration.old_default_name(separated, rows), separated, rows))
        # The owner's note happens to start with the first project's title: that is the note-derived default.
        self.assertIsNone(renamed_share_name("A", "<div>A</div>", rows))

    def test_keeps_a_typed_first_project_title_on_a_share_never_edited(self):
        # Created with a note that has text, the old code would have named the share after the note, so the owner
        # typed the title. Once the share has been edited, the note may have been added later, so it is renamed.
        rows = _rows("Keysight Robot Arm", "B", "C")
        note = "<div>Keysight Robot Arm and friends</div>"
        self.assertIsNone(renamed_share_name("Keysight Robot Arm", note, rows, updated_at=UNEDITED))
        self.assertEqual(
            renamed_share_name("Keysight Robot Arm", note, rows, updated_at=EDITED), "Past Project Curation"
        )

    def test_keeps_one_row_shares_old_shares_and_blank_names(self):
        self.assertIsNone(renamed_share_name("A", "", _rows("A")))
        self.assertIsNone(renamed_share_name("A", "", _rows("A", "B"), created_at=BEFORE_AUTO_NAMING))
        self.assertIsNone(renamed_share_name("", "", _rows("A", "B")))

    def test_keeps_a_name_that_no_longer_matches_the_first_row(self):
        # The first project was removed after creation: the stored name is no longer derivable, so leave it.
        self.assertIsNone(renamed_share_name("A", "", _rows("B", "C")))


class RenameAutoNamedSharesForwardTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.member = get_user_model().objects.create_user(password="SharePass123!", is_active=True)

    def _share(self, name, rows, note="", created_at=AFTER_AUTO_NAMING):
        share = PastProjectShare.objects.create(name=name, rows=rows, note=note, created_by=self.member)
        PastProjectShare.objects.filter(pk=share.pk).update(created_at=created_at, updated_at=EDITED)
        return share

    def test_renames_only_auto_named_shares_and_bumps_their_version(self):
        auto = self._share("Newest Project", _rows("Newest Project", "Older Project"))
        typed = self._share("Western Digital picks", _rows("Newest Project", "Older Project"))
        before_cutoff = self._share("Newest Project", _rows("Newest Project", "Older"), created_at=BEFORE_AUTO_NAMING)

        with patch("sys.stdout", new_callable=StringIO) as stdout:
            migration.rename_auto_named_shares(global_apps, None)

        for share in (auto, typed, before_cutoff):
            share.refresh_from_db()
        self.assertEqual(auto.name, "Past Project Curation")
        self.assertEqual(auto.version, 2)
        self.assertEqual(typed.name, "Western Digital picks")
        self.assertEqual(typed.version, 1)
        self.assertEqual(before_cutoff.name, "Newest Project")
        self.assertEqual(before_cutoff.version, 1)
        self.assertIn(str(auto.pk), stdout.getvalue())
        self.assertNotIn(str(typed.pk), stdout.getvalue())
