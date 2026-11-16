from apps.authn.tests.stale_bearer import assert_stale_bearer_reads_as_anonymous
from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.projects.tests.api.all_projects.test_all_projects import URL, AllProjectsTestCase


class AllProjectsListTest(AllProjectsTestCase):
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
