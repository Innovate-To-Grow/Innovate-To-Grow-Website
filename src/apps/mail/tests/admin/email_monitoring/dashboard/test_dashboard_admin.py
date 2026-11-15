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

    def test_staff_without_the_mail_app_are_refused_everywhere(self):
        self.client.force_login(make_admin(apps=["cms"]))

        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(reverse("admin:mail_email_monitoring_bounce_processing"), {"action": "scan"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND).exists())

    def test_mail_staff_and_superusers_may_open_every_page(self):
        for user in (make_admin(apps=["mail"]), make_superuser()):
            self.client.force_login(user)
            for url in self.urls():
                with self.subTest(user=user.pk, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_bounce_processing_controls_only_take_post(self):
        self.client.force_login(make_superuser())

        self.assertEqual(self.client.get(reverse("admin:mail_email_monitoring_bounce_processing")).status_code, 405)
