from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.projects.models import Project, Semester
from apps.projects.services.catalog.current_project_links import (
    active_current_project_links,
)
from apps.projects.tests.api.pages.test_current_project_links import _row


class NormalisedArchiveMatchTest(TestCase):
    """The archive and the event spell some classes and team numbers differently; both still name the same team."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        spring = CurrentProjectSchedule.objects.create(name="2026 Spring I2G Event")
        sync_schedule(
            spring,
            tracks_records=[
                {"Track": 1, "Room": "Granite", "Class": "CAP"},
                {"Track": 2, "Room": "Lab", "Class": "EngSL"},
            ],
            projects_records=[
                _row(1, 1, "CAP", "01", "Solar Kiln"),
                _row(1, 2, "CAP", "7", "Seed Counter"),
                _row(1, 3, "CAP", "12", "Water Sensor"),
                _row(2, 1, "EngSL", "3", "Community Garden"),
            ],
        )
        CurrentProjectSchedule.objects.create(name="2026 Fall I2G Event", is_active=True)
        self.ids = dict(CurrentProject.objects.values_list("project_title", "pk"))
        self.semester = Semester.objects.create(year=2026, season=1, is_published=True)

    def _archive(self, class_code, team_number, title="Archived title"):
        return Project.objects.create(
            semester=self.semester, class_code=class_code, team_number=team_number, project_title=title
        )

    def _served_id(self, title):
        return self.client.get(f"/projects/{self.ids[title]}/").data["id"]

    def test_class_codes_match_ignoring_case(self):
        archived = self._archive("EngSL", "3")

        self.assertEqual(CurrentProject.objects.get(pk=self.ids["Community Garden"]).class_code, "ENGSL")
        self.assertEqual(self._served_id("Community Garden"), str(archived.pk))

    def test_team_number_prefixed_with_its_class_matches(self):
        archived = self._archive("CAP", "CAP01")

        self.assertEqual(self._served_id("Solar Kiln"), str(archived.pk))

    def test_team_numbers_match_ignoring_leading_zeros(self):
        archived = self._archive("CAP", "07")

        self.assertEqual(self._served_id("Seed Counter"), str(archived.pk))

    def test_another_class_or_number_is_still_another_team(self):
        self._archive("CSE", "12")
        self._archive("CAP", "120")
        self._archive("CAP", "CAPX12")

        self.assertEqual(self._served_id("Water Sensor"), str(self.ids["Water Sensor"]))


class ActiveCurrentProjectLinksTest(TestCase):
    """The active schedule's projects, in archive team order, each with its archive project if it has one."""

    def setUp(self):
        cache.clear()
        self.fall = CurrentProjectSchedule.objects.create(name="2026 Fall I2G Event", is_active=True)
        sync_schedule(
            self.fall,
            tracks_records=[
                {"Track": 1, "Room": "Granite", "Class": "CAP"},
                {"Track": 2, "Room": "Lab", "Class": "CSE"},
            ],
            projects_records=[
                _row(1, 1, "CAP", "10", "Solar Kiln", "2026-2 Fall"),
                _row(1, 2, "CAP", "9", "Seed Counter", "2026-2 Fall"),
                _row(2, 1, "CSE", "1", "Course Planner", "2026-2 Fall"),
                {"Track": "(Spring)", "Order": "(Spring)", "Class": "CAP", "Team#": "2", "Project Title": "Bridge"},
            ],
        )
        semester = Semester.objects.create(year=2026, season=2, is_published=True)
        self.archived = Project.objects.create(
            semester=semester, class_code="CAP", team_number="9", project_title="Seed Counter"
        )

    def test_lists_the_active_schedule_in_team_order_with_archive_matches(self):
        links = active_current_project_links()

        self.assertEqual(
            [(link.detail["class_code"], link.detail["team_number"], link.is_presenting) for link in links],
            [("CAP", "2", False), ("CAP", "9", True), ("CAP", "10", True), ("CSE", "1", True)],
        )
        self.assertEqual([link.archived for link in links], [None, self.archived, None, None])
        self.assertEqual({link.detail["catalog"] for link in links}, {"current"})
        self.assertEqual({link.detail["semester_label"] for link in links}, {"2026-2 Fall"})

    def test_query_count_does_not_grow_with_the_projects(self):
        CurrentProject.objects.bulk_create(
            CurrentProject(schedule=self.fall, class_code="CAP", team_number=str(500 + n), project_title=f"Team {n}")
            for n in range(10)
        )

        # The projects, their slots, the schedule's term and that term's archive.
        with self.assertNumQueries(4):
            self.assertEqual(len(active_current_project_links()), 14)

    def test_no_active_schedule_has_no_links(self):
        CurrentProjectSchedule.objects.filter(pk=self.fall.pk).update(is_active=False)

        with self.assertNumQueries(1):
            self.assertEqual(active_current_project_links(), [])
