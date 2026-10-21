"""Shared fixtures for the past-project share API tests."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

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


class PastProjectShareTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = Member.objects.create_user(password="SharePass123!", is_active=True)
        self.client.force_authenticate(user=self.member)
