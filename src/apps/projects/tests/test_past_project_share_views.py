from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.projects.models import PastProjectShare, Project, Semester
from apps.projects.serializers.past_project_share import (
    NOTE_MAX_LENGTH,
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

    def test_create_without_name_derives_default_from_note(self):
        response = self.client.post(
            "/projects/past-shares/",
            {"rows": [sample_row()], "note": "<div>Spring 2026 finalists shortlist</div>"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Spring 2026 finalists shortlist")

    def test_create_blank_name_falls_back_to_first_project_title(self):
        # No name and no note → default from the first row's project title.
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(name="", note=""),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.name, "Shared Project")

    def test_create_whitespace_name_derives_default(self):
        response = self.client.post("/projects/past-shares/", sample_payload(name="   ", note=""), format="json")
        self.assertEqual(response.status_code, 201)
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.name, "Shared Project")

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
            {"details_text": "<mark>new</mark><script>alert(1)</script>"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<mark>new</mark>", response.data["details_text"])
        self.assertNotIn("<script", response.data["details_text"])
        share.refresh_from_db()
        self.assertNotIn("<script", share.details_text)

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
            {"note": "<strong>new</strong><script>alert(1)</script>"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<strong>new</strong>", response.data["note"])
        self.assertNotIn("<script", response.data["note"])
        share.refresh_from_db()
        self.assertNotIn("<script", share.note)

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

    def test_create_round_trips_is_presenting(self):
        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(rows=[sample_row(is_presenting="Yes")]),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rows"][0]["is_presenting"], "Yes")
        share = PastProjectShare.objects.get(pk=response.data["id"])
        self.assertEqual(share.rows[0]["is_presenting"], "Yes")

    def test_create_round_trips_project_id(self):
        project_id = "11111111-1111-4111-8111-111111111111"

        response = self.client.post(
            "/projects/past-shares/",
            sample_payload(rows=[sample_row(id=project_id)]),
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
        # "" for them rather than erroring on the missing key.
        share = PastProjectShare.objects.create(rows=[sample_row(semester_label="2025 Spring")])

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"][0]["is_presenting"], "")
        self.assertNotIn("id", response.data["rows"][0])

    def test_get_share_backfills_missing_project_id_from_stable_key(self):
        semester = Semester.objects.create(year=2025, season=Semester.Season.SPRING)
        project = Project.objects.create(
            semester=semester,
            class_code="ENGR 120",
            team_number="T01",
            project_title="Current Project",
            source=Project.Source.SHEET,
        )
        share = PastProjectShare.objects.create(rows=[sample_row(semester_label="2025 Spring")])

        response = self.client.get(f"/projects/past-shares/{share.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"][0]["id"], str(project.pk))
        share.refresh_from_db()
        self.assertNotIn("id", share.rows[0])

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
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_edit"])
        self.assertEqual(response.data["name"], "Updated name")
        self.assertEqual(response.data["note"], "Updated note")
        self.assertEqual(response.data["details_text"], "Updated project details")
        self.assertEqual(response.data["rows"][0]["project_title"], "Added Project")
        share.refresh_from_db()
        self.assertEqual(share.name, "Updated name")
        self.assertEqual(share.note, "Updated note")
        self.assertEqual(share.details_text, "Updated project details")
        self.assertEqual(share.rows, next_rows)

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
            f"/projects/past-shares/{share.pk}/", {"note": "Only the note changed"}, format="json"
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
            sample_payload(name="Replaced", note="Replaced note", rows=[sample_row(team_number="T42")]),
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
        # (here, no note → the first project title) rather than 400.
        share = PastProjectShare.objects.create(name="Old", rows=[sample_row()], created_by=self.member)

        response = self.client.put(f"/projects/past-shares/{share.pk}/", {"rows": [sample_row()]}, format="json")

        self.assertEqual(response.status_code, 200)
        share.refresh_from_db()
        self.assertEqual(share.name, "Shared Project")

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
