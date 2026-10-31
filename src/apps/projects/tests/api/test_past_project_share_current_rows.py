"""A share may hold current-semester projects (event CurrentProjects), stored as the event has them until the
archive imports their team, and then shown, and next stored, as the archive row."""

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.projects.models import PastProjectShare, Project, Semester

from .share_helpers import PastProjectShareTestCase, sample_payload, sample_row

URL = "/projects/past-shares/"


def _slotted(order, team, title, **extra):
    return {
        "Track": 1,
        "Order": order,
        "Year-Semester": "2026-2 Fall",
        "Class": "CAP",
        "Team#": team,
        "Project Title": title,
        **extra,
    }


class CurrentShareRowsTestCase(PastProjectShareTestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        spring = CurrentProjectSchedule.objects.create(name="2026 Spring I2G Event")
        sync_schedule(
            spring,
            tracks_records=[{"Track": 1, "Room": "Granite", "Class": "CAP"}],
            projects_records=[
                {**_slotted(1, "50", "Spring Robot"), "Year-Semester": "2026-1 Spring"},
                # Listed in spring, but the team presents in fall: its record is the fall row.
                {"Track": "(Fall)", "Order": "(Fall)", "Class": "CAP", "Team#": "7", "Project Title": "Bridge Sensor"},
            ],
        )
        fall = CurrentProjectSchedule.objects.create(name="2026 Fall I2G Event", is_active=True)
        sync_schedule(
            fall,
            tracks_records=[{"Track": 1, "Room": "Granite", "Class": "CAP"}],
            projects_records=[
                _slotted(1, "10", "Solar Kiln", Abstract="Dries lumber with sunlight.", **{"Student Names": "Ada"}),
                _slotted(2, "7", "Bridge Sensor", Organization="County"),
                # Listed only, with the sheet's placeholders until the team hands anything in.
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
        self.spring = {project.team_number: project for project in CurrentProject.objects.filter(schedule=spring)}
        self.fall = {project.team_number: project for project in CurrentProject.objects.filter(schedule=fall)}

    def current_row(self, project, **overrides):
        """A row as the /all-projects page sends it for a current project: its id and (stale) text."""
        return sample_row(
            id=str(project.pk),
            semester_label="2026 Fall",
            class_code=project.class_code,
            team_number=project.team_number,
            project_title=project.project_title,
            **overrides,
        )

    def import_fall_team(self, team_number, title):
        """What the past-project sheet sync does once it imports fall: the team's archive project."""
        semester, _ = Semester.objects.get_or_create(year=2026, season=Semester.Season.FALL, is_published=True)
        return Project.objects.create(semester=semester, class_code="CAP", team_number=team_number, project_title=title)


class CurrentShareRowsWriteTests(CurrentShareRowsTestCase):
    def test_a_current_project_is_stored_as_the_event_has_it(self):
        kiln = self.fall["10"]

        response = self.client.post(
            URL, sample_payload(rows=[self.current_row(kiln, abstract="Forged")]), format="json"
        )

        self.assertEqual(response.status_code, 201)
        expected = {
            "id": str(kiln.pk),
            "semester_label": "2026 Fall",
            "class_code": "CAP",
            "team_number": "10",
            "team_name": "",
            "project_title": "Solar Kiln",
            "organization": "",
            "industry": "",
            "abstract": "Dries lumber with sunlight.",
            "student_names": "Ada",
            "is_presenting": "Yes",
            "catalog": "current",
        }
        self.assertEqual(response.data["rows"], [expected])
        self.assertEqual(PastProjectShare.objects.get(pk=response.data["id"]).rows, [expected])

    def test_a_listed_only_team_keeps_the_sheet_placeholders_and_the_schedules_term(self):
        response = self.client.post(URL, sample_payload(rows=[self.current_row(self.fall["2"])]), format="json")

        self.assertEqual(response.status_code, 201)
        row = response.data["rows"][0]
        self.assertEqual(
            (row["semester_label"], row["team_name"], row["abstract"], row["is_presenting"], row["catalog"]),
            ("2026 Fall", "CAP-2", "Abstract-002", "No", "current"),
        )

    def test_archive_and_current_rows_are_stored_side_by_side(self):
        rows = [sample_row(id=str(self.catalog["T01"].pk)), self.current_row(self.fall["10"])]

        response = self.client.post(URL, sample_payload(rows=rows), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            [(row["id"], row["catalog"], row["is_presenting"]) for row in response.data["rows"]],
            [(str(self.catalog["T01"].pk), "archive", ""), (str(self.fall["10"].pk), "current", "Yes")],
        )

    def test_a_project_of_an_inactive_schedule_is_accepted_with_its_own_term(self):
        response = self.client.post(URL, sample_payload(rows=[self.current_row(self.spring["50"])]), format="json")

        self.assertEqual(response.status_code, 201)
        row = response.data["rows"][0]
        self.assertEqual((row["id"], row["semester_label"]), (str(self.spring["50"].pk), "2026 Spring"))

    def test_a_team_an_earlier_schedule_only_listed_is_stored_as_its_record(self):
        response = self.client.post(URL, sample_payload(rows=[self.current_row(self.spring["7"])]), format="json")

        self.assertEqual(response.status_code, 201)
        row = response.data["rows"][0]
        self.assertEqual((row["id"], row["organization"]), (str(self.fall["7"].pk), "County"))

    def test_an_archived_team_is_stored_as_its_archive_row(self):
        archived = self.import_fall_team("10", "Solar Kiln")

        response = self.client.post(URL, sample_payload(rows=[self.current_row(self.fall["10"])]), format="json")

        self.assertEqual(response.status_code, 201)
        row = response.data["rows"][0]
        self.assertEqual((row["id"], row["semester_label"], row["catalog"]), (str(archived.pk), "2026 Fall", "archive"))

    def test_rows_naming_the_same_project_are_stored_once(self):
        archived = self.import_fall_team("10", "Solar Kiln")
        rows = [
            self.current_row(self.fall["10"]),
            self.current_row(self.fall["7"]),
            sample_row(id=str(archived.pk)),
            # The spring id of fall's team 7: the same record.
            self.current_row(self.spring["7"]),
        ]

        response = self.client.post(URL, sample_payload(rows=rows), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual([row["id"] for row in response.data["rows"]], [str(archived.pk), str(self.fall["7"].pk)])
        self.assertEqual(len(PastProjectShare.objects.get(pk=response.data["id"]).rows), 2)

    def test_create_refuses_a_deleted_current_project(self):
        row = self.current_row(self.fall["10"])
        self.fall["10"].delete()

        response = self.client.post(URL, sample_payload(rows=[row]), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            str(response.data["rows"][0]), "1 project is not among the published projects. Remove them and save again."
        )

    def test_update_keeps_a_deleted_current_project_as_stored(self):
        created = self.client.post(URL, sample_payload(rows=[self.current_row(self.fall["10"])]), format="json")
        stored = created.data["rows"][0]
        self.fall["10"].delete()

        response = self.client.patch(
            f"{URL}{created.data['id']}/",
            {"rows": [dict(stored, project_title="Invented"), sample_row()], "version": created.data["version"]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"][0], stored)
        self.assertEqual(response.data["rows"][1]["id"], str(self.catalog["T01"].pk))

    def test_a_share_of_archive_rows_never_reads_the_event_tables(self):
        rows = [sample_row(id=str(project.pk)) for project in self.catalog.values()]

        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(URL, sample_payload(rows=rows), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertFalse([query["sql"] for query in queries.captured_queries if '"event_' in query["sql"]])


class CurrentShareRowsReadTests(CurrentShareRowsTestCase):
    def test_a_current_row_reads_as_its_archive_row_once_the_team_is_imported(self):
        created = self.client.post(URL, sample_payload(rows=[self.current_row(self.fall["10"])]), format="json")
        archived = self.import_fall_team("10", "Solar Kiln")

        response = self.client.get(f"{URL}{created.data['id']}/")

        row = response.data["rows"][0]
        self.assertEqual((row["id"], row["catalog"], row["is_presenting"]), (str(archived.pk), "archive", ""))
        # The snapshot itself is unchanged until the next write, which stores the archive row.
        share = PastProjectShare.objects.get(pk=created.data["id"])
        self.assertEqual(share.rows[0]["id"], str(self.fall["10"].pk))
        saved = self.client.patch(
            f"{URL}{share.pk}/", {"rows": response.data["rows"], "version": share.version}, format="json"
        )
        self.assertEqual(saved.status_code, 200)
        share.refresh_from_db()
        self.assertEqual((share.rows[0]["id"], share.rows[0]["catalog"]), (str(archived.pk), "archive"))

    def test_rows_that_became_the_same_project_are_shown_once(self):
        created = self.client.post(URL, sample_payload(rows=[self.current_row(self.fall["10"])]), format="json")
        archived = self.import_fall_team("10", "Solar Kiln")
        share = PastProjectShare.objects.get(pk=created.data["id"])
        share.rows = [*share.rows, {**share.rows[0], "id": str(archived.pk), "catalog": "archive"}]
        share.save()

        response = self.client.get(f"{URL}{share.pk}/")

        self.assertEqual([row["id"] for row in response.data["rows"]], [str(archived.pk)])

    def test_a_current_row_shows_the_events_current_text(self):
        created = self.client.post(URL, sample_payload(rows=[self.current_row(self.fall["10"])]), format="json")
        CurrentProject.objects.filter(pk=self.fall["10"].pk).update(abstract="Dries lumber faster.")

        response = self.client.get(f"{URL}{created.data['id']}/")

        self.assertEqual(response.data["rows"][0]["abstract"], "Dries lumber faster.")

    def test_a_deleted_current_project_is_shown_as_stored(self):
        created = self.client.post(URL, sample_payload(rows=[self.current_row(self.fall["10"])]), format="json")
        self.fall["10"].delete()

        response = self.client.get(f"{URL}{created.data['id']}/")

        self.assertEqual(response.data["rows"], created.data["rows"])
