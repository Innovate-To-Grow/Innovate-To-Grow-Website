"""/projects/<id>/ keeps resolving current-semester project links after the schedule they came from is replaced."""

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.projects.models import Project, Semester


def _schedule_row(team, title, **extra):
    return {
        "Track": 1,
        "Order": int(team) % 100,
        "Year-Semester": "2026-1 Spring",
        "Class": "CAP",
        "Team#": team,
        "Project Title": title,
        **extra,
    }


class CurrentProjectLinkTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        spring = CurrentProjectSchedule.objects.create(name="2026 Spring I2G Event")
        sync_schedule(
            spring,
            tracks_records=[{"Track": 1, "Room": "Granite", "Class": "CAP"}],
            projects_records=[
                _schedule_row("101", "ASHRAE HVAC Design Calculations"),
                _schedule_row("102", "Solar Kiln", Abstract="Dries lumber with sunlight."),
            ],
        )
        # The fall schedule goes live; the spring one stays in the database, inactive.
        CurrentProjectSchedule.objects.create(name="2026 Fall I2G Event", is_active=True)
        self.spring_ids = dict(CurrentProject.objects.filter(schedule=spring).values_list("team_number", "pk"))
        semester = Semester.objects.create(year=2026, season=1, is_published=True)
        self.archived = Project.objects.create(
            semester=semester, class_code="CAP", team_number="101", project_title="ASHRAE HVAC Design Calculations"
        )

    def test_link_to_an_archived_team_serves_its_archive_project(self):
        response = self.client.get(f"/projects/{self.spring_ids['101']}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(self.archived.pk))
        self.assertEqual(response.data["semester_label"], "2026-1 Spring")

    def test_link_to_a_team_not_in_the_archive_serves_the_current_project(self):
        response = self.client.get(f"/projects/{self.spring_ids['102']}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(self.spring_ids["102"]))
        self.assertEqual(response.data["project_title"], "Solar Kiln")
        self.assertEqual(response.data["abstract"], "Dries lumber with sunlight.")
        self.assertEqual(response.data["semester_label"], "2026-1 Spring")
        self.assertEqual((response.data["track"], response.data["presentation_order"]), (1, 2))
        self.assertEqual(response["Cache-Control"], "public, max-age=60, stale-while-revalidate=300")
        self.assertIn("ETag", response)

    def test_unpublished_archive_semester_is_not_served(self):
        Semester.objects.filter(year=2026, season=1).update(is_published=False)

        response = self.client.get(f"/projects/{self.spring_ids['101']}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(self.spring_ids["101"]))

    def test_slotted_team_an_admin_hid_still_matches_its_archive_project_by_team_number(self):
        # The team has a slot, so it presented that semester; hiding it changes nothing about which team it is.
        CurrentProject.objects.filter(pk=self.spring_ids["101"]).update(is_presenting=False)
        Project.objects.filter(pk=self.archived.pk).update(project_title="ASHRAE HVAC Design Calculation Suite")

        response = self.client.get(f"/projects/{self.spring_ids['101']}/")

        self.assertEqual(response.data["id"], str(self.archived.pk))

    def test_unknown_id_is_still_not_found(self):
        response = self.client.get(f"/projects/{uuid.uuid4()}/")

        self.assertEqual(response.status_code, 404)


def _listed_row(team, title):
    # The spring sheet lists teams that present in the fall, before they hand in anything.
    return {
        "Track": "(Fall)",
        "Order": "(Fall)",
        "Class": "CAP",
        "Team#": team,
        "TeamName": f"CAP-{team}",
        "Project Title": title,
        "Abstract": f"Abstract-{team}",
    }


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
