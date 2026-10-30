"""How the schedule sync reads a sheet's cells and keeps each team's CurrentProject across syncs."""

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.event.models import CurrentProject, CurrentProjectSchedule, EventScheduleSlot
from apps.event.services import sync_schedule
from apps.event.services.schedule_sync.parsing import build_slot_rows

TRACKS = [{"Track": 1, "Room": "Granite", "Class": "CAP"}]


def _row(**overrides):
    row = {
        "Track": 1,
        "Order": 1,
        "Year-Semester": "2026-2 Fall",
        "Class": "CAP",
        "Team#": "101",
        "TeamName": "HVAC Regulators",
        "Project Title": "ASHRAE HVAC Design Calculations",
        "Organization": "ASHRAE",
        "Industry": "Energy",
        "Abstract": "Designs an HVAC system.",
        "Student Names": "Ada Lovelace, Ben Ng",
    }
    row.update(overrides)
    return row


class PlaceholderCellsTest(TestCase):
    def test_placeholder_cells_are_stored_as_the_sheet_has_them(self):
        # Before teams hand in theirs, the sheet fills "Abstract-101" and a team name of "CAP-101"; both are kept.
        cache.clear()
        config = CurrentProjectSchedule.objects.create(name="2026 Fall")

        sync_schedule(
            config, tracks_records=TRACKS, projects_records=[_row(TeamName="CAP-101", Abstract="Abstract-101")]
        )

        project = CurrentProject.objects.get(schedule=config)
        slot = EventScheduleSlot.objects.get(track__section__config=config)
        self.assertEqual((project.team_name, project.abstract), ("CAP-101", "Abstract-101"))
        self.assertEqual((slot.team_name, slot.abstract), ("CAP-101", "Abstract-101"))


class WhitespaceCellsTest(TestCase):
    def test_one_line_cells_collapse_whitespace(self):
        (slot,) = build_slot_rows(
            [
                _row(
                    **{
                        "Project Title": "Protein  Separators",
                        "Organization": "UC Merced Sustainability Office",
                        "Student Names": "Ada Lovelace,\tBen Ng",
                    }
                )
            ]
        )

        self.assertEqual(slot["project_title"], "Protein Separators")
        self.assertEqual(slot["organization"], "UC Merced Sustainability Office")
        self.assertEqual(slot["student_names"], "Ada Lovelace, Ben Ng")

    def test_abstract_keeps_its_paragraphs(self):
        (slot,) = build_slot_rows([_row(Abstract="First  paragraph.\r\n\r\nSecond paragraph.")])

        self.assertEqual(slot["abstract"], "First paragraph.\n\nSecond paragraph.")


class CurrentProjectIdentityTest(TestCase):
    def setUp(self):
        cache.clear()
        self.config = CurrentProjectSchedule.objects.create(name="2026 Fall")

    def _sync(self, *rows):
        sync_schedule(self.config, tracks_records=TRACKS, projects_records=list(rows))

    def test_title_edit_keeps_the_project_id(self):
        self._sync(_row(**{"Project Title": "Protein Seperators"}))
        original = CurrentProject.objects.get(schedule=self.config)

        self._sync(_row(**{"Project Title": "Protein Separators"}))

        project = CurrentProject.objects.get(schedule=self.config)
        self.assertEqual(project.pk, original.pk)
        self.assertEqual(project.project_title, "Protein Separators")
        self.assertEqual(EventScheduleSlot.objects.get(track__section__config=self.config).project_id, original.pk)

    def test_each_team_keeps_its_own_row(self):
        self._sync(_row(), _row(Order=2, **{"Team#": "102", "Project Title": "Second"}))
        ids = dict(CurrentProject.objects.values_list("team_number", "pk"))

        self._sync(
            _row(**{"Project Title": "Renamed first"}),
            _row(Order=2, **{"Team#": "102", "Project Title": "Renamed second"}),
        )

        self.assertEqual(dict(CurrentProject.objects.values_list("team_number", "pk")), ids)

    def test_swapped_team_numbers_keep_each_project_its_id(self):
        self._sync(_row(**{"Project Title": "Alpha"}), _row(Order=2, **{"Team#": "102", "Project Title": "Beta"}))
        ids = dict(CurrentProject.objects.values_list("project_title", "pk"))

        self._sync(_row(**{"Project Title": "Beta"}), _row(Order=2, **{"Team#": "102", "Project Title": "Alpha"}))

        self.assertEqual(dict(CurrentProject.objects.values_list("project_title", "pk")), ids)
        self.assertEqual(CurrentProject.objects.get(pk=ids["Alpha"]).team_number, "102")

    def test_title_two_teams_share_does_not_move_a_project(self):
        self._sync(_row(**{"Project Title": "Alpha"}), _row(Order=2, **{"Team#": "102", "Project Title": "Beta"}))
        ids = dict(CurrentProject.objects.values_list("team_number", "pk"))

        # "Beta" names two teams now, so it says nothing about which stored row is whose.
        self._sync(_row(**{"Project Title": "Beta"}), _row(Order=2, **{"Team#": "102", "Project Title": "Beta"}))

        self.assertEqual(dict(CurrentProject.objects.values_list("team_number", "pk")), ids)

    def test_rows_sharing_team_number_and_title_still_share_one_project(self):
        self._sync(_row(), _row(Order=2))

        self.assertEqual(CurrentProject.objects.filter(schedule=self.config).count(), 1)

    def test_resync_checks_the_live_schedule_without_a_query_per_project(self):
        rows = [_row(Order=n, **{"Team#": str(100 + n), "Project Title": f"Project {n}"}) for n in range(1, 4)]
        self._sync(*rows)

        with CaptureQueriesContext(connection) as queries:
            self._sync(*rows)

        # The save signal asks whether each project's schedule is live; the sync already holds that schedule.
        schedule_table = f'"{CurrentProjectSchedule._meta.db_table}"'
        schedule_reads = [
            query["sql"] for query in queries.captured_queries if f"FROM {schedule_table}" in query["sql"]
        ]
        self.assertEqual(schedule_reads, [])
