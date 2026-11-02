"""Who may open and change Site Settings → Request Limits: superusers and staff with the Core (System) app; other
staff get 403, anonymous visitors and members who are not staff are sent to the admin sign-in. Nobody refused can
change a limit."""

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.core.models import RequestRateLimitPolicy
from apps.event.tests.helpers import make_admin, make_superuser

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

    def test_staff_without_the_core_app_get_403_everywhere(self):
        for apps in (["event", "mail", "cms"], []):
            with self.subTest(apps=apps):
                self.client.force_login(make_admin(apps=apps, email=f"other{len(apps)}@example.com"))
                for method, url, data in self.requests():
                    with self.subTest(method=method, url=url):
                        response = getattr(self.client, method)(url, data or {})
                        self.assertEqual(response.status_code, 403)
        self.assert_unchanged()

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
        member.admin_apps = ["core"]  # an app grant without is_staff gives no admin access
        member.save()
        self.client.force_login(member)
        for method, url, data in self.requests():
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, data or {}).status_code, 302)
        self.assert_unchanged()

    def test_inactive_core_staff_cannot_use_the_page(self):
        self.staff.is_active = False
        self.staff.save()
        for method, url, data in self.requests():
            with self.subTest(method=method, url=url):
                self.assertIn(getattr(self.client, method)(url, data or {}).status_code, (302, 403))
        self.assert_unchanged()

    def test_other_methods_are_refused(self):
        self.assertEqual(self.client.put(URL).status_code, 405)
        self.assertEqual(self.client.post(STATUS_URL).status_code, 405)


class AllowedTests(RequestLimitsAdminTestCase):
    def test_core_staff_who_are_not_superusers_view_and_edit(self):
        self.assertFalse(self.staff.is_superuser)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save request limits")
        self.assertEqual(self.client.get(STATUS_URL).status_code, 200)

        response = self.client.post(URL, self.post_data(**{"public-read-tier": "p2"}))

        self.assertRedirects(response, URL, fetch_redirect_response=False)
        self.assertEqual(RequestRateLimitPolicy.for_scope("public-read").tier, "p2")

    def test_superusers_view_and_edit(self):
        self.client.force_login(make_superuser(email="master@example.com"))
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(self.client.get(STATUS_URL).status_code, 200)

        self.client.post(URL, self.post_data(**{"ai-manual_requests": "30"}))

        self.assertEqual(RequestRateLimitPolicy.for_scope("ai").manual_requests, 30)


class SidebarTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_site_settings_lists_the_page_for_core_staff_only(self):
        self.client.force_login(make_admin(apps=["core"], email="core@example.com"))
        self.assertContains(self.client.get("/admin/"), 'href="/admin/core/request-limits/"')

        self.client.force_login(make_admin(apps=["event"], email="event@example.com"))
        self.assertNotContains(self.client.get("/admin/"), 'href="/admin/core/request-limits/"')
