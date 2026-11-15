"""Email Monitoring as the one delivery page (it absorbed the Delivery Dashboard): its five tabs, the Overview's
sections and single KPI strip, the old Delivery Dashboard addresses, and the guards that did not move."""

import re
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.event.tests.helpers import make_superuser
from apps.mail.models import BouncedAddress, EmailCampaign

from ..ses.ses_helpers import PATCH_DASHBOARD, ses_payload

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
