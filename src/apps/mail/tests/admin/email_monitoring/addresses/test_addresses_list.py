from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.services.email_monitoring.helpers import monitoring_settings
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BouncedAddress
from apps.mail.tests.admin.email_monitoring.addresses.test_addresses_admin import EXPORT, LIST
from apps.mail.tests.services.bounced_addresses.helpers import (
    count_now,
    make_bounce,
    make_campaign,
    make_person,
    make_row,
    make_ses_log,
    settled,
)


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
