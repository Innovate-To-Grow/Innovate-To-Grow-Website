from datetime import timedelta
from io import BytesIO

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook

from apps.core.models import EmailBounce
from apps.mail.models import BounceAggregationState, BouncedAddress
from apps.mail.services.email_monitoring.addresses import aggregate, listing
from apps.mail.services.email_monitoring.addresses.listing.export import COLUMNS, export_rows
from apps.mail.tests.services.bounced_addresses.notices.test_left_org_notices import JORDAN, Suggestion, make_notice

from ..helpers import count_now, make_bounce, make_row


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
