"""/projects/all/: the active schedule's projects that are not archived yet, then the archive, paged as one list."""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.projects.models import Project, Semester

URL = "/projects/all/"
COMPACT_FIELDS = {
    "id",
    "semester_label",
    "class_code",
    "team_number",
    "team_name",
    "project_title",
    "organization",
    "industry",
    "student_names",
    "track",
    "presentation_order",
}
CATALOG_FIELDS = {"catalog", "is_presenting", "current_project_id"}
SOLAR_KILN_TEXT = {"Abstract": "Dries lumber with sunlight.", "Student Names": "Ada Lovelace"}


def _slotted(track, order, class_code, team, title, **extra):
    return {
        "Track": track,
        "Order": order,
        "Year-Semester": "2026-2 Fall",
        "Class": class_code,
        "Team#": team,
        "Project Title": title,
        **extra,
    }


class AllProjectsTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        spring = CurrentProjectSchedule.objects.create(name="2026 Spring I2G Event")
        sync_schedule(
            spring,
            tracks_records=[{"Track": 1, "Room": "Granite", "Class": "CAP"}],
            projects_records=[{**_slotted(1, 1, "CAP", "50", "Spring Only"), "Year-Semester": "2026-1 Spring"}],
        )
        self.schedule = CurrentProjectSchedule.objects.create(name="2026 Fall I2G Event", is_active=True)
        sync_schedule(
            self.schedule,
            tracks_records=[
                {"Track": 1, "Room": "Granite", "Class": "CAP"},
                {"Track": 2, "Room": "Lab", "Class": "CSE"},
            ],
            projects_records=[
                _slotted(1, 1, "CAP", "10", "Solar Kiln", **SOLAR_KILN_TEXT),
                _slotted(1, 2, "CAP", "9", "Seed Counter", Abstract="Counts seeds."),
                _slotted(2, 1, "CSE", "1", "Course Planner"),
                # Listed only: no slot, and the sheet's placeholders until the team hands anything in.
                {
                    "Track": "(Spring)",
                    "Order": "(Spring)",
                    "Class": "CAP",
                    "Team#": "2",
                    "TeamName": "CAP-2",
                    "Project Title": "Bridge",
                    "Abstract": "Abstract-002",
                },
            ],
        )
        self.current = {
            project.project_title: project for project in CurrentProject.objects.filter(schedule=self.schedule)
        }
        self.fall = Semester.objects.create(year=2026, season=2, is_published=True)
        self.spring = Semester.objects.create(year=2026, season=1, is_published=True)
        old = Semester.objects.create(year=2025, season=2, is_published=True)
        hidden = Semester.objects.create(year=2027, season=1, is_published=False)
        # Fall's archive already holds CAP 9, so the current CAP 9 is listed as this row.
        self.seed_counter = self.archive(self.fall, "CAP", "9", "Seed Counter")
        self.robotics = self.archive(self.spring, "CAP", "3", "Spring Robotics")
        self.ashrae = self.archive(self.spring, "CAP", "101", "ASHRAE HVAC", abstract="Abstract-101")
        self.planner = self.archive(old, "CSE", "2", "Old Planner", student_names="Ada Byron")
        self.archive(hidden, "CAP", "1", "Unpublished Project")

    @staticmethod
    def archive(semester, class_code, team_number, title, **extra):
        return Project.objects.create(
            semester=semester, class_code=class_code, team_number=team_number, project_title=title, **extra
        )

    def ids(self, params=None):
        response = self.client.get(URL, {"page_size": 100, **(params or {})})
        self.assertEqual(response.status_code, 200)
        return [row["id"] for row in response.data["results"]]

    def current_id(self, title):
        return str(self.current[title].pk)


class AllProjectsListTest(AllProjectsTestCase):
    def test_lists_current_teams_in_team_order_then_the_archive(self):
        response = self.client.get(URL, {"page_size": 100})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 7)
        self.assertEqual(
            [(row["catalog"], row["class_code"], row["team_number"]) for row in response.data["results"]],
            [
                ("current", "CAP", "2"),
                ("current", "CAP", "10"),
                ("current", "CSE", "1"),
                ("archive", "CAP", "9"),
                ("archive", "CAP", "3"),
                ("archive", "CAP", "101"),
                ("archive", "CSE", "2"),
            ],
        )
        self.assertNotIn("Spring Only", [row["project_title"] for row in response.data["results"]])
        self.assertNotIn("Unpublished Project", [row["project_title"] for row in response.data["results"]])

    def test_current_and_archive_rows_carry_the_compact_fields_and_the_catalog_fields(self):
        results = self.client.get(URL, {"page_size": 100}).data["results"]
        by_title = {row["project_title"]: row for row in results}

        for row in results:
            with self.subTest(title=row["project_title"]):
                self.assertEqual(set(row), COMPACT_FIELDS | CATALOG_FIELDS)
        self.assertEqual(
            by_title["Solar Kiln"],
            {
                "id": self.current_id("Solar Kiln"),
                "semester_label": "2026-2 Fall",
                "class_code": "CAP",
                "team_number": "10",
                "team_name": "",
                "project_title": "Solar Kiln",
                "organization": "",
                "industry": "",
                "student_names": "Ada Lovelace",
                "track": 1,
                "presentation_order": 1,
                "catalog": "current",
                "is_presenting": True,
                "current_project_id": None,
            },
        )
        robotics = by_title["Spring Robotics"]
        self.assertEqual(robotics["id"], str(self.robotics.pk))
        self.assertEqual(
            (robotics["catalog"], robotics["is_presenting"], robotics["current_project_id"]), ("archive", None, None)
        )

    def test_team_the_schedule_only_lists_has_the_schedule_term_and_its_sheet_placeholders(self):
        bridge = next(row for row in self.client.get(URL).data["results"] if row["project_title"] == "Bridge")

        self.assertEqual(bridge["id"], self.current_id("Bridge"))
        self.assertEqual((bridge["semester_label"], bridge["team_name"]), ("2026-2 Fall", "CAP-2"))
        self.assertEqual((bridge["track"], bridge["presentation_order"], bridge["is_presenting"]), (None, None, False))
        self.assertEqual(self.ids({"search": "Abstract-002"}), [self.current_id("Bridge")])

    def test_archived_current_team_is_listed_once_as_its_archive_row(self):
        results = self.client.get(URL, {"page_size": 100}).data["results"]

        seed_counters = [row for row in results if row["project_title"] == "Seed Counter"]
        self.assertEqual(len(seed_counters), 1)
        self.assertEqual(seed_counters[0]["id"], str(self.seed_counter.pk))
        self.assertEqual(seed_counters[0]["current_project_id"], self.current_id("Seed Counter"))
        self.assertNotIn(self.current_id("Seed Counter"), [row["id"] for row in results])
        # Its text is the archive's: the current row's abstract no longer finds it.
        self.assertEqual(self.ids({"search": "counts seeds"}), [])
