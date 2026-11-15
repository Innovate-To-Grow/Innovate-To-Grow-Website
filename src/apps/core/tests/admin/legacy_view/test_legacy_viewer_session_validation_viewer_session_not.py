from datetime import timedelta
from unittest.mock import patch

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import Client, override_settings
from django.utils import timezone

from apps.core.models import LegacyAccessGrant
from apps.core.services.legacy_access import (
    LegacyViewerAccessDenied,
    exchange_legacy_access_code,
    issue_legacy_access_grant,
)
from apps.core.services.legacy_access.sessions import (
    _discard_viewer_session,
    create_viewer_session,
)
from apps.core.tests.admin.legacy_view.test_legacy_viewer_session_validation import _LegacyViewerSessionValidationCase
from apps.event.tests.helpers import make_admin


@override_settings(LEGACY_VIEW_ENABLED=True)
class LegacyViewerSessionValidationTests(_LegacyViewerSessionValidationCase):
    def test_viewer_session_is_not_created_for_nearly_expired_source(self):
        now = timezone.now()

        with self.assertRaisesMessage(LegacyViewerAccessDenied, "about to expire"):
            create_viewer_session(self.user, self.source_key, now + timedelta(milliseconds=500), now=now)
        self.assertEqual(Session.objects.count(), 1)

    def test_discard_failure_is_swallowed(self):
        with patch("apps.core.services.legacy_access.sessions._session_store", side_effect=RuntimeError("db down")):
            self.assertIsNone(_discard_viewer_session("any-session-key-0123456789"))

    def test_grant_requires_core_access(self):
        request = self._launch_request()
        request.user = make_admin(apps=["cms"], email="legacy-cms@example.com")

        with self.assertRaisesMessage(LegacyViewerAccessDenied, "Core admin access is required."):
            issue_legacy_access_grant(request)
        self.assertFalse(LegacyAccessGrant.objects.exists())

    def test_grant_requires_persisted_session(self):
        request = self._launch_request()
        request.session = SessionStore()

        with self.assertRaisesMessage(LegacyViewerAccessDenied, "persisted admin session is required"):
            issue_legacy_access_grant(request)

    def test_grant_requires_session_belonging_to_requesting_user(self):
        other_client = Client()
        other_client.force_login(make_admin(apps=["core"], email="legacy-thief@example.com"))
        request = self._launch_request()
        request.session = other_client.session

        with self.assertRaisesMessage(LegacyViewerAccessDenied, "no longer valid"):
            issue_legacy_access_grant(request)
        self.assertFalse(LegacyAccessGrant.objects.exists())

    def test_grant_refused_when_source_session_is_expiring_now(self):
        # Covers the race where the source session expires between validation and issuance.
        now = timezone.now()

        with (
            patch("apps.core.services.legacy_access.grants.timezone.now", return_value=now),
            patch("apps.core.services.legacy_access.grants.database_session_expiry", return_value=now),
            patch("apps.core.services.legacy_access.grants.source_session_is_valid", return_value=True),
            self.assertRaisesMessage(LegacyViewerAccessDenied, "about to expire"),
        ):
            issue_legacy_access_grant(self._launch_request())

    def test_exchange_rejects_non_string_empty_and_oversized_codes_without_db_lookup(self):
        for code in (None, 123, "", "x" * 257):
            with self.subTest(code=repr(code)[:20]), self.assertRaises(LegacyViewerAccessDenied):
                exchange_legacy_access_code(code)

    def test_exchange_after_core_access_revoked_consumes_code_but_denies(self):
        code = issue_legacy_access_grant(self._launch_request()).code
        self.user.admin_apps = ["cms"]
        self.user.save(update_fields=["admin_apps"])

        with self.assertRaisesMessage(LegacyViewerAccessDenied, "no longer valid"):
            exchange_legacy_access_code(code)
        self.assertIsNotNone(LegacyAccessGrant.objects.get().consumed_at)
        self.assertEqual(Session.objects.count(), 1)
