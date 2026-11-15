"""Managing shares: share URLs, listing mine, update with version checks, delete, and throttling."""

from django.test import override_settings
from rest_framework.test import APIClient

from apps.projects.models import PastProjectShare
from apps.projects.serializers.past_project_share import (
    PastProjectShareListSerializer,
    PastProjectShareSerializer,
)

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
        data = PastProjectShareListSerializer(PastProjectShare.objects.summaries().get(pk=share.pk)).data
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
