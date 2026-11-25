"""Mail → Delivery Operations → Email Monitoring: who may open it, what each page shows, and its controls."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import (
    BackgroundJob,
)
from apps.core.services.email.bounces import BOUNCE_SCAN_JOB_KIND
from apps.core.tests.services.email_monitoring.helpers import (
    make_email,
)
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import EmailCampaign
from apps.mail.tests.admin.admin_access.refusal import assert_refused_to_member, make_member

PAGES = (
    ("admin:mail_email_monitoring", ()),
    ("admin:mail_email_monitoring_data", ()),
    ("admin:mail_email_monitoring_emails", ()),
    ("admin:mail_email_monitoring_bounces", ()),
)


class AccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.email = make_email()
        self.campaign = EmailCampaign.objects.create(subject="News", body="<p>x</p>", status="sent")

    def urls(self):
        return [reverse(name, args=args) for name, args in PAGES] + [
            reverse("admin:mail_email_monitoring_email", args=[self.email.pk]),
            reverse("admin:mail_email_monitoring_campaign", args=[self.campaign.pk]),
        ]

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])

    def test_members_who_are_not_admins_are_refused_everywhere(self):
        member = make_member()

        for url in self.urls():
            with self.subTest(url=url):
                assert_refused_to_member(self, url, member)
        url = reverse("admin:mail_email_monitoring_bounce_processing")
        assert_refused_to_member(self, url, member, "post", data={"action": "scan"})
        self.assertFalse(BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND).exists())

    def test_every_admin_may_open_every_page(self):
        self.client.force_login(make_admin())
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_bounce_processing_controls_only_take_post(self):
        self.client.force_login(make_superuser())

        self.assertEqual(self.client.get(reverse("admin:mail_email_monitoring_bounce_processing")).status_code, 405)
