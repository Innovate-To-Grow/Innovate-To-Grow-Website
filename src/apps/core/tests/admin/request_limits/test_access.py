"""Who may open and change Site Settings → Request Limits: every Admin; anonymous visitors, members who are not staff
and inactive admins are sent to the admin sign-in. Nobody refused can change a limit."""

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.core.models import RequestRateLimitPolicy
from apps.event.tests.helpers import make_admin

from .helpers import STATUS_URL, URL, RequestLimitsAdminTestCase

Member = get_user_model()


class RefusedTests(RequestLimitsAdminTestCase):
    def requests(self):
        post = self.post_data(**{"auth-code-send-manual_requests": "99", "auth-code-send-tier": "p3"})
        return (("get", URL, None), ("post", URL, post), ("get", STATUS_URL, None))

    def assert_unchanged(self):
        policy = RequestRateLimitPolicy.for_scope("auth-code-send")
        self.assertEqual((policy.manual_requests, policy.tier), (10, "p0"))
        self.assertFalse(LogEntry.objects.exists())

    def test_anonymous_visitors_are_sent_to_the_admin_sign_in(self):
        self.client.logout()
        for method, url, data in self.requests():
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data or {})
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/admin/login/"))
        self.assert_unchanged()

    def test_members_who_are_not_staff_are_sent_to_the_admin_sign_in(self):
        member = Member.objects.create_user(email="member@example.com", password="pw-123456!", is_active=True)
        self.client.force_login(member)
        for method, url, data in self.requests():
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, data or {}).status_code, 302)
        self.assert_unchanged()

    def test_inactive_admins_cannot_use_the_page(self):
        self.staff.is_active = False
        self.staff.save()
        for method, url, data in self.requests():
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, data or {}).status_code, 302)
        self.assert_unchanged()

    def test_other_methods_are_refused(self):
        self.assertEqual(self.client.put(URL).status_code, 405)
        self.assertEqual(self.client.post(STATUS_URL).status_code, 405)


class AllowedTests(RequestLimitsAdminTestCase):
    def test_admins_view_and_edit(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save request limits")
        self.assertEqual(self.client.get(STATUS_URL).status_code, 200)

        response = self.client.post(URL, self.post_data(**{"public-read-tier": "p2"}))

        self.assertRedirects(response, URL, fetch_redirect_response=False)
        self.assertEqual(RequestRateLimitPolicy.for_scope("public-read").tier, "p2")

    def test_any_other_admin_views_and_edits(self):
        self.client.force_login(make_admin(email="second-admin@example.com"))
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(self.client.get(STATUS_URL).status_code, 200)

        self.client.post(URL, self.post_data(**{"ai-manual_requests": "30"}))

        self.assertEqual(RequestRateLimitPolicy.for_scope("ai").manual_requests, 30)


class SidebarTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_site_settings_lists_the_page_for_every_admin(self):
        self.client.force_login(make_admin(email="admin@example.com"))
        self.assertContains(self.client.get("/admin/"), 'href="/admin/core/request-limits/"')
