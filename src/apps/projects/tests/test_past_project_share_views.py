from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.projects.models import PastProjectShare
from apps.projects.serializers.past_project_share import (
    PastProjectShareListSerializer,
    PastProjectShareSerializer,
)

Member = get_user_model()


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


def sample_payload(**overrides):
    payload = {"name": "My finalists", "rows": [sample_row()]}
    payload.update(overrides)
    return payload


class PastProjectShareAPIViewTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = Member.objects.create_user(password="SharePass123!", is_active=True)
        self.client.force_authenticate(user=self.member)

    def test_create_requires_auth_returns_401(self):
        anon = APIClient()
        response = anon.post("/projects/past-shares/", sample_payload(), format="json")
        self.assertEqual(response.status_code, 401)

    def test_create_share_returns_uuid_and_url(self):
        response = self.client.post("/projects/past-shares/", sample_payload(), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("id", response.data)
        self.assertIn("share_url", response.data)
        self.assertEqual(response.data["name"], "My finalists")
        self.assertEqual(len(response.data["rows"]), 1)
        self.assertTrue(PastProjectShare.objects.filter(pk=response.data["id"]).exists())

    def test_create_requires_name(self):
        response = self.client.post("/projects/past-shares/", {"rows": [sample_row()]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_create_rejects_blank_name(self):
        response = self.client.post("/projects/past-shares/", sample_payload(name=""), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_create_rejects_whitespace_name(self):
        response = self.client.post("/projects/past-shares/", sample_payload(name="   "), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_create_persists_trimmed_name(self):
        response = self.client.post(
            "/projects/past-shares/", sample_payload(name="  Spring finalists  "), format="json"
        )
        self.assertEqual(response.status_code, 201)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.name, "Spring finalists")

    def test_authenticated_create_persists_note_and_created_by(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(note="Projects to review with the team."),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["note"], "Projects to review with the team.")
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.note, "Projects to review with the team.")
        self.assertEqual(share.created_by, self.member)

    def test_note_optional_blank(self):
        response = self.client.post("/projects/past-shares/", sample_payload(), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["note"], "")
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.note, "")

    def test_note_length_validation(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(note="x" * 2001),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("note", response.data)

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

    def test_create_share_rejects_more_than_1000_rows(self):
        rows = [sample_row(team_number=f"T{i:03d}") for i in range(1001)]

        response = self.client.post("/projects/past-shares/", sample_payload(rows=rows), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)

    def test_get_share_returns_saved_rows(self):
        share = PastProjectShare.objects.create(rows=[sample_row(), sample_row(team_number="T02")])

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["rows"]), 2)
        self.assertEqual(response.data["rows"][1]["team_number"], "T02")
        self.assertFalse(response.data["can_edit"])

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

    @override_settings(FRONTEND_URL="https://i2g.example.edu/")
    def test_share_url_uses_frontend_origin(self):
        # share_url must point at the FRONTEND origin (the SPA route), not the API
        # host — otherwise the link lands on the Django admin 404 page. The
        # trailing slash on FRONTEND_URL is normalized away.
        share = PastProjectShare.objects.create(rows=[sample_row()])
        data = PastProjectShareSerializer(share).data
        self.assertEqual(data["share_url"], f"https://i2g.example.edu/past-projects/{share.pk}")

    @override_settings(FRONTEND_URL="")
    def test_share_url_falls_back_to_relative_path_without_request(self):
        # With FRONTEND_URL unset and no request in context, the serializer yields
        # a relative share URL rather than an absolute one.
        share = PastProjectShare.objects.create(rows=[sample_row()])
        data = PastProjectShareSerializer(share).data
        self.assertEqual(data["share_url"], f"/past-projects/{share.pk}")

    @override_settings(FRONTEND_URL="")
    def test_share_url_falls_back_to_request_origin_without_frontend_url(self):
        # With FRONTEND_URL unset but a request present, fall back to the request
        # origin (the dev / same-origin case).
        share = PastProjectShare.objects.create(rows=[sample_row()])
        response = self.client.get(f"/projects/past-shares/{share.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["share_url"].endswith(f"/past-projects/{share.pk}"))
        self.assertIn("http", response.data["share_url"])

    def test_create_without_request_context_sets_created_by_none(self):
        # The serializer is robust when used without a request (e.g. shell/scripts):
        # created_by stays None and the share still saves.
        serializer = PastProjectShareSerializer(data={"name": "Scripted", "rows": [sample_row()], "note": "scripted"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertIsNone(instance.created_by)
        self.assertEqual(instance.note, "scripted")

    # --- "my shares" list ---

    def test_mine_lists_only_my_shares(self):
        other = Member.objects.create_user(password="OtherPass123!", is_active=True)
        PastProjectShare.objects.create(name="Mine A", rows=[sample_row()], created_by=self.member)
        PastProjectShare.objects.create(name="Mine B", rows=[sample_row(), sample_row()], created_by=self.member)
        PastProjectShare.objects.create(name="Theirs", rows=[sample_row()], created_by=other)

        response = self.client.get("/projects/past-shares/mine/")

        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data}
        self.assertEqual(names, {"Mine A", "Mine B"})
        # Light serializer: row_count present, full rows omitted.
        item = next(i for i in response.data if i["name"] == "Mine B")
        self.assertEqual(item["row_count"], 2)
        self.assertNotIn("rows", item)

    def test_mine_requires_auth_returns_401(self):
        anon = APIClient()
        response = anon.get("/projects/past-shares/mine/")
        self.assertEqual(response.status_code, 401)

    @override_settings(FRONTEND_URL="")
    def test_list_serializer_shape_without_request(self):
        share = PastProjectShare.objects.create(name="Shape", rows=[sample_row()], created_by=self.member)
        data = PastProjectShareListSerializer(share).data
        self.assertEqual(data["share_url"], f"/past-projects/{share.pk}")
        self.assertEqual(data["row_count"], 1)
        self.assertEqual(data["name"], "Shape")

    @override_settings(FRONTEND_URL="https://i2g.example.edu")
    def test_list_serializer_share_url_uses_frontend_origin(self):
        share = PastProjectShare.objects.create(name="Shape", rows=[sample_row()], created_by=self.member)
        data = PastProjectShareListSerializer(share).data
        self.assertEqual(data["share_url"], f"https://i2g.example.edu/past-projects/{share.pk}")

    # --- owner-scoped delete ---

    def test_delete_own_share_returns_204(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)
        response = self.client.delete(f"/projects/past-shares/{share.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(PastProjectShare.objects.filter(pk=share.pk).exists())

    def test_delete_other_users_share_returns_404(self):
        other = Member.objects.create_user(password="OtherPass123!", is_active=True)
        share = PastProjectShare.objects.create(name="Theirs", rows=[sample_row()], created_by=other)
        response = self.client.delete(f"/projects/past-shares/{share.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PastProjectShare.objects.filter(pk=share.pk).exists())

    def test_delete_anonymous_returns_401(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)
        anon = APIClient()
        response = anon.delete(f"/projects/past-shares/{share.pk}/")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(PastProjectShare.objects.filter(pk=share.pk).exists())

    # --- owner-scoped edit ---

    def test_patch_own_share_updates_note_and_rows(self):
        share = PastProjectShare.objects.create(
            name="Mine", rows=[sample_row()], note="Old note", created_by=self.member
        )
        next_rows = [sample_row(team_number="T09", project_title="Added Project")]

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {"name": "Updated name", "note": "Updated note", "rows": next_rows},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_edit"])
        self.assertEqual(response.data["name"], "Updated name")
        self.assertEqual(response.data["note"], "Updated note")
        self.assertEqual(response.data["rows"][0]["project_title"], "Added Project")
        share.refresh_from_db()
        self.assertEqual(share.name, "Updated name")
        self.assertEqual(share.note, "Updated note")
        self.assertEqual(share.rows, next_rows)

    def test_patch_own_share_rejects_empty_rows(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)

        response = self.client.patch(f"/projects/past-shares/{share.pk}/", {"rows": []}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("rows", response.data)
        share.refresh_from_db()
        self.assertEqual(len(share.rows), 1)

    def test_patch_other_users_share_returns_404(self):
        other = Member.objects.create_user(password="OtherPass123!", is_active=True)
        share = PastProjectShare.objects.create(name="Theirs", rows=[sample_row()], note="Original", created_by=other)

        response = self.client.patch(f"/projects/past-shares/{share.pk}/", {"note": "Changed"}, format="json")

        self.assertEqual(response.status_code, 404)
        share.refresh_from_db()
        self.assertEqual(share.note, "Original")

    def test_patch_anonymous_returns_401(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)
        anon = APIClient()

        response = anon.patch(f"/projects/past-shares/{share.pk}/", {"note": "Changed"}, format="json")

        self.assertEqual(response.status_code, 401)
        share.refresh_from_db()
        self.assertEqual(share.note, "")

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {
                **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
                "past_project_share": "1/minute",
            },
        }
    )
    def test_create_share_is_throttled_for_authenticated_user(self):
        first = self.client.post("/projects/past-shares/", sample_payload(), format="json")
        second = self.client.post(
            "/projects/past-shares/", sample_payload(rows=[sample_row(team_number="T02")]), format="json"
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 429)
