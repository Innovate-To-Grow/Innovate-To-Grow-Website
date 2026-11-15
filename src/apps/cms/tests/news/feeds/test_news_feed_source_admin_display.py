from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.cms.admin.news.feed_source import NewsFeedSourceAdmin
from apps.cms.admin.news.sync_log import NewsSyncLogAdmin
from apps.cms.models import NewsFeedSource, NewsSyncLog
from apps.cms.tests.news.site.test_admin import Member
from apps.event.tests.helpers import make_admin, make_superuser


class NewsFeedSourceAdminDisplayTests(TestCase):
    def setUp(self):
        self.admin = NewsFeedSourceAdmin(NewsFeedSource, AdminSite())

    def test_status_badge_active(self):
        source = NewsFeedSource(name="A", source_key="a", feed_url="https://x/feed", is_active=True)
        self.assertEqual(self.admin.status_badge(source), ("Active", "success"))

    def test_status_badge_inactive(self):
        source = NewsFeedSource(name="B", source_key="b", feed_url="https://x/feed", is_active=False)
        self.assertEqual(self.admin.status_badge(source), ("Inactive", "danger"))

    def test_sync_result_badge_never_synced(self):
        source = NewsFeedSource(name="C", source_key="c", feed_url="https://x/feed")
        self.assertEqual(self.admin.sync_result_badge(source), ("Never synced", "info"))

    def test_sync_result_badge_errors(self):
        source = NewsFeedSource(
            name="D",
            source_key="d",
            feed_url="https://x/feed",
            last_synced_at=timezone.now(),
            last_sync_errors="something failed",
        )
        self.assertEqual(self.admin.sync_result_badge(source), ("Error", "danger"))

    def test_sync_result_badge_warnings(self):
        source = NewsFeedSource(
            name="D",
            source_key="d-warning",
            feed_url="https://x/feed",
            last_synced_at=timezone.now(),
            last_sync_errors="Warning: article body used the RSS fallback",
        )
        self.assertEqual(self.admin.sync_result_badge(source), ("Warnings", "warning"))

    def test_sync_result_badge_first_attempt_error_is_not_never_synced(self):
        source = NewsFeedSource(
            name="D",
            source_key="d-first-failure",
            feed_url="https://x/feed",
            last_synced_at=None,
            last_sync_errors="HTTP Error 403: Forbidden",
        )
        self.assertEqual(self.admin.sync_result_badge(source), ("Error", "danger"))

    def test_sync_diagnostic_preview_normalizes_legacy_error_and_includes_warning(self):
        source = NewsFeedSource(
            name="D",
            source_key="d-preview",
            feed_url="https://x/feed",
            last_sync_errors="HTTP Error 403: Forbidden\nWarning: article body used the RSS fallback",
        )

        self.assertEqual(
            self.admin.sync_diagnostic_preview(source),
            "Error: HTTP Error 403: Forbidden | Warning: article body used the RSS fallback",
        )

    def test_sync_diagnostic_preview_truncates_long_error_detail(self):
        source = NewsFeedSource(
            name="D",
            source_key="d-long-error",
            feed_url="https://x/feed",
            last_sync_errors=f"Error: {'x' * 300}",
        )

        preview = self.admin.sync_diagnostic_preview(source)

        self.assertEqual(len(preview), 240)
        self.assertTrue(preview.endswith("…"))

    def test_sync_diagnostic_preview_without_diagnostics(self):
        source = NewsFeedSource(name="D", source_key="d-clean", feed_url="https://x/feed")

        self.assertEqual(self.admin.sync_diagnostic_preview(source), "-")

    def test_sync_result_badge_success(self):
        source = NewsFeedSource(
            name="E",
            source_key="e",
            feed_url="https://x/feed",
            last_synced_at=timezone.now(),
            last_sync_errors="",
        )
        self.assertEqual(self.admin.sync_result_badge(source), ("Success", "success"))

    def test_time_since_sync_never(self):
        source = NewsFeedSource(name="F", source_key="f", feed_url="https://x/feed")
        self.assertEqual(self.admin.time_since_sync(source), "-")

    def test_time_since_sync_with_timestamp(self):
        source = NewsFeedSource(
            name="G",
            source_key="g",
            feed_url="https://x/feed",
            last_synced_at=timezone.now() - timedelta(hours=2),
        )
        result = self.admin.time_since_sync(source)
        self.assertTrue(result.endswith("ago"))
        self.assertIn("hour", result)


class NewsSyncLogAdminDisplayTests(TestCase):
    def setUp(self):
        self.admin = NewsSyncLogAdmin(NewsSyncLog, AdminSite())
        self.source = NewsFeedSource.objects.create(name="Log Source", source_key="logsrc", feed_url="https://x/feed")

    def test_has_errors_display_true(self):
        log = NewsSyncLog.objects.create(feed_source=self.source, started_at=timezone.now(), errors_text="boom")
        self.assertTrue(self.admin.has_errors_display(log))

    def test_has_errors_display_false(self):
        log = NewsSyncLog.objects.create(feed_source=self.source, started_at=timezone.now(), errors_text="")
        self.assertFalse(self.admin.has_errors_display(log))


class NewsSyncLogAdminDeletePermissionTests(TestCase):
    """The read-only sync-log admin re-enables delete only for cms-app members."""

    def setUp(self):
        self.admin = NewsSyncLogAdmin(NewsSyncLog, AdminSite())
        self.factory = RequestFactory()

    def _request(self, user):
        request = self.factory.get("/admin/cms/newssynclog/")
        request.user = user
        return request

    def test_delete_allowed_for_cms_staff(self):
        user = make_admin(apps=["cms"], email="cms-log@example.com")
        self.assertTrue(self.admin.has_delete_permission(self._request(user)))

    def test_delete_denied_for_other_app_staff(self):
        user = make_admin(apps=["event"], email="event-log@example.com")
        self.assertFalse(self.admin.has_delete_permission(self._request(user)))

    def test_delete_allowed_for_superuser(self):
        user = make_superuser(email="master-log@example.com")
        self.assertTrue(self.admin.has_delete_permission(self._request(user)))


class NewsSyncLogAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            password="testpass123",
            first_name="Log",
            last_name="Admin",
        )
        ContactEmail.objects.get_or_create(
            member=self.admin, email_address="admin@test.com", defaults={"email_type": "primary", "verified": True}
        )
        self.client.login(username="admin@test.com", password="testpass123")

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:cms_newssynclog_changelist"))
        self.assertEqual(resp.status_code, 200)
