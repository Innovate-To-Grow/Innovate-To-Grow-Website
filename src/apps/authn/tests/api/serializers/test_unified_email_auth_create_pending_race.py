from __future__ import annotations

from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from rest_framework import serializers

from apps.authn.tests.api.serializers.test_coverage_gaps import Member


# ---------------------------------------------------------------------------
# serializers/email_code/auth.py:81  (IntegrityError -> pending then found)
# ---------------------------------------------------------------------------
class UnifiedEmailAuthCreatePendingRaceTests(TestCase):
    def test_create_pending_integrity_then_pending_found(self):
        """auth.py:76-81 — ContactEmail.create IntegrityError, pending found -> reuse it."""
        from apps.authn.serializers.email_code.auth import UnifiedEmailAuthRequestSerializer

        pending = Member.objects.create_user(first_name="", last_name="", is_active=False)
        serializer = UnifiedEmailAuthRequestSerializer()

        with (
            patch(
                "apps.authn.serializers.email_code.auth.claim_unclaimed_contact_email",
                return_value=None,
            ),
            patch(
                "apps.authn.serializers.email_code.auth.get_pending_registration_member",
                side_effect=[None, pending],
            ),
            patch("apps.authn.models.ContactEmail.objects.create", side_effect=IntegrityError("dup")),
        ):
            result = serializer._create_pending_member("authrace@example.com")

        self.assertEqual(result.pk, pending.pk)

    def test_create_pending_integrity_no_pending_raises(self):
        """auth.py:82 — IntegrityError and no pending -> ValidationError."""
        from apps.authn.serializers.email_code.auth import UnifiedEmailAuthRequestSerializer

        serializer = UnifiedEmailAuthRequestSerializer()
        with (
            patch(
                "apps.authn.serializers.email_code.auth.claim_unclaimed_contact_email",
                return_value=None,
            ),
            patch(
                "apps.authn.serializers.email_code.auth.get_pending_registration_member",
                side_effect=[None, None],
            ),
            patch("apps.authn.models.ContactEmail.objects.create", side_effect=IntegrityError("dup")),
        ):
            with self.assertRaises(serializers.ValidationError):
                serializer._create_pending_member("authrace2@example.com")
