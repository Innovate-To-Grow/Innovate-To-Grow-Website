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

    def test_unpublished_archive_semester_is_not_served(self):
        Semester.objects.filter(year=2026, season=1).update(is_published=False)

        response = self.client.get(f"/projects/{self.spring_ids['101']}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(self.spring_ids["101"]))

    def test_unknown_id_is_still_not_found(self):
        response = self.client.get(f"/projects/{uuid.uuid4()}/")

        self.assertEqual(response.status_code, 404)
