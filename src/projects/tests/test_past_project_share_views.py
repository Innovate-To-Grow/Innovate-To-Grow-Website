from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from projects.models import PastProjectShare


def sample_row(**overrides):
    row = {
        "semester_label": "2025-1 Spring",
        "class_code": "ENGR 120",
        "team_number": "T01",
        "team_name": "Team Alpha",
        "project_title": "Shared Project",
        "organization": "Acme",
        "industry": "Technology",
        "abstract": "A project abstract.",
        "student_names": "Alice, Bob",
    }
    row.update(overrides)
    return row


class PastProjectShareAPIViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_create_share_returns_uuid_and_url(self):
        response = self.client.post("/projects/past-shares/", {"rows": [sample_row()]}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("id", response.data)
        self.assertIn("share_url", response.data)
        self.assertEqual(len(response.data["rows"]), 1)
        self.assertTrue(PastProjectShare.objects.filter(pk=response.data["id"]).exists())

    def test_create_share_requires_rows(self):
        response = self.client.post("/projects/past-shares/", {"rows": []}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)

    def test_create_share_validates_row_shape(self):
        response = self.client.post(
            "/projects/past-shares/",
            {"rows": [sample_row(project_title=""), {"team_name": "Missing fields"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)

    def test_create_share_rejects_more_than_1000_rows(self):
        rows = [sample_row(team_number=f"T{i:03d}") for i in range(1001)]

        response = self.client.post("/projects/past-shares/", {"rows": rows}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)

    def test_get_share_returns_saved_rows(self):
        share = PastProjectShare.objects.create(rows=[sample_row(), sample_row(team_number="T02")])

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["rows"]), 2)
        self.assertEqual(response.data["rows"][1]["team_number"], "T02")

    def test_get_unknown_share_returns_404(self):
        import uuid

        response = self.client.get(f"/projects/past-shares/{uuid.uuid4()}/")

        self.assertEqual(response.status_code, 404)

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {
                **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
                "past_project_share": "1/minute",
            },
        }
    )
    def test_create_share_is_throttled(self):
        first = self.client.post("/projects/past-shares/", {"rows": [sample_row()]}, format="json")
        second = self.client.post("/projects/past-shares/", {"rows": [sample_row(team_number="T02")]}, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 429)
