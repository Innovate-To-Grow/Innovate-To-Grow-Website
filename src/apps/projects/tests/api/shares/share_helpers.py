"""Shared fixtures for the past-project share API tests."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import Project, Semester

Member = get_user_model()

# Team numbers the shared fixture puts in the published catalog. Shares store catalog rows, so a row a test posts
# must name one of these (or a project the test adds) to be accepted.
CATALOG_TEAM_NUMBERS = ("T01", "T02", "T09", "T42")


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


def catalog_project(semester, **overrides):
    """The published archive project ``sample_row(**overrides)`` describes."""
    fields = {key: value for key, value in sample_row(**overrides).items() if key not in {"semester_label", "id"}}
    return Project.objects.create(semester=semester, source=Project.Source.SHEET, **fields)


def sample_payload(**overrides):
    payload = {"name": "My finalists", "rows": [sample_row()]}
    payload.update(overrides)
    return payload


class PastProjectShareTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = Member.objects.create_user(password="SharePass123!", is_active=True)
        self.client.force_authenticate(user=self.member)
        self.semester = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_published=True)
        self.catalog = {
            team_number: catalog_project(self.semester, team_number=team_number) for team_number in CATALOG_TEAM_NUMBERS
        }
