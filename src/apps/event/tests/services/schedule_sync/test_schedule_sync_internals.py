from unittest.mock import MagicMock

from django.test import TestCase

from apps.event.models import CurrentProjectSchedule
from apps.event.services.schedule_sync.parsing import (
    build_grand_winners,
    build_slot_rows,
    build_track_rows,
    normalize_section_code,
)
from apps.event.services.schedule_sync.projects import sync_projects_from_slots
from apps.event.services.schedule_sync.sheets import (
    get_worksheet_by_gid,
)


class NormalizeSectionCodeTest(TestCase):
    def test_blank_candidate_is_skipped(self):
        # First candidate normalizes to empty -> continue; second matches a known code.
        self.assertEqual(normalize_section_code("", "CAP-101"), "CAP")

    def test_eng_prefix_maps_to_engsl(self):
        self.assertEqual(normalize_section_code("ENG 110"), "ENGSL")

    def test_unknown_returns_empty(self):
        self.assertEqual(normalize_section_code("ZZZ"), "")


class BuildTrackRowsTest(TestCase):
    def test_skips_rows_without_track_or_section(self):
        records = [
            {"Track": "", "Class": "CAP"},  # no track number -> continue
            {"Track": 2, "Class": ""},  # no section code -> continue
            {"Track": 1, "Class": "CAP", "Room": "Granite"},
        ]
        rows = build_track_rows(records)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["track_number"], 1)
        self.assertEqual(rows[0]["section_code"], "CAP")


class BuildGrandWinnersTest(TestCase):
    def test_collects_award_rows(self):
        records = [
            {"Track": "Award:", "Class": "CAP", "Winner": "Team Alpha"},
            {"Track": "Award:", "Class": "CEE", "Winner": ""},  # no winner -> skipped
            {"Track": "1", "Class": "CAP", "Winner": "ignored"},  # not award -> skipped
        ]
        winners = build_grand_winners(records)
        self.assertEqual(winners, [{"section": "CAP", "winner": "Team Alpha"}])


class BuildSlotRowsTest(TestCase):
    def test_rows_with_missing_track_and_order_are_non_presenting(self):
        records = [{"Track": "", "Order": "", "Class": "CAP", "Team#": "CAP-1"}]
        rows = build_slot_rows(records)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["is_presenting"])
        self.assertEqual(rows[0]["team_number"], "CAP-1")

    def test_spring_and_fall_markers_are_non_presenting(self):
        records = [
            {"Track": "(Spring)", "Order": "(Spring)", "Class": "CAP", "Team#": "CAP-1"},
            {"Track": 1, "Order": "(fall)", "Class": "CAP", "Team#": "CAP-2"},
        ]
        self.assertEqual([row["is_presenting"] for row in build_slot_rows(records)], [False, False])

    def test_skips_half_filled_and_non_numeric_rows(self):
        records = [
            {"Track": 1, "Order": "", "Class": "CAP", "Team#": "CAP-1"},
            {"Track": "", "Order": 2, "Class": "CAP", "Team#": "CAP-2"},
            {"Track": 1, "Order": "TBD", "Class": "CAP", "Team#": "CAP-3"},
        ]
        self.assertEqual(build_slot_rows(records), [])

    def test_blank_track_and_order_break_row_is_dropped(self):
        records = [{"Track": "", "Order": "", "Class": "CAP", "Team Name": "Break"}]
        self.assertEqual(build_slot_rows(records), [])

    def test_skips_non_break_without_team_number(self):
        records = [
            {
                "Track": 1,
                "Order": 1,
                "Class": "CAP",
                "Team#": "",
                "Project Title": "No team here",
            }
        ]
        self.assertEqual(build_slot_rows(records), [])

    def test_keeps_break_slot_without_team_number(self):
        records = [
            {
                "Track": 1,
                "Order": 1,
                "Class": "CAP",
                "Team#": "",
                "Team Name": "break",
                "Project Title": "",
            }
        ]
        rows = build_slot_rows(records)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_break"])


class SyncProjectsFromSlotsTest(TestCase):
    def setUp(self):
        self.config = CurrentProjectSchedule.objects.create(name="Demo Day")

    def _slot(self, **overrides):
        slot = {
            "track_number": 1,
            "slot_order": 1,
            "is_break": False,
            "team_number": "CAP-1",
            "team_name": "Alpha",
            "project_title": "Smart Farm",
            "class_code": "CAP",
            "organization": "Org",
            "industry": "Ag",
            "abstract": "abs",
            "student_names": "Ada",
            "is_presenting": True,
        }
        slot.update(overrides)
        return slot

    def test_skips_slot_without_team_number(self):
        lookup, touched = sync_projects_from_slots(self.config, [self._slot(team_number="   ")])
        self.assertEqual(lookup, {})
        self.assertEqual(touched, set())

    def test_skips_break_titled_slot(self):
        lookup, touched = sync_projects_from_slots(self.config, [self._slot(project_title="Break")])
        self.assertEqual(lookup, {})
        self.assertEqual(touched, set())

    def test_creates_project_and_lookup_for_presenting(self):
        lookup, touched = sync_projects_from_slots(self.config, [self._slot()])
        self.assertEqual(len(touched), 1)
        self.assertIn(("CAP", "CAP-1"), lookup)


class GetWorksheetByGidTest(TestCase):
    def test_returns_matching_worksheet(self):
        ws = MagicMock(id=5)
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=1), ws]))
        self.assertIs(get_worksheet_by_gid(spreadsheet, 5), ws)

    def test_returns_none_when_no_match(self):
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=1)]))
        self.assertIsNone(get_worksheet_by_gid(spreadsheet, 99))
