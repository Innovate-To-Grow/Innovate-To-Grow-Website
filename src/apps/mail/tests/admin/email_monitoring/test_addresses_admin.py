"""Email Monitoring → Bounced addresses: who may open it, the list (counting, tabs, filters, sorting, row menus),
one address's page, and the spreadsheet export."""

from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.core.cache import cache
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.authn.models import ContactEmail
from apps.core.tests.services.email_monitoring.helpers import make_email, monitoring_settings
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BouncedAddress, BouncedAddressAction
from apps.mail.tests.services.bounced_addresses.helpers import (
    add_email,
    count_now,
    make_bounce,
    make_campaign,
    make_person,
    make_row,
    make_ses_log,
    settled,
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

    def test_staff_without_the_mail_app_are_refused_everywhere(self):
        self.client.force_login(make_admin(apps=["authn", "cms"]))

        for url in self.get_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        for url in self.post_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {"step": "apply", "note": "x"}).status_code, 403)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, BouncedAddress.Status.OPEN)

    def test_mail_staff_and_superusers_may_open_every_page(self):
        for user in (make_admin(apps=["mail"], email="m@example.org"), make_superuser()):
            self.client.force_login(user)
            for url in self.get_urls():
                with self.subTest(user=user.pk, url=url):
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


class ListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.master = make_superuser()
        self.client.force_login(self.master)

    def test_loading_the_list_counts_new_reports_and_shows_the_member(self):
        member = make_person("listed@example.org", first="Lee", last="Stone")
        make_bounce(recipient="listed@example.org", status_code="5.1.1", reason="Recipient mailbox does not exist")

        with settled():
            response = self.client.get(reverse(LIST))

        self.assertContains(response, "listed@example.org")
        self.assertContains(response, "not found 1")
        self.assertContains(response, "Recipient mailbox does not exist")
        self.assertContains(response, reverse("admin:authn_member_change", args=[member.pk]))
        self.assertContains(response, "Mark undeliverable or replace the address")
        self.assertContains(response, "Mark undeliverable…")
        self.assertEqual(response.context["page"].paginator.count, 1)

    def test_mail_only_staff_see_names_without_links_and_only_the_actions_they_may_take(self):
        member = make_person("member@example.org", first="Mo")
        make_row("member@example.org")
        make_row("list-only@example.org")
        self.client.force_login(make_admin(apps=["mail"], email="mailstaff@example.org"))

        response = self.client.get(reverse(LIST))

        self.assertContains(response, "Mo Doe")
        self.assertNotContains(response, reverse("admin:authn_member_change", args=[member.pk]))
        menus = {
            entry["row"].address: [item["action"] for item in entry["quick"]] for entry in response.context["entries"]
        }
        self.assertNotIn("mark_undeliverable", menus["member@example.org"])
        self.assertIn("suppress", menus["list-only@example.org"])

    def test_reports_still_settling_are_shown_as_not_counted_yet(self):
        make_bounce(recipient="late@example.org")

        with monitoring_settings(address_settle_seconds=3600):
            response = self.client.get(reverse(LIST))

        self.assertEqual(response.context["pending"], 1)
        self.assertContains(response, "1 report (counted as this page reloads and hourly)")

    def test_a_counting_failure_never_breaks_the_page(self):
        make_row("shown@example.org")

        with patch(
            "apps.mail.admin.email_monitoring.addresses.aggregate.run", side_effect=DatabaseError("deadlock detected")
        ):
            with self.assertLogs("apps.mail.admin.email_monitoring.addresses", level="WARNING"):
                response = self.client.get(reverse(LIST))

        self.assertContains(response, "shown@example.org")
        self.assertContains(response, "counting failed on this load")

    def test_status_tabs_default_to_open(self):
        make_row("open@example.org")
        make_row("dismissed@example.org", status=BouncedAddress.Status.DISMISSED)

        default = self.client.get(reverse(LIST))
        everything = self.client.get(reverse(LIST), {"status": "all"})

        self.assertEqual([entry["row"].address for entry in default.context["entries"]], ["open@example.org"])
        self.assertEqual(default.context["status_counts"], {"all": 2, "open": 1, "dismissed": 1, "resolved": 0})
        self.assertEqual(everything.context["page"].paginator.count, 2)

    def test_every_filter_narrows_the_list(self):
        now = timezone.now()
        blast = make_campaign("Blast")
        member = make_person("member@example.org", first="Maya")
        make_person("boss@example.org", is_staff=True)
        make_row("member@example.org")
        make_row("boss@example.org")
        make_row("nobody@example.org", hard_count=0, rejected_count=2, suggestion="policy")
        make_row("muted@example.org", suppressed_at=now, suppression="suppressed")
        old = make_row("old@example.org", last_bounce_at=now - timedelta(days=40))
        complaint = make_row("complaint@example.org", hard_count=0, complaint_count=1)
        make_ses_log(blast, "complaint@example.org", complained=True, bounced=False)
        count_now()
        cases = {
            "type": ("complaint", ["complaint@example.org"]),
            "role": ("primary", ["boss@example.org", "member@example.org"]),
            "member": ("staff", ["boss@example.org"]),
            "suppressed": ("yes", ["muted@example.org"]),
            "suggestion": ("policy", ["nobody@example.org"]),
            "campaign": (str(blast.pk), ["complaint@example.org"]),
            "q": ("Maya", ["member@example.org"]),
            "start": ((now - timedelta(days=41)).date().isoformat(), None),
        }
        for name, (value, expected) in cases.items():
            with self.subTest(filter=name):
                response = self.client.get(reverse(LIST), {name: value, "status": "all"})
                addresses = sorted(entry["row"].address for entry in response.context["entries"])
                if expected is not None:
                    self.assertEqual(addresses, expected)
        until = (now - timedelta(days=39)).date().isoformat()
        response = self.client.get(reverse(LIST), {"end": until, "status": "all"})
        self.assertEqual([entry["row"].address for entry in response.context["entries"]], [old.address])
        self.assertIsNotNone(complaint.pk)
        self.assertIsNotNone(member.pk)

    def test_the_evidence_filter_separates_matched_reports_from_unmatched_ones(self):
        make_bounce(recipient="matched@example.org", match_method="message_id")
        make_bounce(recipient="unmatched@example.org")
        count_now()

        matched = self.client.get(reverse(LIST), {"evidence": "matched"})
        unmatched = self.client.get(reverse(LIST), {"evidence": "unmatched"})

        self.assertEqual([entry["row"].address for entry in matched.context["entries"]], ["matched@example.org"])
        self.assertEqual([entry["row"].address for entry in unmatched.context["entries"]], ["unmatched@example.org"])
        self.assertContains(unmatched, "unmatched reports only: check them first")

    def test_dates_far_out_of_range_are_ignored_instead_of_failing(self):
        make_row("a@example.org")

        for params in ({"end": "9999-12-31"}, {"start": "0001-01-01"}):
            with self.subTest(params=params):
                for name in (LIST, EXPORT):
                    self.assertEqual(self.client.get(reverse(name), params).status_code, 200)

    def test_invalid_filters_and_sorts_fall_back_quietly(self):
        make_row("a@example.org")

        response = self.client.get(
            reverse(LIST),
            {
                "role": "boss",
                "campaign": "nope",
                "start": "2026-02-30",
                "sort": "password",
                "page_size": "7",
                "status": "x",
            },
        )

        self.assertEqual(response.status_code, 200)
        listing = response.context["listing"]
        self.assertEqual((listing.sort, listing.page_size, listing.filters["status"]), ("last", 50, "open"))
        self.assertEqual(listing.filters["campaign"], "")

    def test_sorting_by_address_and_by_counts(self):
        make_row("b@example.org", hard_count=1)
        make_row("a@example.org", hard_count=5)

        by_address = self.client.get(reverse(LIST), {"sort": "address", "dir": "asc"})
        by_hard = self.client.get(reverse(LIST), {"sort": "hard", "dir": "desc"})

        self.assertEqual(
            [entry["row"].address for entry in by_address.context["entries"]], ["a@example.org", "b@example.org"]
        )
        self.assertEqual(
            [entry["row"].address for entry in by_hard.context["entries"]], ["a@example.org", "b@example.org"]
        )


class DetailTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_the_page_shows_reports_member_campaigns_actions_and_history(self):
        member = make_person("detail@example.org", first="Dina")
        add_email(member, "alt@example.org", verified=True)
        blast = make_campaign("Blast")
        email = make_email(recipient="detail@example.org", campaign_id=blast.pk)
        make_bounce(recipient="detail@example.org", email=email, campaign_id=blast.pk, remote_mta="mx.example.org")
        make_ses_log(blast, "detail@example.org", bounce_type="Transient")
        count_now()
        row = BouncedAddress.objects.get(address="detail@example.org")
        BouncedAddressAction.objects.create(bounced_address=row, address=row.address, action="dismiss", note="checked")

        response = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(response, "mx.example.org")
        self.assertContains(response, "Amazon SES events")
        self.assertContains(response, "Blast")
        self.assertContains(response, "Dina Doe")
        self.assertContains(response, "alt@example.org")
        self.assertContains(response, "checked")
        allowed = {item["action"]: item["allowed"] for item in response.context["actions"]}
        self.assertTrue(allowed["mark_undeliverable"])
        self.assertTrue(allowed["make_primary"])
        self.assertFalse(allowed["suppress"])

    def test_a_members_other_addresses_are_shown_only_with_the_members_app(self):
        member = make_person("card@example.org", first="Cara")
        add_email(member, "hidden-alt@example.org", verified=True)
        row = make_row("card@example.org")
        self.client.force_login(make_admin(apps=["mail"], email="mailstaff@example.org"))

        response = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(response, "Cara Doe")
        self.assertNotContains(response, "hidden-alt@example.org")
        self.assertContains(response, "shown to staff who also hold the Members app")
        self.client.force_login(make_admin(apps=["mail", "authn"], email="memberstaff@example.org"))
        self.assertContains(self.client.get(reverse(DETAIL, args=[row.pk])), "hidden-alt@example.org")

    def test_disabled_actions_say_why(self):
        make_person("why@example.org")
        row = make_row("why@example.org")
        self.client.force_login(make_admin(apps=["mail"], email="mailstaff@example.org"))

        response = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(response, "Needs the Members (authn) app as well as Mail.")
        self.assertContains(response, "disabled aria-disabled")

    def test_an_ambiguous_address_lists_every_contact_record(self):
        make_person("Dup@Example.org", first="Ann")
        make_person("dup@example.org", first="Bob")
        row = make_row("dup@example.org")

        response = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(response, "saved 2 times in different letter cases")
        for contact in ContactEmail.objects.filter(email_address__iexact="dup@example.org"):
            self.assertContains(response, reverse("admin:authn_contactemail_change", args=[contact.pk]))


class ExportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_the_filtered_list_is_exported_formula_safe(self):
        make_person("formula@example.org", first="=HYPERLINK(1)", last="X")
        make_row("formula@example.org")
        make_row("other@example.org", status=BouncedAddress.Status.DISMISSED)

        response = self.client.get(reverse(EXPORT), {"status": "open"})

        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn('attachment; filename="bounced_addresses_', response["Content-Disposition"])
        sheet = load_workbook(BytesIO(response.content)).active
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(rows[0][0], "Address")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "formula@example.org")
        self.assertEqual(rows[1][4], "'=HYPERLINK(1) X")
        self.assertEqual(rows[1][3], "Primary")

    def test_control_characters_in_a_name_never_break_the_export(self):
        make_person("ctrl@example.org", first="Pat\x0b", last="\x01Doe")
        make_row("ctrl@example.org")

        response = self.client.get(reverse(EXPORT))

        self.assertEqual(response.status_code, 200)
        rows = list(load_workbook(BytesIO(response.content)).active.iter_rows(values_only=True))
        self.assertEqual(rows[1][4], "Pat Doe")

    def test_the_export_is_capped(self):
        for index in range(3):
            make_row(f"cap{index}@example.org")

        with monitoring_settings(address_export_max_rows=2):
            response = self.client.get(reverse(EXPORT))

        self.assertEqual(len(list(load_workbook(BytesIO(response.content)).active.iter_rows())), 3)
