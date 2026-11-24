"""Email Monitoring → Bounced addresses: who may open it (Admins), the list (counting, tabs, filters, sorting, row menus),
one address's page, and the spreadsheet export."""

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BouncedAddress
from apps.mail.tests.admin.admin_access.refusal import assert_refused_to_member, make_member
from apps.mail.tests.services.bounced_addresses.helpers import (
    make_row,
)

LIST = "admin:mail_email_monitoring_addresses"
EXPORT = "admin:mail_email_monitoring_addresses_export"
BULK = "admin:mail_email_monitoring_addresses_bulk"
REBUILD = "admin:mail_email_monitoring_addresses_rebuild"
DETAIL = "admin:mail_email_monitoring_address"
ACTION = "admin:mail_email_monitoring_address_action"


class AccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.row = make_row("access@example.org")

    def get_urls(self):
        return [reverse(LIST), reverse(EXPORT), reverse(DETAIL, args=[self.row.pk])]

    def post_urls(self):
        return [reverse(BULK), reverse(REBUILD), reverse(ACTION, args=[self.row.pk, "dismiss"])]

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        for url in self.get_urls() + self.post_urls():
            with self.subTest(url=url):
                response = self.client.post(url) if url in self.post_urls() else self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])

    def test_members_who_are_not_admins_are_refused_everywhere(self):
        member = make_member()

        for url in self.get_urls():
            with self.subTest(url=url):
                assert_refused_to_member(self, url, member)
        for url in self.post_urls():
            with self.subTest(url=url):
                assert_refused_to_member(self, url, member, "post", data={"step": "apply", "note": "x"})
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, BouncedAddress.Status.OPEN)

    def test_every_admin_may_open_every_page(self):
        self.client.force_login(make_admin(email="m@example.org"))
        for url in self.get_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_action_views_only_take_post_with_a_csrf_token(self):
        user = make_superuser()
        self.client.force_login(user)
        for url in self.post_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(user)

        response = strict.post(reverse(ACTION, args=[self.row.pk, "dismiss"]), {"step": "apply", "note": "x"})

        self.assertEqual(response.status_code, 403)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, BouncedAddress.Status.OPEN)

    def test_an_unknown_action_or_address_is_not_found(self):
        self.client.force_login(make_superuser())

        self.assertEqual(self.client.post(reverse(ACTION, args=[self.row.pk, "explode"])).status_code, 404)
        missing = reverse(DETAIL, args=["00000000-0000-0000-0000-000000000000"])
        self.assertEqual(self.client.get(missing).status_code, 404)

    def test_the_tab_is_on_every_monitoring_page(self):
        self.client.force_login(make_superuser())

        response = self.client.get(reverse("admin:mail_email_monitoring"))

        self.assertContains(response, reverse(LIST))
        self.assertContains(response, "Bounced addresses")
