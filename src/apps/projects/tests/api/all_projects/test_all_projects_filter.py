from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.projects.tests.api.all_projects.test_all_projects import URL, AllProjectsTestCase


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
