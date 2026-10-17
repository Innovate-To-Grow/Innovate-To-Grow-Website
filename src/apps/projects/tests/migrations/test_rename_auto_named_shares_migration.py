import importlib
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import patch

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.projects.models import PastProjectShare

migration = importlib.import_module("apps.projects.migrations.0010_rename_auto_named_past_project_shares")
renamed_share_name = migration.renamed_share_name

AFTER_AUTO_NAMING = datetime(2026, 10, 16, 23, 18, tzinfo=UTC)
# Names were still required (typed) until PR #335 merged on 2026-06-19 22:48:45 UTC.
BEFORE_AUTO_NAMING = datetime(2026, 6, 19, 12, tzinfo=UTC)
PROJECT_SUMMARY_BLOCK = (
    '<div data-past-project-note-curation="project-summary"><div data-past-project-key="k1">'
    "<div><strong>Project 1</strong></div><div><strong>Year-Semester:</strong> 2026 Spring</div></div></div>"
)


def _rows(*titles):
    return [{"project_title": title, "team_number": str(index)} for index, title in enumerate(titles)]


class RenamedShareNameTests(SimpleTestCase):
    def test_renames_a_share_named_after_its_first_project(self):
        # The reported share: blank name and note, 14 rows, named after rows[0].
        rows = _rows("Upgrading Advanced Image Analysis Platform", *[f"Project {n}" for n in range(13)])
        self.assertEqual(
            renamed_share_name("Upgrading Advanced Image Analysis Platform", "", rows, AFTER_AUTO_NAMING),
            "Past Project Curation",
        )

    def test_renames_a_name_built_from_inserted_project_details(self):
        note = "<div>Hi Bob,</div><br><br>" + PROJECT_SUMMARY_BLOCK
        old_name = migration.old_default_name(note, _rows("A", "B"))
        self.assertTrue(old_name.startswith("Hi Bob, Project 1"))
        self.assertEqual(renamed_share_name(old_name, note, _rows("A", "B"), AFTER_AUTO_NAMING), "Hi Bob,")

    def test_renames_a_project_title_name_after_a_note_was_added_later(self):
        # Adding a note on the shared page never re-derived the name, so the stored name is still rows[0]'s title.
        rows = _rows("Upgrading Advanced Image Analysis Platform", "Other")
        for note in ["<div>For the Keysight meeting</div>", PROJECT_SUMMARY_BLOCK]:
            with self.subTest(note=note):
                self.assertEqual(
                    renamed_share_name("Upgrading Advanced Image Analysis Platform", note, rows, AFTER_AUTO_NAMING),
                    "Past Project Curation",
                )

    def test_renames_a_heading_typed_inside_the_inserted_block_to_that_heading(self):
        note = PROJECT_SUMMARY_BLOCK.replace(
            '<div data-past-project-key="k1">', '<div data-past-project-key="k1"><div><strong>My CSE list</strong></div>'
        )
        old_name = migration.old_default_name(note, _rows("A", "B"))
        self.assertTrue(old_name.startswith("My CSE list Project 1"))
        self.assertEqual(renamed_share_name(old_name, note, _rows("A", "B"), AFTER_AUTO_NAMING), "My CSE list")

    def test_keeps_typed_names_and_names_from_the_owners_own_note(self):
        rows = _rows("A", "B")
        self.assertIsNone(renamed_share_name("Keysight picks", "", rows, AFTER_AUTO_NAMING))
        note = "<div>Spring 2026 finalists</div><div>Please review by Friday</div>"
        self.assertIsNone(
            renamed_share_name("Spring 2026 finalists Please review by Friday", note, rows, AFTER_AUTO_NAMING)
        )
        # The owner's note happens to start with the first project's title: that is the note-derived default.
        self.assertIsNone(renamed_share_name("A", "<div>A</div>", rows, AFTER_AUTO_NAMING))

    def test_keeps_one_row_shares_old_shares_and_blank_names(self):
        self.assertIsNone(renamed_share_name("A", "", _rows("A"), AFTER_AUTO_NAMING))
        self.assertIsNone(renamed_share_name("A", "", _rows("A", "B"), BEFORE_AUTO_NAMING))
        self.assertIsNone(renamed_share_name("", "", _rows("A", "B"), AFTER_AUTO_NAMING))

    def test_keeps_a_name_that_no_longer_matches_the_first_row(self):
        # The first project was removed after creation: the stored name is no longer derivable, so leave it.
        self.assertIsNone(renamed_share_name("A", "", _rows("B", "C"), AFTER_AUTO_NAMING))


class RenameAutoNamedSharesForwardTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.member = get_user_model().objects.create_user(password="SharePass123!", is_active=True)

    def _share(self, name, rows, note=""):
        share = PastProjectShare.objects.create(name=name, rows=rows, note=note, created_by=self.member)
        PastProjectShare.objects.filter(pk=share.pk).update(created_at=AFTER_AUTO_NAMING)
        return share

    def test_renames_only_auto_named_shares_and_bumps_their_version(self):
        auto = self._share("Newest Project", _rows("Newest Project", "Older Project"))
        typed = self._share("Western Digital picks", _rows("Newest Project", "Older Project"))

        with patch("sys.stdout", new_callable=StringIO) as stdout:
            migration.rename_auto_named_shares(global_apps, None)

        auto.refresh_from_db()
        typed.refresh_from_db()
        self.assertEqual(auto.name, "Past Project Curation")
        self.assertEqual(auto.version, 2)
        self.assertEqual(typed.name, "Western Digital picks")
        self.assertEqual(typed.version, 1)
        self.assertIn(str(auto.pk), stdout.getvalue())
        self.assertNotIn(str(typed.pk), stdout.getvalue())
