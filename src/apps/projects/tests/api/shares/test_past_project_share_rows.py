"""Share rows and reading a share: row validation, round-tripped fields, and the public view."""

from rest_framework.test import APIClient

from apps.projects.models import PastProjectShare, Project, Semester

from .share_helpers import Member, PastProjectShareTestCase, sample_payload, sample_row


class PastProjectShareRowsTests(PastProjectShareTestCase):
    """Share rows and reading a share: row validation, round-tripped fields, and the public view."""

    def test_create_share_requires_rows(self):
        response = self.client.post("/projects/past-shares/", sample_payload(rows=[]), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)

    def test_create_share_validates_row_shape(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(rows=[sample_row(project_title=""), {"team_name": "Missing fields"}]),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)

    def test_create_share_accepts_exactly_1000_rows(self):
        rows = [sample_row(team_number=f"T{i:03d}") for i in range(1000)]
        Project.objects.bulk_create(
            Project(
                semester=self.semester, class_code=row["class_code"], team_number=row["team_number"], project_title="P"
            )
            for row in rows
        )

        response = self.client.post("/projects/past-shares/", sample_payload(rows=rows), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["rows"]), 1000)

    def test_create_share_rejects_more_than_1000_rows(self):
        rows = [sample_row(team_number=f"T{i:03d}") for i in range(1001)]

        response = self.client.post("/projects/past-shares/", sample_payload(rows=rows), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)

    def test_get_share_returns_saved_rows(self):
        share = PastProjectShare.objects.create(
            rows=[sample_row(), sample_row(team_number="T02")],
            details_text="Project 1\nAbstract: A project abstract.",
        )

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["rows"]), 2)
        self.assertEqual(response.data["rows"][1]["team_number"], "T02")
        self.assertEqual(response.data["details_text"], "Project 1\nAbstract: A project abstract.")
        self.assertFalse(response.data["can_edit"])

    def test_create_ignores_a_client_presenting_flag(self):
        # Archive projects carry no presenting flag; the pages give their rows "" and so does the stored row.
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(rows=[sample_row(is_presenting="Yes")]),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rows"][0]["is_presenting"], "")
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.rows[0]["is_presenting"], "")

    def test_create_round_trips_project_id(self):
        project_id = str(self.catalog["T02"].pk)

        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(rows=[sample_row(id=project_id, team_number="T02")]),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rows"][0]["id"], project_id)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.rows[0]["id"], project_id)

    def test_create_rejects_invalid_project_id(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(rows=[sample_row(id="not-a-uuid")]),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)

    def test_rows_saved_without_is_presenting_serialize_as_blank(self):
        # Pre-existing shares were stored before is_presenting existed; GET must still return
        # "" for them rather than erroring on the missing key. (T77 is not in the catalog.)
        share = PastProjectShare.objects.create(rows=[sample_row(semester_label="2025 Spring", team_number="T77")])

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"][0]["is_presenting"], "")
        self.assertNotIn("id", response.data["rows"][0])

    def test_get_share_backfills_missing_project_id_from_stable_key(self):
        semester = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=True)
        project = Project.objects.create(
            semester=semester,
            class_code="ENGR 120",
            team_number="T01",
            project_title="Current Project",
            source=Project.Source.SHEET,
        )
        share = PastProjectShare.objects.create(rows=[sample_row(semester_label="2024 Fall")])

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"][0]["id"], str(project.pk))
        share.refresh_from_db()
        self.assertNotIn("id", share.rows[0])

    def test_get_share_does_not_backfill_a_project_of_an_unpublished_semester(self):
        hidden = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=False)
        Project.objects.create(semester=hidden, class_code="ENGR 120", team_number="T01", project_title="Hidden")
        share = PastProjectShare.objects.create(rows=[sample_row(semester_label="2024 Fall")])

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("id", response.data["rows"][0])
        self.assertEqual(response.data["rows"][0]["project_title"], "Shared Project")

    def test_get_share_marks_owner_can_edit(self):
        share = PastProjectShare.objects.create(rows=[sample_row()], created_by=self.member)

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_edit"])

    def test_get_share_marks_non_owner_can_edit_false(self):
        other = Member.objects.create_user(password="OtherPass123!", is_active=True)
        share = PastProjectShare.objects.create(rows=[sample_row()], created_by=other)

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["can_edit"])

    def test_get_share_is_public(self):
        # Viewing a shared snapshot does not require authentication.
        share = PastProjectShare.objects.create(rows=[sample_row()], note="Visible to anyone")
        anon = APIClient()

        response = anon.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["note"], "Visible to anyone")
        self.assertFalse(response.data["can_edit"])

    def test_get_unknown_share_returns_404(self):
        import uuid

        response = self.client.get(f"/projects/past-shares/{uuid.uuid4()}/")

        self.assertEqual(response.status_code, 404)

    def test_patch_own_share_rejects_empty_rows(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {"rows": [], "version": share.version},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)
        share.refresh_from_db()
        self.assertEqual(len(share.rows), 1)
