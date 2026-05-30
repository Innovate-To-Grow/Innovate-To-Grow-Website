from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.event.models import CurrentProjectSchedule
from apps.event.services.schedule_sync.parsing import (
    build_grand_winners,
    build_slot_rows,
    build_track_rows,
    normalize_section_code,
)
from apps.event.services.schedule_sync.projects import sync_projects_from_slots
from apps.event.services.schedule_sync.shared import ScheduleSyncError
from apps.event.services.schedule_sync.sheets import (
    fetch_schedule_sheet_records,
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
    def test_skips_rows_with_missing_track_and_order(self):
        records = [{"Track": "", "Order": "", "Class": "CAP", "Team#": "CAP-1"}]
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


class FetchScheduleSheetRecordsTest(TestCase):
    def _configure(self):
        config = CurrentProjectSchedule.objects.create(
            name="Demo Day",
            sheet_id="sheet-id",
            tracks_gid=1,
            projects_gid=2,
        )
        return config

    def test_unconfigured_source_raises(self):
        CurrentProjectSchedule.objects.create(name="Empty")
        with self.assertRaises(ScheduleSyncError) as ctx:
            fetch_schedule_sheet_records()
        self.assertIn("not fully configured", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_unconfigured_credentials_raises(self, mock_load):
        self._configure()
        mock_load.return_value = MagicMock(is_configured=False)
        with self.assertRaises(ScheduleSyncError) as ctx:
            fetch_schedule_sheet_records()
        self.assertIn("No active Google service account", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_missing_tracks_worksheet_raises(self, mock_load):
        self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        # tracks gid 1 not present, projects gid 2 present.
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=2)]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(ScheduleSyncError) as ctx:
                fetch_schedule_sheet_records()
        self.assertIn("tracks worksheet not found", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_missing_projects_worksheet_raises(self, mock_load):
        self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=1)]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(ScheduleSyncError) as ctx:
                fetch_schedule_sheet_records()
        self.assertIn("projects worksheet not found", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_returns_records_for_both_worksheets(self, mock_load):
        self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        tracks_ws = MagicMock(id=1)
        tracks_ws.get_all_records.return_value = [{"Track": 1}]
        projects_ws = MagicMock(id=2)
        projects_ws.get_all_records.return_value = [{"Team#": "CAP-1"}]
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[tracks_ws, projects_ws]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            tracks, projects = fetch_schedule_sheet_records()
        self.assertEqual(tracks, [{"Track": 1}])
        self.assertEqual(projects, [{"Team#": "CAP-1"}])

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_open_failure_raises_schedule_sync_error(self, mock_load):
        # When gspread cannot open the configured sheet, the error is wrapped.
        self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        client = MagicMock()
        client.open_by_key.side_effect = RuntimeError("boom: sheet unreachable")
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(ScheduleSyncError) as ctx:
                fetch_schedule_sheet_records()
        self.assertIn("Unable to open the configured Google Sheet", str(ctx.exception))
        self.assertIn("boom: sheet unreachable", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_get_all_records_failure_raises_schedule_sync_error(self, mock_load):
        # When reading worksheet records fails, the error is wrapped.
        self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        tracks_ws = MagicMock(id=1)
        tracks_ws.get_all_records.side_effect = RuntimeError("read failed")
        projects_ws = MagicMock(id=2)
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[tracks_ws, projects_ws]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(ScheduleSyncError) as ctx:
                fetch_schedule_sheet_records()
        self.assertIn("Unable to read schedule worksheet records", str(ctx.exception))
        self.assertIn("read failed", str(ctx.exception))
