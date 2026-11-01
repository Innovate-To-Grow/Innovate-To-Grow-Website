"""A share stores and shows what the published archive says, never the text a client sent."""

import uuid

from apps.projects.models import PastProjectShare, Project, Semester

from .share_helpers import PastProjectShareTestCase, sample_payload, sample_row


class PastProjectShareCatalogRowsTests(PastProjectShareTestCase):
    def test_create_rebuilds_rows_from_the_catalog(self):
        project = self.catalog["T01"]
        forged = sample_row(
            id=str(project.pk),
            project_title="Official 2026 Capstone Award Results",
            organization="Invented Sponsor",
            student_names="Somebody Who Never Took Part",
            abstract="x" * 15_000,
        )

        response = self.client.post("/projects/past-shares/", sample_payload(rows=[forged]), format="json")

        self.assertEqual(response.status_code, 201)
        expected = {
            "id": str(project.pk),
            "semester_label": "2025 Spring",
            "class_code": "ENGR 120",
            "team_number": "T01",
            "team_name": "Team Alpha",
            "project_title": "Shared Project",
            "organization": "Acme",
            "industry": "Technology",
            "abstract": "A project abstract.",
            "student_names": "Alice, Bob",
            "is_presenting": "",
        }
        self.assertEqual(response.data["rows"], [expected])
        self.assertEqual(PastProjectShare.objects.get(pk=response.data["id"]).rows, [expected])

    def test_create_rejects_a_project_id_the_catalog_does_not_have(self):
        response = self.client.post(
            "/projects/past-shares/", sample_payload(rows=[sample_row(id=str(uuid.uuid4()))]), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)
        self.assertFalse(PastProjectShare.objects.exists())

    def test_create_rejects_a_project_of_an_unpublished_semester(self):
        hidden = Semester.objects.create(year=2026, season=Semester.Season.SPRING, is_published=False)
        project = Project.objects.create(semester=hidden, class_code="CAP", team_number="1", project_title="Hidden")

        response = self.client.post(
            "/projects/past-shares/", sample_payload(rows=[sample_row(id=str(project.pk))]), format="json"
        )

        self.assertEqual(response.status_code, 400)

    def test_create_rejects_a_row_without_id_that_names_no_project(self):
        response = self.client.post(
            "/projects/past-shares/", sample_payload(rows=[sample_row(team_number="T77")]), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            str(response.data["rows"][0]), "1 project is not in the published archive. Remove them and save again."
        )

    def test_rejects_oversized_row_text(self):
        response = self.client.post(
            "/projects/past-shares/", sample_payload(rows=[sample_row(abstract="x" * 20_001)]), format="json"
        )

        self.assertEqual(response.status_code, 400)

    def test_patch_keeps_a_stored_row_the_catalog_no_longer_has_as_stored(self):
        removed = sample_row(id=str(uuid.uuid4()), team_number="T77", project_title="Removed since")
        share = PastProjectShare.objects.create(
            name="Mine", rows=[removed, sample_row(team_number="T88")], created_by=self.member
        )
        edited = dict(removed, project_title="Invented title")

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {"rows": [edited, sample_row(team_number="T02")], "version": share.version},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"][0]["project_title"], "Removed since")
        self.assertEqual(response.data["rows"][1]["id"], str(self.catalog["T02"].pk))

    def test_patch_rejects_a_new_row_the_catalog_does_not_have(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {"rows": [sample_row(), sample_row(id=str(uuid.uuid4()))], "version": share.version},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        share.refresh_from_db()
        self.assertEqual(len(share.rows), 1)

    def test_get_shows_the_catalog_text_for_rows_stored_before_it(self):
        project = self.catalog["T01"]
        share = PastProjectShare.objects.create(
            rows=[sample_row(id=str(project.pk), project_title="Forged before the fix", student_names="Nobody")]
        )

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.data["rows"][0]["project_title"], "Shared Project")
        self.assertEqual(response.data["rows"][0]["student_names"], "Alice, Bob")
