"""Left-the-organisation notices in Bounced addresses (the ``inbound`` counting source): a notice the helpdesk matched
to an email the site sent counts against the address that email went to, once; out-of-office replies, unmatched
notices and second copies never count; a notice is evidence with a suggestion, never an action: it changes no member,
contact, subscription, suppression or review state; a rebuild and a restarted Graph count keep it. Every address is
synthetic."""

import itertools
from datetime import timedelta
from io import BytesIO

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook

from apps.authn.models import ContactEmail
from apps.core.models import EmailBounce, InboundMessage
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressAction
from apps.mail.services.email_monitoring.addresses import aggregate, audit, listing
from apps.mail.services.email_monitoring.addresses.export import COLUMNS, export_rows
from apps.mail.services.email_monitoring.addresses.suggestions import suggest

from .helpers import count_now, make_bounce, make_person, make_row

Suggestion = BouncedAddress.Suggestion
SITE = "i2g@ucmerced.edu"
JORDAN = "jordan.park@contoso.example"
_ids = itertools.count(1)


def make_notice(recipient=JORDAN, *, classification="left_org", status="done", received=None, processed=None, **result):
    """An inbound queue row as the helpdesk leaves a notice (``recipient``: the address the site mailed; "" for a
    notice that answers nothing the site sent)."""
    now = timezone.now()
    data = {"ticket": 1000 + next(_ids), "created": True, "rule": "new", "site_mail": "a1b2c3d4", **result}
    if recipient:
        data["site_recipient"] = recipient
    return InboundMessage.objects.create(
        mailbox=SITE,
        graph_id=f"AAMk-notice-{next(_ids)}",
        received_at=received or now - timedelta(hours=1),
        from_address=JORDAN,
        classification=classification,
        subtype=classification,
        status=status,
        result=data,
        processed_at=(processed or now - timedelta(minutes=5)) if status == "done" else None,
    )


class CountingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_matched_notice_counts_against_the_address_the_site_mailed(self):
        member = make_person(JORDAN)
        notice = make_notice(named_contact="Riley.Chen@contoso.example", named_contact_kind="contact")
        before = ContactEmail.objects.get(email_address=JORDAN)

        result = count_now()

        self.assertEqual((result["inbound"], result["graph"], result["ses"]), (1, 0, 0))
        row = BouncedAddress.objects.get(address=JORDAN)
        self.assertEqual(
            (row.left_org_count, row.left_org_first_at, row.left_org_last_at),
            (1, notice.received_at, notice.received_at),
        )
        self.assertEqual((row.left_org_contact, row.left_org_contact_kind), ("riley.chen@contoso.example", "contact"))
        self.assertEqual(row.left_org_ticket, notice.result["ticket"])
        self.assertEqual((row.first_bounce_at, row.last_bounce_at), (notice.received_at, notice.received_at))
        self.assertEqual((row.suggestion, row.status, row.suppressed_at), (Suggestion.LEFT_ORG, "open", None))
        self.assertEqual((row.member, row.role), (member, "primary"))
        self.assertTrue(row.has_matched_evidence and row.suggests_address_action)
        self.assertEqual((row.report_total, row.left_org_contact_label), (0, "who to contact instead, the notice says"))
        after = ContactEmail.objects.get(email_address=JORDAN)
        self.assertEqual((after.subscribe, after.verified, after.email_type), (before.subscribe, True, "primary"))
        self.assertFalse(BouncedAddressAction.objects.exists())

    def test_each_notice_counts_once_and_the_latest_names_the_contact(self):
        now = timezone.now()
        make_notice(received=now - timedelta(days=3), named_contact="old@contoso.example", named_contact_kind="contact")
        count_now()
        count_now()
        make_notice(
            received=now - timedelta(days=1), named_contact="new@newco.example", named_contact_kind="new_address"
        )
        make_notice(
            received=now - timedelta(days=5), named_contact="older@contoso.example", named_contact_kind="contact"
        )

        count_now()

        row = BouncedAddress.objects.get(address=JORDAN)
        self.assertEqual(row.left_org_count, 3)
        self.assertEqual((row.left_org_contact, row.left_org_contact_kind), ("new@newco.example", "new_address"))
        self.assertEqual(row.left_org_first_at, now - timedelta(days=5))
        self.assertEqual(row.left_org_last_at, now - timedelta(days=1))
        self.assertEqual(BounceAggregationState.objects.get(source="inbound").processed_total, 3)
        self.assertEqual(aggregate.pending(), 0)

    def test_out_of_office_replies_unmatched_notices_and_copies_never_count(self):
        make_notice(classification="auto_reply")
        make_notice(recipient="")
        make_notice(status="pending")
        make_notice(duplicate=True)
        make_notice(recipient="not an address")

        self.assertEqual(count_now()["inbound"], 2)  # the copy and the bad address are read, and counted for nobody

        self.assertFalse(BouncedAddress.objects.exists())

    def test_a_notice_still_settling_waits_for_the_next_run(self):
        make_notice(processed=timezone.now())

        self.assertEqual(aggregate.run()["inbound"], 0)  # the default settle delay
        self.assertEqual(aggregate.pending(), 1)

    def test_the_named_contact_is_a_bounded_hint(self):
        make_notice("a@contoso.example", named_contact="a@contoso.example", named_contact_kind="contact")
        make_notice("b@contoso.example", named_contact="b2@contoso.example", named_contact_kind="bogus")
        make_notice("c@contoso.example", named_contact=f"{'x' * 250}@contoso.example", named_contact_kind="contact")
        make_notice("d@contoso.example", ticket="1234")

        count_now()

        rows = {row.address: row for row in BouncedAddress.objects.all()}
        self.assertEqual(
            (rows["a@contoso.example"].left_org_contact, rows["a@contoso.example"].left_org_contact_kind), ("", "")
        )
        self.assertEqual(
            (rows["b@contoso.example"].left_org_contact, rows["b@contoso.example"].left_org_contact_kind),
            ("b2@contoso.example", ""),
        )
        self.assertEqual(rows["b@contoso.example"].left_org_contact_label, "an address the notice names")
        self.assertEqual(rows["c@contoso.example"].left_org_contact, "")
        self.assertIsNone(rows["d@contoso.example"].left_org_ticket)

    def test_a_malformed_result_is_skipped(self):
        notice = make_notice()
        InboundMessage.objects.filter(pk=notice.pk).update(result=["site_recipient"])

        count_now()

        self.assertFalse(BouncedAddress.objects.exists())


class EvidenceOnlyTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_notice_never_reopens_a_dismissed_address(self):
        row = make_row(JORDAN, status="dismissed", reviewed_at=timezone.now() - timedelta(days=2))
        make_notice(received=timezone.now() - timedelta(hours=1))

        count_now()

        row.refresh_from_db()
        self.assertEqual((row.status, row.left_org_count), ("dismissed", 1))
        self.assertFalse(BouncedAddressAction.objects.filter(action="reopen").exists())

    def test_the_suggestion_order(self):
        cases = (
            ({"complaint_count": 1}, Suggestion.UNSUBSCRIBE),
            ({}, Suggestion.UNDELIVERABLE),
            ({"hard_count": 0, "category_counts": {"mailbox_disabled": 1}}, Suggestion.REPLACE),
            ({"hard_count": 0, "soft_count": 5}, Suggestion.LEFT_ORG),
            ({"hard_count": 0, "rejected_count": 1, "category_counts": {"relay_denied": 1}}, Suggestion.LEFT_ORG),
        )
        for index, (values, expected) in enumerate(cases):
            with self.subTest(expected=expected, values=values):
                row = make_row(f"case{index}@contoso.example", left_org_count=1, **values)
                self.assertEqual(suggest(row), expected)
        suppressed = make_row("gone@contoso.example", left_org_count=1, suppressed_at=timezone.now())
        self.assertEqual(suggest(suppressed), "")

    def test_the_audit_summary_names_the_notices(self):
        notices_only = make_row(
            "n@contoso.example", hard_count=0, left_org_count=2, graph_last_at=None, last_classification=""
        )
        both = make_row("b@contoso.example", left_org_count=1)

        self.assertEqual(audit.evidence(notices_only), "2 left-the-organisation notices")
        self.assertEqual(audit.evidence(both), "address does not exist 5.1.1, 1 report, 1 left-the-organisation notice")


class KeptCountsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_rebuild_keeps_the_notices_and_their_dates(self):
        notice = make_notice()
        make_bounce(recipient=JORDAN, received_at=timezone.now() - timedelta(days=10))
        count_now()

        aggregate.rebuild()

        row = BouncedAddress.objects.get(address=JORDAN)
        self.assertEqual((row.left_org_count, row.hard_count), (1, 0))
        self.assertEqual((row.first_bounce_at, row.last_bounce_at), (notice.received_at, notice.received_at))
        self.assertEqual(row.suggestion, Suggestion.LEFT_ORG)
        self.assertEqual(BounceAggregationState.objects.get(source="inbound").processed_total, 1)
        count_now()
        row.refresh_from_db()
        self.assertEqual((row.left_org_count, row.hard_count, row.suggestion), (1, 1, Suggestion.UNDELIVERABLE))
        self.assertEqual((row.first_bounce_at, row.last_bounce_at), (row.graph_first_at, notice.received_at))

    def test_a_restarted_graph_count_keeps_the_notice_and_ses_dates(self):
        now = timezone.now()
        make_notice("notice@contoso.example", received=now - timedelta(days=9))
        make_notice("both@contoso.example", received=now - timedelta(days=9))
        for address in ("notice@contoso.example", "both@contoso.example", "graph@contoso.example"):
            make_bounce(recipient=address, received_at=now - timedelta(days=2))
        count_now()
        BouncedAddress.objects.filter(address="both@contoso.example").update(
            ses_first_at=now - timedelta(days=30), ses_last_at=now - timedelta(days=20)
        )
        EmailBounce.objects.all().delete()  # purged: the restarted Graph count cannot recount them
        aggregate.park_graph()

        count_now()

        rows = {row.address: row for row in BouncedAddress.objects.all()}
        notice, both, graph = (
            rows["notice@contoso.example"],
            rows["both@contoso.example"],
            rows["graph@contoso.example"],
        )
        self.assertEqual((notice.first_bounce_at, notice.last_bounce_at), (now - timedelta(days=9),) * 2)
        self.assertEqual(
            (both.first_bounce_at, both.last_bounce_at), (now - timedelta(days=30), now - timedelta(days=9))
        )
        self.assertEqual((graph.first_bounce_at, graph.last_bounce_at, graph.hard_count), (None, None, 0))
        self.assertEqual((notice.left_org_count, notice.hard_count, notice.suggestion), (1, 0, ""))
        aggregate.refresh_all()  # the hourly refresh suggests again
        notice.refresh_from_db()
        self.assertEqual(notice.suggestion, Suggestion.LEFT_ORG)


class ListingAndExportTests(TestCase):
    def setUp(self):
        cache.clear()
        make_notice("left@contoso.example", named_contact="riley@contoso.example", named_contact_kind="contact")
        count_now()
        make_row("hard@contoso.example", matched_count=0)

    def addresses(self, **params):
        current = listing.parse_listing({"status": "all", **params})
        return sorted(row.address for row in listing.rows_for(current))

    def test_the_type_and_evidence_filters(self):
        self.assertEqual(self.addresses(type="left_org"), ["left@contoso.example"])
        self.assertEqual(self.addresses(evidence="matched"), ["left@contoso.example"])
        self.assertEqual(self.addresses(evidence="unmatched"), ["hard@contoso.example"])
        self.assertEqual(self.addresses(suggestion="left_org"), ["left@contoso.example"])

    def test_the_counts_sort_includes_the_notices(self):
        current = listing.parse_listing({"status": "all", "sort": "reports", "dir": "desc"})
        rows = list(listing.rows_for(current))

        self.assertEqual([row.report_sort for row in rows], [1, 1])

    def test_the_export_has_the_notice_columns(self):
        current = listing.parse_listing({"status": "all", "type": "left_org"})
        sheet = load_workbook(BytesIO(export_rows(listing.rows_for(current)))).active
        header = [cell.value for cell in sheet[1]]
        values = dict(zip(header, [cell.value for cell in sheet[2]], strict=True))

        self.assertEqual(len(header), len(COLUMNS))
        self.assertEqual(values["Left-org notices"], 1)
        self.assertEqual(values["Address the notice names"], "riley@contoso.example")
        self.assertTrue(values["Last notice"])
        self.assertEqual(values["Suggestion"], Suggestion.LEFT_ORG.label)
