"""Managing shares: share URLs, listing mine, update with version checks, delete, and throttling."""

from unittest.mock import patch

from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.projects.models import PastProjectShare
from apps.projects.serializers.past_project_share import (
    PastProjectShareListSerializer,
    PastProjectShareSerializer,
    StalePastProjectShareSnapshot,
)
from apps.projects.services.share_names import DEFAULT_SHARE_NAME

from .share_helpers import Member, PastProjectShareTestCase, sample_payload, sample_row


class PastProjectShareManageTests(PastProjectShareTestCase):
    """Managing shares: share URLs, listing mine, update with version checks, delete, and throttling."""

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

    def test_mine_lists_the_most_recently_changed_first(self):
        older = PastProjectShare.objects.create(name="Created first", rows=[sample_row()], created_by=self.member)
        PastProjectShare.objects.create(name="Created second", rows=[sample_row()], created_by=self.member)
        # Editing the first share makes it the most recently changed.
        response = self.client.patch(
            f"/projects/past-shares/{older.pk}/", {"note": "Edited", "version": older.version}, format="json"
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/projects/past-shares/mine/")

        self.assertEqual([item["name"] for item in response.data], ["Created first", "Created second"])
        older.refresh_from_db()
        self.assertIn("updated_at", response.data[0])
        self.assertGreater(older.updated_at, older.created_at)

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

    def test_patch_single_field_preserves_others(self):
        # A true partial PATCH (only one field) must succeed even though name/rows are
        # required=True — confirms the update() override honors partial=True.
        share = PastProjectShare.objects.create(
            name="Keep name",
            rows=[sample_row()],
            note="Keep note",
            details_text="Keep details",
            created_by=self.member,
        )

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {"note": "Only the note changed", "version": share.version},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["note"], "Only the note changed")
        share.refresh_from_db()
        self.assertEqual(share.name, "Keep name")
        self.assertEqual(share.details_text, "Keep details")
        self.assertEqual(len(share.rows), 1)

    def test_put_replaces_the_whole_share(self):
        share = PastProjectShare.objects.create(
            name="Old", rows=[sample_row()], note="Old note", created_by=self.member
        )

        response = self.client.put(
            f"/projects/past-shares/{share.pk}/",
            sample_payload(
                name="Replaced",
                note="Replaced note",
                rows=[sample_row(team_number="T42")],
                version=share.version,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Replaced")
        share.refresh_from_db()
        self.assertEqual(share.name, "Replaced")
        self.assertEqual(share.note, "Replaced note")
        self.assertEqual(share.rows[0]["team_number"], "T42")

    def test_put_without_name_derives_default(self):
        # name is optional even on a full PUT: omitting it derives a default from the content
        # (here, no note → the generic title, never a project title) rather than 400.
        share = PastProjectShare.objects.create(name="Old", rows=[sample_row()], created_by=self.member)

        response = self.client.put(
            f"/projects/past-shares/{share.pk}/",
            {"rows": [sample_row()], "version": share.version},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        share.refresh_from_db()
        self.assertEqual(share.name, DEFAULT_SHARE_NAME)

    def test_patch_requires_version(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {"note": "Changed"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "version_required")

    def test_patch_rejects_stale_version_with_current_snapshot(self):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)
        first = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {"note": "First edit", "version": 1},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        current = self.client.get(f"/projects/past-shares/{share.pk}/")
        self.assertEqual(current.status_code, 200)

        stale = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {"note": "Stale edit", "version": 1},
            format="json",
        )

        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "stale_snapshot")
        self.assertEqual(stale.data["current"], current.data)

    @patch("apps.projects.serializers.past_project_share.PastProjectShareSerializer.update")
    def test_patch_stale_snapshot_deleted_during_update_returns_404(self, mock_update):
        share = PastProjectShare.objects.create(name="Mine", rows=[sample_row()], created_by=self.member)

        def delete_then_raise(*_args, **_kwargs):
            share.delete()
            raise StalePastProjectShareSnapshot

        mock_update.side_effect = delete_then_raise
        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {"note": "Stale edit", "version": share.version},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

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

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {
                **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
                "past_project_share": "1/minute",
            },
        }
    )
    def test_create_share_throttle_is_isolated_per_user(self):
        other = Member.objects.create_user(password="OtherPass123!", is_active=True)
        other_client = APIClient()
        other_client.force_authenticate(user=other)

        first = self.client.post("/projects/past-shares/", sample_payload(), format="json")
        other_first = other_client.post("/projects/past-shares/", sample_payload(), format="json")
        second = self.client.post(
            "/projects/past-shares/", sample_payload(rows=[sample_row(team_number="T02")]), format="json"
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(other_first.status_code, 201)
        self.assertEqual(second.status_code, 429)

    def test_create_share_accepts_real_jwt_access_token(self):
        client = APIClient()
        access_token = RefreshToken.for_user(self.member).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = client.post("/projects/past-shares/", sample_payload(), format="json")

        self.assertEqual(response.status_code, 201)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.created_by, self.member)
