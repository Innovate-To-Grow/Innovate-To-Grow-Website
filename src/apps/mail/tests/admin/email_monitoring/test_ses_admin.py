"""Mail → Delivery Operations → Email Monitoring → Amazon SES: the former Delivery Dashboard as a tab (its figures once
each, its window, its notices, the suppression list) and its JSON endpoints, old and new. AWS is never called."""

import json
import re
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_superuser

from .ses_helpers import PATCH_DASHBOARD, ses_payload

# Every label of a figure on the tab: a tile's (``<p>``) or a fact's (``<dt>``) or a breakdown row's.
FIGURE_LABEL = re.compile(r'<(?:p|dt)>([^<]+)</(?:p|dt)>|<span class="i2g-monitor-meter-label">([^<]+)</span>')


def figure_labels(response) -> list[str]:
    return [tile or meter for tile, meter in FIGURE_LABEL.findall(response.content.decode())]


@patch(PATCH_DASHBOARD)
class SesTabTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())
        self.url = reverse("admin:mail_email_monitoring_ses")

    def test_the_tab_shows_each_aws_figure_once(self, dashboard):
        dashboard.return_value = ses_payload()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/mail/email_monitoring/ses.html")
        dashboard.assert_called_once_with(days=183)
        labels = figure_labels(response)
        for label in ("SES attempts", "Delivered by SES", "SES errors", "Bounces", "Complaints", "Rejected by SES"):
            self.assertEqual(labels.count(label), 1, label)
        self.assertEqual(len(labels), len(set(labels)), labels)
        # The old page's "Bounce / Complaint" tile was Bounced + Complained, and its Delivery Mix repeated the Sent
        # and Delivered tiles: each of those numbers is now shown once.
        for gone in ("Bounce / Complaint", "Delivery Mix", "SES Attempts", "Successful Delivery"):
            self.assertNotContains(response, gone)
        self.assertContains(response, "<p>SES attempts</p><strong>120</strong>", html=True)
        self.assertContains(response, "<p>Delivered by SES</p><strong>116</strong>", html=True)
        self.assertContains(response, "<p>SES errors</p><strong>4</strong>", html=True)
        self.assertContains(response, "3.3% failure rate")
        self.assertContains(response, "2 delivery delays: SES was still retrying")
        self.assertEqual(
            [(row["label"], row["count"]) for row in response.context["error_types"]],
            [("Bounces", 3), ("Complaints", 1), ("Rejected by SES", 0), ("Rendering failures", 0)],
        )

    def test_the_daily_chart_has_every_day_and_a_data_table(self, dashboard):
        dashboard.return_value = ses_payload()

        response = self.client.get(self.url)

        payload = json.loads(
            re.search(
                r'id="i2g-monitor-ses" type="application/json">(.*?)</script>', response.content.decode(), re.S
            ).group(1)
        )
        daily = payload["daily"]
        self.assertEqual(daily["labels"], ["2026-06-06", "2026-06-07", "2026-06-08"])
        self.assertEqual(daily["series"], {"attempts": [0, 20, 100], "problems": [0, 0, 4]})
        self.assertEqual([row["label"] for row in daily["table"]], ["Jun 07", "Jun 08"])
        self.assertContains(response, 'data-chart="daily" data-kind="lines" data-source="i2g-monitor-ses"')
        self.assertContains(response, "mail/js/email-monitoring.js")

    def test_the_window_is_one_of_the_four_and_defaults_to_six_months(self, dashboard):
        dashboard.side_effect = lambda *, days: ses_payload(window_days=days)

        for value, days in (("7", 7), ("90", 90), ("365", 365), ("999", 183), ("abc", 183), ("", 183)):
            with self.subTest(days=value):
                dashboard.reset_mock()
                response = self.client.get(self.url, {"days": value})
                dashboard.assert_called_once_with(days=days)
                self.assertEqual(
                    [option["days"] for option in response.context["windows"] if option["selected"]], [days]
                )
        self.assertContains(response, '<option value="7">Last 7 days</option>', html=True)
        self.assertContains(response, '<option value="90">Last 3 months</option>', html=True)
        self.assertContains(response, '<option value="183" selected>Last 6 months</option>', html=True)
        self.assertContains(response, '<option value="365">Last 12 months</option>', html=True)

    def test_the_suppression_list_rows_carry_what_the_filter_and_export_read(self, dashboard):
        dashboard.return_value = ses_payload()

        response = self.client.get(self.url)

        self.assertContains(
            response, 'data-ses-row data-email="bounce@example.com" data-domain="example.com" data-status="bounced"'
        )
        self.assertContains(
            response, 'data-email="complaint@example.org" data-domain="example.org" data-status="complained"'
        )
        self.assertContains(
            response, 'data-window-days="183" data-window-label="Last 6 months" data-window-short="6mo"'
        )
        self.assertContains(response, "AWS SES Suppression List - Account-level suppression", count=2)
        recipients = response.context["recipients"]
        self.assertEqual((recipients["total"], recipients["bounced"], recipients["complained"]), (2, 1, 1))
        self.assertEqual(recipients["latest"], "Jun 08, 12:00")
        for value, label in (("csv", "CSV"), ("tsv", "TSV"), ("json", "JSON"), ("xls", "Excel")):
            self.assertContains(response, f'<option value="{value}">{label}</option>', html=True)
        self.assertContains(response, "mail/js/email-monitoring-ses.js")

    def test_addresses_and_reasons_are_escaped(self, dashboard):
        row = {**ses_payload()["problem_recipients"][0], "email": '"<b>x</b>"@example.com', "reason": "<img src=x>"}
        dashboard.return_value = ses_payload(problem_recipients=[row])

        response = self.client.get(self.url)

        self.assertNotContains(response, "<b>x</b>")
        self.assertNotContains(response, "<img src=x>")
        self.assertContains(response, "&lt;img src=x&gt;")

    def test_an_empty_list_says_why(self, dashboard):
        cases = (
            ({}, "No suppressed recipient addresses found in AWS SES for last 6 months."),
            (
                {"available": False, "reason": "permission"},
                "CloudWatch only provides aggregate counts, not recipient email addresses.",
            ),
            (
                {"available": False, "reason": "aws_error"},
                "are unavailable from the AWS SES suppression list right now.",
            ),
            (
                {"available": False, "reason": "unconfigured"},
                "The suppression list cannot be read: AWS SES is not configured.",
            ),
        )
        for details, text in cases:
            with self.subTest(details=details):
                aws = {"recipient_details_available": details.get("available", True)}
                aws["recipient_details_reason"] = details.get("reason", "")
                dashboard.return_value = ses_payload(problem_recipients=[], details=details, aws=aws)
                response = self.client.get(self.url)
                self.assertContains(response, text)
                self.assertNotContains(response, "data-ses-row")
                self.assertNotContains(response, "data-ses-export")

    def test_no_errors_says_so(self, dashboard):
        summary = {**ses_payload()["summary"], "problems": 0, "bounces": 0, "complaints": 0, "delayed": 1}
        dashboard.return_value = ses_payload(summary=summary)

        response = self.client.get(self.url)

        self.assertContains(response, "No SES errors in this range.")
        self.assertContains(response, "1 delivery delay: SES was still retrying, so it is not counted as errors.")

    def test_one_notice_in_the_old_pages_order(self, dashboard):
        permission = {
            "recipient_details_available": False,
            "recipient_details_reason": "permission",
            "recipient_details_error_code": "AccessDeniedException",
            "recipient_details_required_actions": ["ses:ListSuppressedDestinations", "ses:GetSuppressedDestination"],
        }
        cases = (
            ({"provider": "graph", "provider_label": "Microsoft Graph", "configured": False}, "provider", "note"),
            ({"configured": False, "metrics_available": False}, "unconfigured", "alert"),
            ({"metrics_available": False, **permission}, "metrics", "alert"),
            (permission, "recipients", "alert"),
            ({}, None, None),
        )
        for aws, key, role in cases:
            with self.subTest(notice=key):
                dashboard.return_value = ses_payload(aws=aws)
                response = self.client.get(self.url)
                notice = response.context["notice"]
                self.assertEqual(notice and notice["key"], key)
                self.assertEqual(response.content.decode().count("data-ses-notice="), 1 if key else 0)
                if key:
                    self.assertContains(response, f'role="{role}" data-ses-notice="{key}"')
        dashboard.return_value = ses_payload(aws=permission)
        response = self.client.get(self.url)
        self.assertContains(
            response,
            "Grant ses:ListSuppressedDestinations, ses:GetSuppressedDestination to ...1234 in us-west-2. "
            "AWS returned AccessDeniedException.",
        )

    def test_the_send_rate_is_on_the_overview_not_here(self, dashboard):
        dashboard.return_value = ses_payload()

        response = self.client.get(self.url)

        self.assertNotContains(response, "Send rate:")
        self.assertNotContains(response, "Now: 12 recipients/sec")


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
