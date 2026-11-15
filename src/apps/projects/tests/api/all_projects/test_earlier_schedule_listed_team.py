import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.projects.models import Project, Semester
from apps.projects.services.catalog.current_project_links import (
    resolve_current_project_link,
    resolve_current_project_links,
)
from apps.projects.tests.api.pages.test_current_project_links import _listed_row, _schedule_row


class EarlierScheduleListedTeamTest(TestCase):
    """A team an earlier schedule only listed resolves to the row of the semester it presents in."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        tracks = [{"Track": 1, "Room": "Granite", "Class": "CAP"}]
        spring = CurrentProjectSchedule.objects.create(name="2026 Spring I2G Event")
        sync_schedule(
            spring,
            tracks_records=tracks,
            projects_records=[
                _schedule_row("102", "Solar Kiln"),
                _listed_row("201", "Power Aspire"),
                _listed_row("202", "Frequency Ablation Caps"),
            ],
        )
        self.spring_ids = dict(CurrentProject.objects.filter(schedule=spring).values_list("team_number", "pk"))
        fall = CurrentProjectSchedule.objects.create(name="2026 Fall I2G Event", is_active=True)
        fall_row = {"Year-Semester": "2026-2 Fall"}
        sync_schedule(
            fall,
            tracks_records=tracks,
            projects_records=[
                _schedule_row("201", "Power Aspire", **fall_row, **{"Student Names": "Ada Lovelace"}),
                _schedule_row("202", "Seed Vacuum Harvester", **fall_row),
                _schedule_row("102", "Solar Kiln", **fall_row, Order=3),
            ],
        )
        self.fall_ids = dict(CurrentProject.objects.filter(schedule=fall).values_list("team_number", "pk"))

    def test_listed_team_serves_the_live_schedule_row(self):
        response = self.client.get(f"/projects/{self.spring_ids['201']}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(self.fall_ids["201"]))
        self.assertEqual(response.data["semester_label"], "2026-2 Fall")
        self.assertEqual(response.data["student_names"], "Ada Lovelace")
        self.assertEqual((response.data["track"], response.data["presentation_order"]), (1, 1))

    def test_reused_team_number_with_another_title_is_not_the_same_team(self):
        response = self.client.get(f"/projects/{self.spring_ids['202']}/")

        self.assertEqual(response.data["id"], str(self.spring_ids["202"]))
        self.assertEqual(response.data["project_title"], "Frequency Ablation Caps")

    def test_listed_team_is_not_served_another_archive_team_with_its_number(self):
        # The listed 202 presents in a later semester; spring's own CAP 202 was another team.
        semester = Semester.objects.create(year=2026, season=1, is_published=True)
        Project.objects.create(semester=semester, class_code="CAP", team_number="202", project_title="Seed Counter")

        response = self.client.get(f"/projects/{self.spring_ids['202']}/")

        self.assertEqual(response.data["id"], str(self.spring_ids["202"]))
        self.assertEqual(response.data["project_title"], "Frequency Ablation Caps")

    def test_unslotted_row_an_admin_shows_still_needs_its_title_to_match_an_archive_project(self):
        CurrentProject.objects.filter(pk=self.spring_ids["202"]).update(is_presenting=True)
        semester = Semester.objects.create(year=2026, season=1, is_published=True)
        Project.objects.create(semester=semester, class_code="CAP", team_number="202", project_title="Seed Counter")

        response = self.client.get(f"/projects/{self.spring_ids['202']}/")

        self.assertEqual(response.data["id"], str(self.spring_ids["202"]))
        self.assertEqual(response.data["project_title"], "Frequency Ablation Caps")

    def test_unslotted_team_with_its_title_in_the_archive_serves_the_archive_project(self):
        semester = Semester.objects.create(year=2026, season=1, is_published=True)
        archived = Project.objects.create(
            semester=semester, class_code="CAP", team_number="202", project_title="Frequency Ablation Caps"
        )

        response = self.client.get(f"/projects/{self.spring_ids['202']}/")

        self.assertEqual(response.data["id"], str(archived.pk))

    def test_team_that_presented_in_the_earlier_semester_keeps_its_own_row(self):
        response = self.client.get(f"/projects/{self.spring_ids['102']}/")

        self.assertEqual(response.data["id"], str(self.spring_ids["102"]))
        self.assertEqual(response.data["semester_label"], "2026-1 Spring")

    def test_only_listed_team_detail_is_not_presenting(self):
        response = self.client.get(f"/projects/{self.spring_ids['202']}/")

        self.assertEqual((response.data["catalog"], response.data["is_presenting"]), ("current", False))

    def test_unslotted_team_matches_its_archive_title_ignoring_case_and_spacing(self):
        semester = Semester.objects.create(year=2026, season=1, is_published=True)
        archived = Project.objects.create(
            semester=semester, class_code="CAP", team_number="202", project_title=" frequency  ablation CAPS"
        )

        response = self.client.get(f"/projects/{self.spring_ids['202']}/")

        self.assertEqual(response.data["id"], str(archived.pk))

    def test_links_in_bulk_are_keyed_by_the_requested_id_and_match_the_single_lookup(self):
        semester = Semester.objects.create(year=2026, season=1, is_published=True)
        archived = Project.objects.create(semester=semester, class_code="CAP", team_number="102", project_title="Kiln")
        ids = [*self.spring_ids.values(), *self.fall_ids.values()]

        links = resolve_current_project_links([*ids, uuid.uuid4(), "not-a-uuid"])

        self.assertEqual(set(links), {str(project_id) for project_id in ids})
        for project_id in ids:
            self.assertEqual(links[str(project_id)], resolve_current_project_link(project_id))
        self.assertEqual(links[str(self.spring_ids["102"])].archived, archived)
        self.assertIsNone(links[str(self.fall_ids["102"])].archived)
        self.assertEqual(links[str(self.spring_ids["201"])].detail["id"], str(self.fall_ids["201"]))

    def test_bulk_lookup_runs_one_archive_query_per_term_however_many_ids(self):
        # The project rows, the team records of the listed rows, the slots, the terms, and the two terms' archives.
        with self.assertNumQueries(6):
            resolve_current_project_links([self.spring_ids["102"], self.spring_ids["201"], self.spring_ids["202"]])
        with self.assertNumQueries(6):
            resolve_current_project_links([*self.spring_ids.values(), *self.fall_ids.values()])
