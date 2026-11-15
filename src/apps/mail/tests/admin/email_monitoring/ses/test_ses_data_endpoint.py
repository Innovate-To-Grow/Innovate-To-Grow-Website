from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_superuser

from .ses_helpers import PATCH_DASHBOARD, ses_payload


@patch(PATCH_DASHBOARD)
class SesDataEndpointTests(TestCase):
    """The tab's JSON and the Delivery Dashboard's old one: the same payload, unchanged."""

    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_the_new_and_the_old_endpoint_return_the_payload_as_it_is(self, dashboard):
        dashboard.side_effect = lambda *, days: ses_payload(window_days=days)

        for name in ("admin:mail_email_monitoring_ses_data", "admin:mail_delivery_dashboard_data"):
            with self.subTest(name=name):
                dashboard.reset_mock()
                response = self.client.get(reverse(name), {"days": "90"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/json")
                self.assertEqual(response.json(), ses_payload(window_days=90))
                dashboard.assert_called_once_with(days=90)

    def test_an_unlisted_window_reads_the_default(self, dashboard):
        dashboard.side_effect = lambda *, days: ses_payload(window_days=days)

        for name in ("admin:mail_email_monitoring_ses_data", "admin:mail_delivery_dashboard_data"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name), {"days": "999"}).json()["window_days"], 183)
                self.assertEqual(self.client.get(reverse(name)).json()["window_days"], 183)


@patch(PATCH_DASHBOARD, side_effect=AssertionError("AWS must not be read for a refused request"))
class SesAccessTests(TestCase):
    NAMES = (
        "admin:mail_email_monitoring_ses",
        "admin:mail_email_monitoring_ses_data",
        "admin:mail_delivery_dashboard_data",
    )

    def setUp(self):
        cache.clear()

    def test_anonymous_visitors_are_sent_to_the_login_page(self, _dashboard):
        for name in self.NAMES:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])

    def test_staff_without_the_mail_app_are_refused_before_aws_is_read(self, _dashboard):
        self.client.force_login(make_admin(apps=["cms"]))

        for name in self.NAMES:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_mail_staff_may_open_the_tab(self, dashboard):
        dashboard.side_effect = None
        dashboard.return_value = ses_payload()
        self.client.force_login(make_admin(apps=["mail"]))

        for name in self.NAMES:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
