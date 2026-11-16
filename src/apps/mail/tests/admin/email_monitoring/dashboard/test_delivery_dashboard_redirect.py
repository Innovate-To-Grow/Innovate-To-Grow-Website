import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import resolve, reverse

from apps.core.models import BackgroundJob
from apps.core.services.email.bounces import BOUNCE_SCAN_JOB_KIND
from apps.core.services.request_limits.classification.scopes import classify_route
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BouncedAddress

from ..ses.ses_helpers import PATCH_DASHBOARD, ses_payload


class DeliveryDashboardRedirectTests(TestCase):
    """/admin/mail/delivery-dashboard/ became Email Monitoring → Amazon SES; its address and URL names stay valid."""

    def setUp(self):
        cache.clear()
        self.old = reverse("admin:mail_delivery_dashboard")
        self.new = reverse("admin:mail_email_monitoring_ses")

    def test_the_names_still_reverse_to_the_old_addresses(self):
        self.assertEqual(self.old, "/admin/mail/delivery-dashboard/")
        self.assertEqual(reverse("admin:mail_delivery_dashboard_data"), "/admin/mail/delivery-dashboard/data/")
        self.assertEqual(self.new, "/admin/mail/email-monitoring/ses/")

    def test_the_old_page_redirects_temporarily_with_its_query_string(self):
        self.client.force_login(make_superuser())

        for query, target in (
            ("", self.new),
            ("?days=365", f"{self.new}?days=365"),
            ("?days=90&utm=x%20y&days=7", f"{self.new}?days=90&utm=x%20y&days=7"),
        ):
            with self.subTest(query=query):
                for method in (self.client.get, self.client.head):
                    response = method(self.old + query)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response["Location"], target)
                    self.assertIn("no-cache", response["Cache-Control"])

    @patch(PATCH_DASHBOARD)
    def test_following_the_redirect_opens_the_tab_with_the_same_window(self, dashboard):
        dashboard.side_effect = lambda *, days: ses_payload(window_days=days)
        self.client.force_login(make_admin(apps=["mail"]))

        response = self.client.get(self.old, {"days": "365"}, follow=True)

        self.assertEqual(response.redirect_chain, [(f"{self.new}?days=365", 302)])
        self.assertTemplateUsed(response, "admin/mail/email_monitoring/pages/ses.html")
        dashboard.assert_called_once_with(days=365)

    def test_only_get_and_head_are_redirected(self):
        self.client.force_login(make_superuser())

        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.old).status_code, 405)

    def test_anonymous_visitors_log_in_first_and_come_back_to_the_old_address(self):
        response = self.client.get(self.old, {"days": "90"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertIn("next=/admin/mail/delivery-dashboard/%3Fdays%3D90", response["Location"])

    @patch(PATCH_DASHBOARD, side_effect=AssertionError("AWS must not be read for a refused request"))
    def test_staff_without_the_mail_app_are_refused_at_the_tab(self, _dashboard):
        self.client.force_login(make_admin(apps=["cms"]))

        response = self.client.get(self.old, follow=True)

        self.assertEqual(response.redirect_chain, [(self.new, 302)])
        self.assertEqual(response.status_code, 403)

    @patch(PATCH_DASHBOARD, return_value=ses_payload())
    def test_the_old_json_endpoint_answers_without_a_redirect(self, _dashboard):
        self.client.force_login(make_superuser())

        response = self.client.get(reverse("admin:mail_delivery_dashboard_data"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.client.get(reverse("admin:mail_email_monitoring_ses_data")).json())


class GuardTests(TestCase):
    """The POST actions kept their addresses (nothing is redirected that could drop a body), the Mail app check and
    CSRF."""

    def setUp(self):
        cache.clear()
        self.address = BouncedAddress.objects.create(address="gone@example.com")
        self.posts = (
            reverse("admin:mail_email_monitoring_bounce_processing"),
            reverse("admin:mail_email_monitoring_addresses_bulk"),
            reverse("admin:mail_email_monitoring_addresses_rebuild"),
            reverse("admin:mail_email_monitoring_address_action", args=[self.address.pk, "dismiss"]),
        )

    def test_the_post_actions_did_not_move(self):
        self.assertEqual(
            self.posts,
            (
                "/admin/mail/email-monitoring/bounce-processing/",
                "/admin/mail/email-monitoring/addresses/bulk/",
                "/admin/mail/email-monitoring/addresses/rebuild/",
                f"/admin/mail/email-monitoring/addresses/{self.address.pk}/dismiss/",
            ),
        )

    def test_a_post_without_the_csrf_token_is_refused(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(make_superuser())

        for url in self.posts:
            with self.subTest(url=url):
                self.assertEqual(client.post(url, {"action": "scan", "step": "confirm"}).status_code, 403)
        self.assertFalse(BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND).exists())

    def test_a_post_with_the_page_token_reaches_the_action(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(make_superuser())
        client.get(reverse("admin:mail_email_monitoring"))
        token = client.cookies["csrftoken"].value

        response = client.post(self.posts[0], {"action": "drop", "csrfmiddlewaretoken": token})

        self.assertRedirects(response, reverse("admin:mail_email_monitoring"), fetch_redirect_response=False)

    def test_staff_without_the_mail_app_are_refused_every_action(self):
        self.client.force_login(make_admin(apps=["cms"]))

        for url in self.posts:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {"action": "scan", "step": "confirm"}).status_code, 403)
        self.assertTrue(BouncedAddress.objects.filter(pk=self.address.pk, status=BouncedAddress.Status.OPEN).exists())

    def test_the_data_endpoints_are_rate_limited_as_polling(self):
        for path in ("/admin/mail/email-monitoring/ses/data/", "/admin/mail/delivery-dashboard/data/"):
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(classify_route(match.func, match.view_name, "GET").scope, "staff-polling")

    def test_unknown_ids_still_404_on_the_drill_downs(self):
        self.client.force_login(make_superuser())

        for name in ("admin:mail_email_monitoring_email", "admin:mail_email_monitoring_campaign"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=[uuid.uuid4()])).status_code, 404)
