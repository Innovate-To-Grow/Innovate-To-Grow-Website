from apps.event.models import CurrentProject
from apps.projects.models import PastProjectShare
from apps.projects.services.shares.names import DEFAULT_PROJECT_SHARE_NAME, DEFAULT_SHARE_NAME
from apps.projects.tests.api.share_content.test_past_project_share_current_rows import URL, CurrentShareRowsTestCase

from ..shares.share_helpers import sample_payload, sample_row


class CurrentShareRowsDefaultNameTests(CurrentShareRowsTestCase):
    """A curation saved without a name or any note text of the owner's is named after the rows it stores: one holding
    a current-semester project is not a list of past projects."""

    def test_create_names_a_curation_holding_a_current_project_a_project_curation(self):
        rows = [sample_row(id=str(self.catalog["T01"].pk)), self.current_row(self.fall["10"])]

        response = self.client.post(URL, sample_payload(name="", note="", rows=rows), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], DEFAULT_PROJECT_SHARE_NAME)
        self.assertEqual(PastProjectShare.objects.get(pk=response.data["id"]).name, "Project Curation")

    def test_create_names_from_the_stored_rows_not_the_rows_sent(self):
        # The archive has imported the team since the page listed it, so the share stores its archive row.
        self.import_fall_team("10", "Solar Kiln")

        response = self.client.post(
            URL, sample_payload(name="", rows=[self.current_row(self.fall["10"])]), format="json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rows"][0]["catalog"], "archive")
        self.assertEqual(response.data["name"], DEFAULT_SHARE_NAME)

    def test_create_still_takes_the_first_line_of_the_owners_note(self):
        response = self.client.post(
            URL,
            sample_payload(name="", note="<div>Fall picks</div>", rows=[self.current_row(self.fall["10"])]),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Fall picks")

    def test_clearing_the_name_names_the_curation_after_its_stored_rows(self):
        created = self.client.post(URL, sample_payload(rows=[self.current_row(self.fall["10"])]), format="json")

        response = self.client.patch(
            f"{URL}{created.data['id']}/", {"name": "", "version": created.data["version"]}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], DEFAULT_PROJECT_SHARE_NAME)

    def test_clearing_the_name_names_the_curation_after_the_rows_saved_with_it(self):
        created = self.client.post(URL, sample_payload(rows=[sample_row()]), format="json")
        share_url = f"{URL}{created.data['id']}/"

        added = self.client.patch(
            share_url,
            {"name": "", "rows": [sample_row(), self.current_row(self.fall["10"])], "version": 1},
            format="json",
        )
        removed = self.client.patch(share_url, {"name": "", "rows": [sample_row()], "version": 2}, format="json")

        self.assertEqual((added.status_code, added.data["name"]), (200, DEFAULT_PROJECT_SHARE_NAME))
        self.assertEqual((removed.status_code, removed.data["name"]), (200, DEFAULT_SHARE_NAME))

    def test_a_rows_only_edit_keeps_the_name(self):
        created = self.client.post(URL, sample_payload(name="", rows=[sample_row()]), format="json")

        response = self.client.patch(
            f"{URL}{created.data['id']}/",
            {"rows": [sample_row(), self.current_row(self.fall["10"])], "version": created.data["version"]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], DEFAULT_SHARE_NAME)


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
