"""Share notes and project detail text: length caps and HTML sanitization on create and update."""

from apps.projects.models import PastProjectShare
from apps.projects.serializers.past_project_share import (
    DETAILS_TEXT_MAX_LENGTH,
    NOTE_MAX_LENGTH,
)

from .share_helpers import PastProjectShareTestCase, sample_payload, sample_row


class PastProjectShareContentTests(PastProjectShareTestCase):
    """Share notes and project detail text: length caps and HTML sanitization on create and update."""

    def test_note_optional_blank(self):
        response = self.client.post("/projects/past-shares/", sample_payload(), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["note"], "")
        self.assertEqual(response.data["details_text"], "")
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.note, "")
        self.assertEqual(share.details_text, "")

    def test_details_text_is_sanitized_on_create(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(
                details_text=(
                    "<mark>Keep</mark><script>alert(1)</script><b>bold</b>"
                    '<span onclick="x">drop</span>'
                    '<a href="/past-projects/project/11111111-1111-4111-8111-111111111111">Individual Link</a>'
                    '<a href="javascript:alert(1)">bad</a>'
                ),
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        stored = response.data["details_text"]
        # Allowlisted markup survives; script/span and event handlers are stripped.
        self.assertIn("<mark>Keep</mark>", stored)
        self.assertIn("<b>bold</b>", stored)
        self.assertIn(
            '<a href="/past-projects/project/11111111-1111-4111-8111-111111111111">Individual Link</a>',
            stored,
        )
        self.assertNotIn("<script", stored)
        self.assertNotIn("onclick", stored)
        self.assertNotIn("<span", stored)
        self.assertNotIn("javascript:", stored)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertNotIn("<script", share.details_text)

    def test_note_is_sanitized_but_preserves_safe_individual_links(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(
                note=(
                    "<strong>Project 1</strong>"
                    '<a href="/past-projects/project/11111111-1111-4111-8111-111111111111">Individual Link</a>'
                    '<a href="javascript:alert(1)">bad</a>'
                ),
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn(
            '<a href="/past-projects/project/11111111-1111-4111-8111-111111111111">Individual Link</a>',
            response.data["note"],
        )
        self.assertNotIn("javascript:", response.data["note"])

    def test_details_text_is_sanitized_on_patch(self):
        share = PastProjectShare.objects.create(
            name="Mine", rows=[sample_row()], details_text="<b>old</b>", created_by=self.member
        )

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {
                "details_text": "<mark>new</mark><script>alert(1)</script>",
                "version": share.version,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<mark>new</mark>", response.data["details_text"])
        self.assertNotIn("<script", response.data["details_text"])
        share.refresh_from_db()
        self.assertNotIn("<script", share.details_text)

    def test_details_text_at_cap_is_accepted(self):
        details_text = "x" * DETAILS_TEXT_MAX_LENGTH

        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(details_text=details_text),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["details_text"]), DETAILS_TEXT_MAX_LENGTH)

    def test_details_text_over_cap_is_rejected(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(details_text="x" * 2_000_001),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("details_text", response.data)

    def test_large_generated_details_text_is_accepted(self):
        # A generated detail for many projects with long abstracts can be hundreds of KB; the
        # cap must not reject a legitimate large share.
        big_detail = "Project 1\nAbstract: " + ("lorem ipsum " * 40000)  # ~480 KB, well-formed text
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(details_text=big_detail),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertGreater(len(response.data["details_text"]), 100_000)

    def test_note_at_cap_is_accepted(self):
        note = "x" * NOTE_MAX_LENGTH

        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(note=note),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["note"]), NOTE_MAX_LENGTH)

    def test_note_length_validation(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(note="x" * (NOTE_MAX_LENGTH + 1)),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("note", response.data)

    def test_note_round_trips_rich_text(self):
        # The share-level note is rich text; allowlisted emphasis persists through create + GET.
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(note="<strong>Review</strong> these <mark>finalists</mark>"),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["note"], "<strong>Review</strong> these <mark>finalists</mark>")
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.note, "<strong>Review</strong> these <mark>finalists</mark>")

    def test_note_preserves_curation_block_marker(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(
                note='<div data-past-project-note-curation="project-summary"><strong>Project 1</strong></div>'
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn('data-past-project-note-curation="project-summary"', response.data["note"])
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertIn('data-past-project-note-curation="project-summary"', share.note)

    def test_note_is_sanitized_on_create(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(
                note='<mark>Keep</mark><script>alert(1)</script><b>bold</b><span onclick="x">drop</span>',
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        stored = response.data["note"]
        # Allowlisted markup survives; script/span and event handlers are stripped.
        self.assertIn("<mark>Keep</mark>", stored)
        self.assertIn("<b>bold</b>", stored)
        self.assertNotIn("<script", stored)
        self.assertNotIn("onclick", stored)
        self.assertNotIn("<span", stored)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertNotIn("<script", share.note)

    def test_note_strips_dangerous_attributes_from_allowed_tags(self):
        # The allowlist permits <a href> and <div data-past-project-note-curation>; an event-handler
        # or style on those *allowed* tags must still be stripped (the existing onclick test only
        # covers a disallowed <span>, which bleach removes wholesale). This pins the tight per-tag
        # attribute allowlist so a future widening of DETAILS_ALLOWED_ATTRIBUTES is caught.
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(
                note=(
                    '<a href="/past-projects/project/x" onclick="steal()" target="_blank" style="x">link</a>'
                    '<div data-past-project-note-curation="ok" onmouseover="steal()" style="x">block</div>'
                ),
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        stored = response.data["note"]
        # The allowed attributes survive...
        self.assertIn('href="/past-projects/project/x"', stored)
        self.assertIn('data-past-project-note-curation="ok"', stored)
        # ...but every event handler / style / unlisted attribute on those allowed tags is gone.
        self.assertNotIn("onclick", stored)
        self.assertNotIn("onmouseover", stored)
        self.assertNotIn("style", stored)
        self.assertNotIn("target", stored)

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
        next_rows = [sample_row(team_number="T09", project_title="Added Project")]

        response = self.client.patch(
            f"/projects/past-shares/{share.pk}/",
            {
                "name": "Updated name",
                "note": "Updated note",
                "details_text": "Updated project details",
                "rows": next_rows,
                "version": share.version,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_edit"])
        self.assertEqual(response.data["name"], "Updated name")
        self.assertEqual(response.data["note"], "Updated note")
        self.assertEqual(response.data["details_text"], "Updated project details")
        self.assertEqual(response.data["rows"][0]["project_title"], "Added Project")
        self.assertEqual(response.data["version"], 2)
        share.refresh_from_db()
        self.assertEqual(share.name, "Updated name")
        self.assertEqual(share.note, "Updated note")
        self.assertEqual(share.details_text, "Updated project details")
        self.assertEqual(share.rows, next_rows)

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
