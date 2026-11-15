"""Email Monitoring as the one delivery page (it absorbed the Delivery Dashboard): its five tabs, the Overview's
sections and single KPI strip, the old Delivery Dashboard addresses, and the guards that did not move."""

import re
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import resolve, reverse

from apps.core.models import AWSCredentialConfig, BackgroundJob, EmailCategory, EmailServiceConfig, OutboundEmail
from apps.core.services.email.bounces import BOUNCE_SCAN_JOB_KIND
from apps.core.services.request_limits.scopes import classify_route
from apps.core.tests.services.email_monitoring.helpers import make_attempt, make_bounce, make_email
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BouncedAddress, EmailCampaign

from .ses_helpers import PATCH_DASHBOARD, ses_payload

TABS = (
    ("Overview", "admin:mail_email_monitoring"),
    ("Email log", "admin:mail_email_monitoring_emails"),
    ("Bounce reports", "admin:mail_email_monitoring_bounces"),
    ("Bounced addresses", "admin:mail_email_monitoring_addresses"),
    ("Amazon SES", "admin:mail_email_monitoring_ses"),
)
SUBNAV = re.compile(r'<nav class="i2g-monitor-subnav" aria-label="Email monitoring sections">(.*?)</nav>', re.S)
SUBNAV_LINK = re.compile(r'<a href="([^"]*)"\s*(aria-current="page")?\s*>\s*<span[^>]*>[^<]*</span>([^<]+)</a>')
OVERVIEW_FIGURES = (
    "Total outgoing emails",
    "API accepted",
    "API failed",
    "API success rate",
    "Confirmed bounced emails",
    "Emails retried",
    "Total intended recipients",
    "Recipients in accepted emails",
    "Recipients in failed or unsent emails",
    "Confirmed bounced recipients",
    "Bounce reports received",
    "API attempts",
    "Retries",
    "429 throttling incidents",
    "Average API response time",
    "Attempt success rate",
)
FIGURE_LABEL = re.compile(r"<(?:p|dt)>([^<]+)</(?:p|dt)>")


def subnav(response) -> list[tuple[str, bool, str]]:
    """``(href, current, label)`` of each Email Monitoring tab link on the page."""
    found = SUBNAV.search(response.content.decode())
    return [(href, bool(current), label.strip()) for href, current, label in SUBNAV_LINK.findall(found.group(1))]


class TabTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())
        self.email = make_email()
        self.campaign = EmailCampaign.objects.create(subject="News", body="<p>x</p>", status="sent")
        self.address = BouncedAddress.objects.create(address="gone@example.com")

    @patch(PATCH_DASHBOARD, return_value=ses_payload())
    def test_every_page_has_the_same_five_tabs_and_marks_its_own(self, _dashboard):
        pages = [(reverse(name), label) for label, name in TABS] + [
            (reverse("admin:mail_email_monitoring_email", args=[self.email.pk]), "Email log"),
            (reverse("admin:mail_email_monitoring_address", args=[self.address.pk]), "Bounced addresses"),
            (reverse("admin:mail_email_monitoring_campaign", args=[self.campaign.pk]), None),
        ]
        for url, current in pages:
            with self.subTest(url=url):
                links = subnav(self.client.get(url))
                self.assertEqual([label for _href, _current, label in links], [label for label, _name in TABS])
                self.assertEqual([href.split("?")[0] for href, _c, _l in links], [reverse(name) for _l, name in TABS])
                self.assertEqual(
                    [label for _href, is_current, label in links if is_current], [current] if current else []
                )

    def test_the_range_and_provider_follow_the_telemetry_tabs(self):
        links = subnav(self.client.get(reverse("admin:mail_email_monitoring"), {"range": "30d", "provider": "graph"}))

        hrefs = {label: href for href, _current, label in links}
        for label in ("Overview", "Email log", "Bounce reports"):
            self.assertTrue(hrefs[label].endswith("?range=30d&amp;provider=graph"), hrefs[label])
        # Bounced addresses and Amazon SES have their own filters and window.
        self.assertEqual(hrefs["Bounced addresses"], reverse("admin:mail_email_monitoring_addresses"))
        self.assertEqual(hrefs["Amazon SES"], reverse("admin:mail_email_monitoring_ses"))


class OverviewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())
        self.url = reverse("admin:mail_email_monitoring")

    def test_every_section_is_on_the_overview(self):
        failed = make_email(status=OutboundEmail.Status.FAILED, last_error="Microsoft Graph rejected the request.")
        make_attempt(failed, outcome="permanent", http_status=400, error_kind="bad_request")
        campaign = EmailCampaign.objects.create(subject="News", body="<p>x</p>", status="sent")
        make_email(campaign_id=campaign.pk)
        make_bounce(recipient="lost@example.com", match_method="unmatched")

        response = self.client.get(self.url)

        for heading in (
            'id="monitor-bounce-processing"',
            'id="monitor-key-figures"',
            'id="monitor-levels"',
            'id="monitor-recipients"',
            'id="monitor-attempts"',
            "Most recent sending error",
            'id="monitor-trends"',
            'data-chart="volume"',
            'data-chart="api"',
            'data-chart="bounces"',
            'id="monitor-breakdowns"',
            "Failed attempts by HTTP status",
            "Emails by category",
            "Top failure reasons",
            "Top bounce reasons",
            'id="monitor-campaigns"',
            reverse("admin:mail_email_monitoring_campaign", args=[campaign.pk]),
        ):
            self.assertContains(response, heading)

    def test_one_kpi_strip_and_every_figure_exactly_once(self):
        make_attempt(make_email(), http_status=202)

        response = self.client.get(self.url)
        html = response.content.decode()

        self.assertEqual(html.count('class="i2g-monitor-tiles"'), 1)
        strip = html.split("data-monitor-kpis>", 1)[1].split("</div>\n  <p", 1)[0]
        self.assertEqual(strip.count('class="i2g-monitor-tile"'), 6)
        labels = FIGURE_LABEL.findall(html)
        for label in OVERVIEW_FIGURES:
            self.assertEqual(labels.count(label), 1, label)
        # Amazon SES's own figures are on their tab only, not repeated here.
        for label in ("SES attempts", "Delivered by SES", "SES errors"):
            self.assertNotIn(label, labels)
        self.assertNotContains(response, ">Delivered<")

    def test_the_send_rate_is_shown_once_with_a_link_to_delivery_rates(self):
        with patch("apps.mail.services.email_monitoring.overview.email_send_rate_line", return_value="Now: 5/sec"):
            response = self.client.get(self.url)

        self.assertContains(response, "Send rate: Now: 5/sec", count=1)
        self.assertContains(response, f'<a href="{reverse("admin:mail_delivery_rates")}">Delivery Rates</a>', count=1)

    def test_a_send_rate_that_cannot_be_read_never_breaks_the_page(self):
        with (
            patch("apps.mail.services.email_monitoring.overview.email_send_rate_line", side_effect=RuntimeError("x")),
            self.assertLogs("apps.mail.services.email_monitoring.overview", "WARNING"),
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["send_rate"], "")
        self.assertNotContains(response, "data-monitor-send-rate")

    def test_the_overview_never_reads_aws(self):
        # SES is the sender and AWS credentials are set, so an AWS read (CloudWatch, the suppression list, a Secrets
        # Manager key) would get as far as building a boto3 client. Check that no client is built at all. Building one
        # raises, so a read fails at once (a stand-in client would page CloudWatch forever), but the raise alone proves
        # nothing: the SES dashboard turns every AWS failure into a notice and the page would still load.
        no_client = AssertionError("the Overview must not build an AWS client")
        AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="AKIAEXAMPLE0000",
            secret_access_key="not-a-real-secret",
            default_region="us-west-2",
        )
        EmailServiceConfig.objects.create(
            name="Primary Sender", is_active=True, provider="ses", from_email="sender@example.com", max_send_rate=0
        )

        with (
            patch("boto3.client", side_effect=no_client) as client,
            patch("boto3.session.Session.client", side_effect=no_client) as session_client,
        ):
            page = self.client.get(self.url)
            data = self.client.get(reverse("admin:mail_email_monitoring_data"))

        self.assertEqual((page.status_code, data.status_code), (200, 200))
        client.assert_not_called()
        session_client.assert_not_called()
        self.assertContains(page, f'href="{reverse("admin:mail_email_monitoring_ses")}"')

    def test_the_response_time_names_microsoft_graph_whose_answers_it_averages(self):
        # Only the Graph provider records an HTTP answer (AttemptNotes.answered), and the average reads only attempts
        # with one, so the caption names Microsoft whatever the Provider filter says.
        make_attempt(make_email(), http_status=202, response_ms=300)
        make_attempt(make_email(provider="ses"), provider="ses", http_status=None, response_ms=900)

        response = self.client.get(self.url)

        self.assertEqual(response.context["figures"]["attempts"]["avg_response_ms"], 300)
        self.assertContains(response, "requests Microsoft answered", count=1)

    def test_the_probe_note_and_the_figures_still_leave_probes_out(self):
        make_email(category=EmailCategory.ACCESS_CHECK)

        response = self.client.get(self.url)

        self.assertEqual(response.context["figures"]["messages"]["total"], 0)
        self.assertContains(response, "1 Graph access check probe send in this range is listed in the email log")


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
        self.assertTemplateUsed(response, "admin/mail/email_monitoring/ses.html")
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
