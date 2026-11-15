from apps.projects.models import PastProjectShare

from ..shares.share_helpers import PastProjectShareTestCase, sample_row


class PastProjectShareContentTests(PastProjectShareTestCase):
    def test_note_is_sanitized_on_patch(self):
        share = PastProjectShare.objects.create(
            name="Mine", rows=[sample_row()], note="<b>old</b>", created_by=self.member
        )

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {
                "note": "<strong>new</strong><script>alert(1)</script>",
                "version": share.version,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<strong>new</strong>", response.data["note"])
        self.assertNotIn("<script", response.data["note"])
        share.refresh_from_db()
        self.assertNotIn("<script", share.note)

    def test_patch_own_share_updates_note_and_rows(self):
        share = PastProjectShare.objects.create(
            name="Mine", rows=[sample_row()], note="Old note", details_text="Old details", created_by=self.member
        )
        self.catalog["T09"].project_title = "Added Project"
        self.catalog["T09"].save(update_fields=["project_title"])
        next_rows = [sample_row(team_number="T09", project_title="Added Project")]

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {
                "name": "Updated name",
                "note": "Updated note",
                "rows": next_rows,
                "version": share.version,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_edit"])
        self.assertEqual(response.data["name"], "Updated name")
        self.assertEqual(response.data["note"], "Updated note")
        self.assertEqual(response.data["rows"][0]["project_title"], "Added Project")
        self.assertEqual(response.data["version"], 2)
        share.refresh_from_db()
        self.assertEqual(share.name, "Updated name")
        self.assertEqual(share.note, "Updated note")
        self.assertEqual(share.details_text, "Old details")
        self.assertEqual([row["id"] for row in share.rows], [str(self.catalog["T09"].pk)])

    def test_patch_blank_name_rederives_from_the_saved_note(self):
        share = PastProjectShare.objects.create(
            name="Shared Project",
            rows=[sample_row(), sample_row(team_number="T02")],
            note="<div>Keysight picks</div><div>second line</div>",
            created_by=self.member,
        )

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/", {"name": "  ", "version": share.version}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Keysight picks")
        share.refresh_from_db()
        self.assertEqual(share.name, "Keysight picks")
