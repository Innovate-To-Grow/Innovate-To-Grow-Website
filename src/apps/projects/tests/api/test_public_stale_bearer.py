"""A stale stored session must not break the public project endpoints.

The SPA sends whatever access token local storage holds with every request, and DRF authenticates before it
checks permissions. The listing and detail reads never look at the caller, so they run no authentication. The
shared-snapshot detail read reports ``can_edit`` for the caller, so it honours a valid token and treats a bad one
as anonymous; changing a share still needs a valid token.
"""

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.authn.models import Member
from apps.authn.tests.stale_bearer import (
    assert_stale_bearer_reads_as_anonymous,
    stale_bearer_headers,
    valid_bearer_header,
)
from apps.projects.models import PastProjectShare, Project, Semester

ROW = {
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


class PublicProjectEndpointsStaleBearerTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.semester = Semester.objects.create(year=2025, season=1, is_published=True)
        self.project = Project.objects.create(semester=self.semester, project_title="Solar", team_number="1")

    def assert_reads_as_anonymous(self, url):
        assert_stale_bearer_reads_as_anonymous(self, lambda **extra: self.client.get(url, **extra))

    def test_past_projects(self):
        self.assert_reads_as_anonymous("/projects/past/")

    def test_all_past_projects(self):
        self.assert_reads_as_anonymous("/projects/past-all/")

    def test_compact_past_projects(self):
        self.assert_reads_as_anonymous("/projects/archive/")

    def test_project_detail(self):
        self.assert_reads_as_anonymous(f"/projects/{self.project.pk}/")

    def test_missing_project_detail(self):
        self.assert_reads_as_anonymous(f"/projects/{uuid.uuid4()}/")


class PastProjectShareDetailAuthTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.owner = Member.objects.create_user(password="SharePass123!", is_active=True)
        self.other = Member.objects.create_user(password="SharePass123!", is_active=True)
        self.share = PastProjectShare.objects.create(name="Finalists", rows=[ROW], created_by=self.owner)
        self.url = f"/projects/past-shares/{self.share.pk}/"

    def test_stale_bearer_reads_the_snapshot_as_anonymous(self):
        assert_stale_bearer_reads_as_anonymous(self, lambda **extra: self.client.get(self.url, **extra))

    def test_stale_bearer_is_not_the_owner(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                response = self.client.get(self.url, HTTP_AUTHORIZATION=header)

                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.data["can_edit"])

    def test_valid_bearer_of_the_owner_can_edit(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION=valid_bearer_header(self.owner))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_edit"])

    def test_valid_bearer_of_another_member_cannot_edit(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION=valid_bearer_header(self.other))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["can_edit"])

    def test_changing_a_share_still_needs_a_valid_token(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                patched = self.client.patch(
                    self.url, {"name": "Hijacked", "version": 1}, format="json", HTTP_AUTHORIZATION=header
                )
                deleted = self.client.delete(self.url, HTTP_AUTHORIZATION=header)

                self.assertEqual(patched.status_code, 401)
                self.assertEqual(deleted.status_code, 401)
        self.assertEqual(PastProjectShare.objects.get(pk=self.share.pk).name, "Finalists")

    def test_anonymous_cannot_change_a_share(self):
        self.assertEqual(self.client.patch(self.url, {"name": "Hijacked"}, format="json").status_code, 401)
        self.assertEqual(self.client.delete(self.url).status_code, 401)

    def test_owner_with_a_valid_token_can_still_delete(self):
        response = self.client.delete(self.url, HTTP_AUTHORIZATION=valid_bearer_header(self.owner))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(PastProjectShare.objects.filter(pk=self.share.pk).exists())
