"""Coverage tests for assorted authn service helpers."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.authn.services.email.auth_email import (
    claim_unclaimed_contact_email,
    get_pending_registration_member,
    get_unclaimed_contact_email,
    resolve_auth_email,
)
from apps.authn.services.members.accounts.create import CreateMemberService

Member = get_user_model()


def _member(email="primary@example.com", **kwargs):
    member = Member.objects.create_user(
        password="StrongPass123!",
        first_name=kwargs.pop("first_name", "First"),
        last_name=kwargs.pop("last_name", "Last"),
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )
    ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
    return member


class CreateMemberErrorPathTests(TestCase):
    def test_integrity_error_path(self):
        with patch(
            "apps.authn.services.members.accounts.create.Member.objects.create_user",
            side_effect=IntegrityError("dup key"),
        ):
            result = CreateMemberService.create_member(password="StrongPass123!", first_name="A", last_name="B")
        self.assertFalse(result["success"])
        self.assertIn("Database integrity error", result["error"])

    def test_validation_error_path(self):
        with patch(
            "apps.authn.services.members.accounts.create.Member.objects.create_user",
            side_effect=ValidationError("bad"),
        ):
            result = CreateMemberService.create_member(password="StrongPass123!", first_name="A", last_name="B")
        self.assertFalse(result["success"])
        self.assertIn("Validation error", result["error"])

    def test_unexpected_error_path(self):
        with patch(
            "apps.authn.services.members.accounts.create.Member.objects.create_user",
            side_effect=RuntimeError("boom"),
        ):
            result = CreateMemberService.create_member(password="StrongPass123!", first_name="A", last_name="B")
        self.assertFalse(result["success"])
        self.assertIn("Unexpected error", result["error"])


class AuthEmailHelperTests(TestCase):
    def test_resolve_auth_email_empty_returns_none(self):
        self.assertIsNone(resolve_auth_email(""))

    def test_get_unclaimed_contact_email_empty_returns_none(self):
        self.assertIsNone(get_unclaimed_contact_email(""))

    def test_get_unclaimed_contact_email_returns_match(self):
        ContactEmail.objects.create(email_address="unclaimed@example.com", email_type="primary", member=None)
        result = get_unclaimed_contact_email("Unclaimed@Example.com")
        self.assertIsNotNone(result)

    def test_claim_unclaimed_contact_email_empty_returns_none(self):
        member = _member()
        self.assertIsNone(claim_unclaimed_contact_email("", member=member))

    def test_claim_unclaimed_contact_email_no_match_returns_none(self):
        member = _member()
        self.assertIsNone(claim_unclaimed_contact_email("nothing@example.com", member=member))

    def test_get_pending_registration_member_empty_returns_none(self):
        self.assertIsNone(get_pending_registration_member(""))
