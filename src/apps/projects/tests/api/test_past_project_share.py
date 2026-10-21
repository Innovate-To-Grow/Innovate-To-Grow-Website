from rest_framework.test import APIClient

from apps.projects.models import PastProjectShare
from apps.projects.serializers.past_project_share import (
    PastProjectShareSerializer,
)
from apps.projects.services.share_names import DEFAULT_SHARE_NAME

from .share_helpers import PastProjectShareTestCase, sample_payload, sample_row


class PastProjectShareCreateTests(PastProjectShareTestCase):
    """Creating a share: authentication, the derived default name, and who created it."""

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

    def test_create_without_name_derives_default_from_note(self):
        response = self.client.post(
            "/projects/past-shares/",
            {"rows": [sample_row()], "note": "<div>Spring 2026 finalists shortlist</div>"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Spring 2026 finalists shortlist")

    def test_create_blank_name_and_note_uses_generic_title_not_a_project_title(self):
        # Regression: a blank name and note used to name the whole curation after rows[0]'s project title,
        # which then titled the shared page and its PDF.
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(
                name="",
                note="",
                rows=[sample_row(project_title="Newest Project"), sample_row(team_number="T02")],
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.name, DEFAULT_SHARE_NAME)
        self.assertEqual(response.data["name"], DEFAULT_SHARE_NAME)

    def test_create_whitespace_name_derives_default(self):
        response = self.client.post("/projects/past-shares/", sample_payload(name="   ", note=""), format="json")
        self.assertEqual(response.status_code, 201)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.name, DEFAULT_SHARE_NAME)

    def test_create_note_with_only_inserted_projects_uses_generic_title(self):
        # "Insert projects into note" output is project data, not the curator's words.
        note = (
            '<div data-past-project-note-curation="project-summary"><div data-past-project-key="k1">'
            "<div><strong>Project 1</strong></div><div><strong>Project Title:</strong> Shared Project</div>"
            "</div></div>"
        )
        response = self.client.post("/projects/past-shares/", sample_payload(name="", note=note), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], DEFAULT_SHARE_NAME)

    def test_create_note_intro_before_inserted_projects_names_the_curation(self):
        note = (
            "<div>Western Digital capstones</div><br><br>"
            '<div data-past-project-note-curation="project-summary"><div data-past-project-key="k1">'
            "<div><strong>Project 1</strong></div></div></div>"
        )
        response = self.client.post("/projects/past-shares/", sample_payload(name="", note=note), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Western Digital capstones")

    def test_create_long_note_default_name_is_truncated(self):
        response = self.client.post(
            "/projects/past-shares/",
            {"rows": [sample_row()], "note": "<div>" + ("x" * 200) + "</div>"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        name = response.data["name"]
        self.assertLessEqual(len(name), 60)
        self.assertTrue(name.endswith("…"))

    def test_create_explicit_name_still_wins(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(name="Chosen name", note="<div>ignored for naming</div>"),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Chosen name")

    def test_create_persists_trimmed_name(self):
        response = self.client.post(
            "/projects/past-shares/", sample_payload(name="  Spring finalists  "), format="json"
        )
        self.assertEqual(response.status_code, 201)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.name, "Spring finalists")

    def test_create_without_request_context_sets_created_by_none(self):
        # The serializer is robust when used without a request (e.g. shell/scripts):
        # created_by stays None and the share still saves.
        serializer = PastProjectShareSerializer(
            data={
                "name": "Scripted",
                "rows": [sample_row()],
                "note": "scripted",
                "details_text": "scripted details",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertIsNone(instance.created_by)
        self.assertEqual(instance.note, "scripted")
        self.assertEqual(instance.details_text, "scripted details")

    def test_authenticated_create_persists_note_and_created_by(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(
                note="Projects to review with the team.",
                details_text="Past Projects Detail\nProject Title: Shared Project",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["note"], "Projects to review with the team.")
        self.assertEqual(response.data["details_text"], "Past Projects Detail\nProject Title: Shared Project")
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.note, "Projects to review with the team.")
        self.assertEqual(share.details_text, "Past Projects Detail\nProject Title: Shared Project")
        self.assertEqual(share.created_by, self.member)
