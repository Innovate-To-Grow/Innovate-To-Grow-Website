from unittest.mock import patch

from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.tests.request_limits.helpers import view_limit
from apps.projects.models import PastProjectShare
from apps.projects.serializers.past_project_share import (
    StalePastProjectShareSnapshot,
)
from apps.projects.services.shares.names import DEFAULT_SHARE_NAME

from .share_helpers import Member, PastProjectShareTestCase, sample_payload, sample_row


class PastProjectShareManageTests(PastProjectShareTestCase):
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

    @view_limit(**{"view-past-project-share": (1, 60)})
    def test_create_share_is_throttled_for_authenticated_user(self):
        first = self.client.post("/projects/past-shares/", sample_payload(), format="json")
        second = self.client.post(
            "/projects/past-shares/", sample_payload(rows=[sample_row(team_number="T02")]), format="json"
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 429)

    @view_limit(**{"view-past-project-share": (1, 60)})
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
