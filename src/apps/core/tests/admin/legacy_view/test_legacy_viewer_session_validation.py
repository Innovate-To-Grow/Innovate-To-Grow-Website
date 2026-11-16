from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import HASH_SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.core.services.legacy_access import (
    LEGACY_VIEWER_COOKIE_NAME,
    LegacyViewerAccessDenied,
    exchange_legacy_access_code,
    issue_legacy_access_grant,
    require_legacy_viewer,
)
from apps.core.services.legacy_access.sessions import (
    database_session_expiry,
    source_session_is_valid,
)
from apps.core.tests.admin.legacy_view.test_access import _MISSING
from apps.event.tests.helpers import make_admin


class _LegacyViewerSessionValidationCase(TestCase):
    def setUp(self):
        self.user = make_admin(apps=["core"], email="legacy-session@example.com")
        self.client.force_login(self.user)
        self.source_key = self.client.session.session_key
        self.source_expiry = Session.objects.get(session_key=self.source_key).expire_date

    def _launch_request(self):
        request = RequestFactory().post("/admin/legacy-view/")
        request.user = self.user
        request.session = self.client.session
        return request

    def _viewer_cookie_request(self, session_key):
        return RequestFactory().get("/", HTTP_COOKIE=f"{LEGACY_VIEWER_COOKIE_NAME}={session_key}")

    def _viewer_session_key(self):
        code = issue_legacy_access_grant(self._launch_request()).code
        return exchange_legacy_access_code(code).session_key

    def _forged_viewer_session(self, **overrides):
        now = timezone.now()
        data = {
            "legacy_viewer_version": 1,
            "legacy_viewer_user_id": str(self.user.pk),
            "legacy_viewer_source_session_key": self.source_key,
            "legacy_viewer_source_expires_at": self.source_expiry.timestamp(),
            "legacy_viewer_expires_at": (now + timedelta(minutes=30)).timestamp(),
        }
        data.update(overrides)
        data = {key: value for key, value in data.items() if value is not _MISSING}
        store = SessionStore()
        store.update(data)
        store.create()
        return store.session_key

    def assert_denied_and_discarded(self, session_key, message):
        with self.assertRaisesMessage(LegacyViewerAccessDenied, message):
            require_legacy_viewer(self._viewer_cookie_request(session_key))
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())


@override_settings(LEGACY_VIEW_ENABLED=True)
class LegacyViewerSessionValidationTests(_LegacyViewerSessionValidationCase):
    def test_valid_forged_shape_is_accepted_and_cached_on_request(self):
        request = self._viewer_cookie_request(self._forged_viewer_session())

        self.assertEqual(require_legacy_viewer(request).pk, self.user.pk)
        with patch("apps.core.services.legacy_access.sessions._load_session") as load_session:
            self.assertEqual(require_legacy_viewer(request).pk, self.user.pk)
        load_session.assert_not_called()

    @override_settings(LEGACY_VIEW_ENABLED="off")
    def test_disabled_flag_denies_even_a_valid_viewer_session(self):
        session_key = self._forged_viewer_session()

        with self.assertRaisesMessage(LegacyViewerAccessDenied, "disabled"):
            require_legacy_viewer(self._viewer_cookie_request(session_key))

    def test_missing_short_and_overlong_cookies_are_denied(self):
        requests = (
            RequestFactory().get("/"),
            self._viewer_cookie_request("short"),
            self._viewer_cookie_request("a" * 129),
            self._viewer_cookie_request("nonexistentsessionkey0123456789ab"),
        )
        for request in requests:
            with self.subTest(cookie=request.COOKIES.get(LEGACY_VIEWER_COOKIE_NAME)):
                with self.assertRaisesMessage(LegacyViewerAccessDenied, "valid legacy viewer session is required"):
                    require_legacy_viewer(request)

    def test_admin_session_cookie_cannot_be_replayed_as_viewer_cookie(self):
        with self.assertRaisesMessage(LegacyViewerAccessDenied, "valid legacy viewer session is required"):
            require_legacy_viewer(self._viewer_cookie_request(self.source_key))
        self.assertTrue(Session.objects.filter(session_key=self.source_key).exists())

    def test_session_backend_failure_fails_closed(self):
        session_key = self._viewer_session_key()

        with (
            patch("apps.core.services.legacy_access.sessions._session_store", side_effect=RuntimeError("db down")),
            self.assertRaises(LegacyViewerAccessDenied),
        ):
            require_legacy_viewer(self._viewer_cookie_request(session_key))

    def test_tampered_session_payloads_are_denied_and_discarded(self):
        cases = (
            {"legacy_viewer_expires_at": _MISSING},
            {"legacy_viewer_source_expires_at": "not-a-number"},
            {"legacy_viewer_user_id": _MISSING},
            {"legacy_viewer_source_session_key": _MISSING},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assert_denied_and_discarded(
                    self._forged_viewer_session(**overrides), "valid legacy viewer session is required"
                )

    def test_wrong_session_version_is_denied(self):
        session_key = self._forged_viewer_session(legacy_viewer_version=2)

        with self.assertRaisesMessage(LegacyViewerAccessDenied, "valid legacy viewer session is required"):
            require_legacy_viewer(self._viewer_cookie_request(session_key))

    def test_expired_viewer_or_source_timestamps_are_denied_and_discarded(self):
        past = (timezone.now() - timedelta(seconds=1)).timestamp()
        for overrides in ({"legacy_viewer_expires_at": past}, {"legacy_viewer_source_expires_at": past}):
            with self.subTest(overrides=overrides):
                self.assert_denied_and_discarded(self._forged_viewer_session(**overrides), "expired")

    def test_unknown_user_id_is_denied_and_discarded(self):
        for user_id in ("00000000-0000-4000-8000-000000000000", "not-a-uuid"):
            with self.subTest(user_id=user_id):
                session_key = self._forged_viewer_session(legacy_viewer_user_id=user_id)

                self.assert_denied_and_discarded(session_key, "no longer valid")

    def test_logout_of_source_admin_session_revokes_viewer(self):
        session_key = self._viewer_session_key()

        self.client.logout()

        self.assert_denied_and_discarded(session_key, "no longer valid")

    def test_password_change_revokes_viewer_via_session_auth_hash(self):
        session_key = self._viewer_session_key()

        self.user.set_password("a-brand-new-password-123")
        self.user.save()

        self.assert_denied_and_discarded(session_key, "no longer valid")

    def test_viewer_bound_to_another_users_session_is_denied(self):
        other = make_admin(apps=["core"], email="legacy-other@example.com")
        session_key = self._forged_viewer_session(legacy_viewer_user_id=str(other.pk))

        self.assert_denied_and_discarded(session_key, "no longer valid")

    def test_source_session_without_auth_hash_is_rejected(self):
        store = SessionStore(session_key=self.source_key)
        store.pop(HASH_SESSION_KEY)
        store.save()

        self.assertFalse(source_session_is_valid(self.user, self.source_key, self.source_expiry))

    def test_source_session_validity_rejects_missing_or_past_expiry(self):
        now = timezone.now()

        self.assertTrue(source_session_is_valid(self.user, self.source_key, self.source_expiry, now=now))
        self.assertFalse(source_session_is_valid(self.user, self.source_key, None, now=now))
        self.assertFalse(source_session_is_valid(self.user, self.source_key, now, now=now))

    def test_database_session_expiry_denies_unknown_session(self):
        with self.assertRaisesMessage(LegacyViewerAccessDenied, "source admin session is unavailable"):
            database_session_expiry("missing-session-key-0123456789")
