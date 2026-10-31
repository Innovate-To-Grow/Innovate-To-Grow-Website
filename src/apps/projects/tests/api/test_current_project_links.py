"""/projects/<id>/ keeps resolving current-semester project links after the schedule they came from is replaced."""

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.projects.models import Project, Semester
from apps.projects.services.current_project_links import (
    active_current_project_links,
    resolve_current_project_link,
    resolve_current_project_links,
)


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

    def test_current_project_detail_names_its_catalog_and_presenting_flag(self):
        response = self.client.get(f"/projects/{self.spring_ids['102']}/")

        self.assertEqual((response.data["catalog"], response.data["is_presenting"]), ("current", True))
        link = resolve_current_project_link(self.spring_ids["102"])
        self.assertIs(link.is_presenting, True)

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


def _row(track, order, class_code, team, title, term="2026-1 Spring"):
    return {
        "Track": track,
        "Order": order,
        "Year-Semester": term,
        "Class": class_code,
        "Team#": team,
        "Project Title": title,
    }


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
