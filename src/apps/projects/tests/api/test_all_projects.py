"""/projects/all/: the active schedule's projects that are not archived yet, then the archive, paged as one list."""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.authn.tests.stale_bearer import assert_stale_bearer_reads_as_anonymous
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

    def test_archive_import_turns_a_current_row_into_its_archive_row(self):
        before = self.client.get(URL)

        imported = self.archive(self.fall, "CAP", "10", "Solar Kiln")
        after = self.client.get(URL, HTTP_IF_NONE_MATCH=before["ETag"])

        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.data["count"], before.data["count"])
        solar_kilns = [row for row in after.data["results"] if row["project_title"] == "Solar Kiln"]
        self.assertEqual([(row["id"], row["catalog"]) for row in solar_kilns], [(str(imported.pk), "archive")])
        self.assertEqual(solar_kilns[0]["current_project_id"], self.current_id("Solar Kiln"))

    def test_listed_team_with_an_archived_teams_number_but_another_title_is_kept(self):
        # Team numbers are reused every semester; without a slot only the title says it is the same team.
        other = self.archive(self.fall, "CAP", "2", "Truss Analyzer")

        response = self.client.get(URL, {"page_size": 100})

        self.assertEqual(response.data["count"], 8)
        self.assertIn(self.current_id("Bridge"), [row["id"] for row in response.data["results"]])
        truss = next(row for row in response.data["results"] if row["id"] == str(other.pk))
        self.assertIsNone(truss["current_project_id"])

    def test_listed_team_whose_title_is_archived_is_hidden(self):
        archived = self.archive(self.fall, "CAP", "2", " bridge ")

        results = self.client.get(URL, {"page_size": 100}).data["results"]

        self.assertNotIn(self.current_id("Bridge"), [row["id"] for row in results])
        stand_in = next(row for row in results if row["id"] == str(archived.pk))
        self.assertEqual(stand_in["current_project_id"], self.current_id("Bridge"))

    def test_archived_team_is_matched_by_its_normalised_class_and_team_number(self):
        # The event sync stores "EngSL" as "ENGSL"; the archive keeps the sheet's spelling and padding.
        current = CurrentProject.objects.create(
            schedule=self.schedule, class_code="ENGSL", team_number="7", project_title="Service Kiosk"
        )
        archived = self.archive(self.fall, "EngSL", "07", "Service  kiosk")

        results = self.client.get(URL, {"page_size": 100}).data["results"]

        self.assertNotIn(str(current.pk), [row["id"] for row in results])
        stand_in = next(row for row in results if row["id"] == str(archived.pk))
        self.assertEqual(stand_in["current_project_id"], str(current.pk))

    def test_rows_resolve_at_the_detail_endpoint_with_the_same_catalog(self):
        for row in self.client.get(URL, {"page_size": 100}).data["results"]:
            with self.subTest(title=row["project_title"]):
                detail = self.client.get(f"/projects/{row['id']}/")
                self.assertEqual(detail.status_code, 200)
                self.assertEqual((detail.data["id"], detail.data["catalog"]), (row["id"], row["catalog"]))
                self.assertEqual(detail.data["is_presenting"], row["is_presenting"])

    def test_no_active_schedule_lists_the_archive(self):
        CurrentProjectSchedule.objects.filter(pk=self.schedule.pk).update(is_active=False)

        response = self.client.get(URL, {"page_size": 100})

        archive = self.client.get("/projects/archive/", {"page_size": 100})
        self.assertEqual(response.data["count"], archive.data["count"])
        self.assertEqual(
            [row["id"] for row in response.data["results"]], [row["id"] for row in archive.data["results"]]
        )
        self.assertEqual({row["catalog"] for row in response.data["results"]}, {"archive"})
        self.assertEqual({row["current_project_id"] for row in response.data["results"]}, {None})

    def test_reads_as_anonymous_with_a_stale_bearer(self):
        self.assertEqual(self.client.get(URL).status_code, 200)
        assert_stale_bearer_reads_as_anonymous(self, lambda **extra: self.client.get(URL, **extra))


class AllProjectsFilterTest(AllProjectsTestCase):
    def test_search_reads_a_current_abstract_and_student_names_ignoring_case(self):
        self.assertEqual(self.ids({"search": "SUNLIGHT"}), [self.current_id("Solar Kiln")])
        self.assertEqual(self.ids({"search": "ada lovelace"}), [self.current_id("Solar Kiln")])
        # Current and archive rows alike.
        self.assertEqual(self.ids({"search": "ada"}), [self.current_id("Solar Kiln"), str(self.planner.pk)])

    def test_search_reads_the_other_text_fields(self):
        for search, title in (("kiln", "Solar Kiln"), ("cap-2", "Bridge"), ("cse", "Course Planner")):
            with self.subTest(search=search):
                self.assertEqual(self.ids({"search": search})[0], self.current_id(title))

    def test_term_filters_read_a_current_projects_term(self):
        fall = [self.current_id("Bridge"), self.current_id("Solar Kiln"), self.current_id("Course Planner")]
        self.assertEqual(self.ids({"year": 2026, "season": 2}), [*fall, str(self.seed_counter.pk)])
        self.assertEqual(self.ids({"semester": "2026-2 FALL"}), [*fall, str(self.seed_counter.pk)])
        self.assertEqual(self.ids({"year": 2026, "season": 1}), [str(self.robotics.pk), str(self.ashrae.pk)])
        self.assertEqual(self.ids({"year": 2025}), [str(self.planner.pk)])
        self.assertEqual(self.ids({"year": 2026, "search": "planner"}), [self.current_id("Course Planner")])

    def test_blank_search_lists_everything(self):
        self.assertEqual(len(self.ids({"search": "  "})), 7)

    def test_rejects_invalid_pagination_and_filters(self):
        for params in (
            {"page": 0},
            {"page": "nope"},
            {"page_size": 0},
            {"page_size": 101},
            {"search": "x" * 201},
            {"year": 1999},
            {"season": 3},
            {"semester": ""},
        ):
            with self.subTest(params=params):
                response = self.client.get(URL, params)
                self.assertEqual(response.status_code, 400)


class AllProjectsPaginationTest(AllProjectsTestCase):
    def test_pages_run_across_the_current_and_archive_boundary(self):
        pages = [self.client.get(URL, {"page": page, "page_size": 2}) for page in (1, 2, 3, 4)]

        self.assertEqual([page.data["count"] for page in pages], [7, 7, 7, 7])
        self.assertEqual(
            [[row["catalog"] for row in page.data["results"]] for page in pages],
            [["current", "current"], ["current", "archive"], ["archive", "archive"], ["archive"]],
        )
        self.assertEqual([row["id"] for page in pages for row in page.data["results"]], self.ids())
        self.assertEqual(pages[1].data["next"], "http://testserver/projects/all/?page=3&page_size=2")
        self.assertEqual(pages[1].data["previous"], "http://testserver/projects/all/?page_size=2")
        self.assertIsNone(pages[3].data["next"])

    def test_page_past_the_end_is_not_found(self):
        self.assertEqual(self.client.get(URL, {"page": 4, "page_size": 2}).status_code, 200)
        self.assertEqual(self.client.get(URL, {"page": 5, "page_size": 2}).status_code, 404)
        self.assertEqual(self.client.get(URL, {"page": 2}).status_code, 404)

    def test_empty_list_still_has_a_first_page(self):
        response = self.client.get(URL, {"search": "nothing matches this"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["count"], response.data["results"]), (0, []))


class AllProjectsCachingTest(AllProjectsTestCase):
    def test_public_etag_answers_conditional_gets_and_follows_a_schedule_change(self):
        first = self.client.get(URL, {"page_size": 2})

        self.assertEqual(first["Cache-Control"], "public, max-age=60, stale-while-revalidate=300")
        self.assertNotEqual(first["ETag"], self.client.get(URL, {"page_size": 3})["ETag"])
        unchanged = self.client.get(URL, {"page_size": 2}, HTTP_IF_NONE_MATCH=first["ETag"])
        self.assertEqual(unchanged.status_code, 304)
        self.assertEqual(unchanged.content, b"")

        # No server cache: the next request reads the synced schedule.
        CurrentProject.objects.filter(pk=self.current["Bridge"].pk).update(project_title="Bridge Monitor")
        changed = self.client.get(URL, {"page_size": 2}, HTTP_IF_NONE_MATCH=first["ETag"])
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.data["results"][0]["project_title"], "Bridge Monitor")

    def test_query_count_does_not_grow_with_the_projects(self):
        CurrentProject.objects.bulk_create(
            CurrentProject(schedule=self.schedule, class_code="ME", team_number=str(n), project_title=f"Team {n}")
            for n in range(10)
        )
        for n in range(10):
            self.archive(self.spring, "ME", str(n), f"Archived {n}")

        # The active schedule's projects, their slots, its term and that term's archive; then the count and the page.
        with self.assertNumQueries(6):
            self.assertEqual(self.client.get(URL, {"page": 2, "page_size": 10}).status_code, 200)
        # A page of current rows only reads no archive rows.
        with self.assertNumQueries(5):
            self.client.get(URL, {"page_size": 10})

    def test_no_active_schedule_costs_one_query_before_the_archive(self):
        CurrentProjectSchedule.objects.filter(pk=self.schedule.pk).update(is_active=False)

        # The (empty) active schedule's projects, then the archive's count and page.
        with self.assertNumQueries(3):
            self.client.get(URL)


class ArchiveProjectDetailCatalogTest(AllProjectsTestCase):
    def test_archive_project_detail_names_the_archive_catalog(self):
        response = self.client.get(f"/projects/{self.robotics.pk}/")

        self.assertEqual((response.data["catalog"], response.data["is_presenting"]), ("archive", None))

    def test_link_to_an_archived_current_team_serves_the_archive_catalog(self):
        response = self.client.get(f"/projects/{self.current_id('Seed Counter')}/")

        self.assertEqual(response.data["id"], str(self.seed_counter.pk))
        self.assertEqual((response.data["catalog"], response.data["is_presenting"]), ("archive", None))
