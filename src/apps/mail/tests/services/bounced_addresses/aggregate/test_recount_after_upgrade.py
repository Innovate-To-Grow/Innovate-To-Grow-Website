from django.core.cache import cache
from django.test import TestCase

from apps.core.models import EmailBounce
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressAction, BouncedAddressCampaign
from apps.mail.services.email_monitoring.addresses import aggregate, listing
from apps.mail.services.email_monitoring.addresses.aggregate import sources
from apps.mail.tests.services.bounced_addresses.aggregate.test_categories import (
    TIMEOUT,
    Category,
    Suggestion,
    park_graph_cursor,
    row_for,
)

from ..helpers import count_now, make_bounce, make_campaign, make_row, make_ses_log


class RecountAfterUpgradeTests(TestCase):
    """``mail.0026`` parks the Graph cursor when Graph reports were counted before categories existed."""

    def setUp(self):
        cache.clear()

    def test_a_parked_cursor_counts_nothing_for_the_previous_release(self):
        make_bounce(recipient="p@example.org")
        count_now()
        park_graph_cursor()
        make_bounce(recipient="p@example.org", category="")
        state = BounceAggregationState.objects.get(source="graph")

        # The previous release reads the same cursor: no report is past it, and the page still loads.
        self.assertFalse(sources.after_cursor(EmailBounce.objects.all(), state, "created_at").exists())
        self.assertEqual(aggregate.pending(), 0)

    def test_the_first_count_starts_the_graph_counts_again_once_and_keeps_the_ses_counts(self):
        make_bounce(
            recipient="old@example.org",
            category="",
            classification="hard",
            status_code="5.4.316",
            match_method="message_id",
        )
        make_ses_log(make_campaign(), "old@example.org", bounce_type="Permanent")
        count_now()
        # As the release before categories left it: the report counted as hard, without category counts.
        BouncedAddress.objects.filter(address="old@example.org").update(
            hard_count=1, soft_count=0, category_counts={}, last_category="", suggestion=Suggestion.UNDELIVERABLE
        )
        EmailBounce.objects.update(category="", classification="hard")
        park_graph_cursor()

        count_now()

        row = row_for("old@example.org")
        self.assertEqual((row.hard_count, row.soft_count, row.matched_count), (0, 1, 1))
        self.assertEqual((row.category_counts, row.last_category), ({"transient": 1}, "transient"))
        self.assertEqual(row.ses_permanent_count, 1)
        self.assertEqual(row.suggestion, Suggestion.UNDELIVERABLE)  # the SES permanent bounce, not the timeout
        state = BounceAggregationState.objects.get(source="graph")
        self.assertLess(state.cursor_at, aggregate.PARKED)
        self.assertEqual(state.processed_total, 1)
        entry = BouncedAddressAction.objects.get(action=BouncedAddressAction.Action.REBUILD)
        self.assertEqual((entry.actor, entry.details), (None, {"source": "graph"}))
        self.assertTrue(entry.actor_label.startswith("Automatic"))
        self.assertEqual(BouncedAddressCampaign.objects.filter(source="ses").count(), 1)

        count_now()

        self.assertEqual(row_for("old@example.org").soft_count, 1)
        self.assertEqual(BouncedAddressAction.objects.filter(action="rebuild").count(), 1)

    def test_an_address_with_only_ses_events_is_left_as_it_is(self):
        make_ses_log(make_campaign(), "ses@example.org", bounce_type="Transient")
        count_now()
        before = row_for("ses@example.org")
        BounceAggregationState.objects.update_or_create(
            source="graph", defaults={"cursor_at": aggregate.PARKED, "processed_total": 1}
        )

        count_now()

        after = row_for("ses@example.org")
        self.assertEqual(
            (after.ses_transient_count, after.first_bounce_at, after.suggestion),
            (before.ses_transient_count, before.first_bounce_at, before.suggestion),
        )


class SelfHealTests(TestCase):
    """Every report this release counts adds one to a classification count and one to a category count."""

    def setUp(self):
        cache.clear()

    def test_a_row_whose_counts_do_not_add_up_has_the_graph_counts_started_again(self):
        make_bounce(recipient="h@example.org", category="transient", classification="soft", status_code="5.4.316")
        count_now()
        # As if the release before categories counted a report during the rollout: a classification count only.
        BouncedAddress.objects.filter(address="h@example.org").update(hard_count=1)
        self.assertFalse(aggregate.graph_counts_agree(row_for("h@example.org")))

        aggregate.refresh_all()
        self.assertEqual(BounceAggregationState.objects.get(source="graph").cursor_at, aggregate.PARKED)
        count_now()

        row = row_for("h@example.org")
        self.assertEqual((row.hard_count, row.soft_count, row.category_counts), (0, 1, {"transient": 1}))
        self.assertTrue(aggregate.graph_counts_agree(row))
        self.assertEqual(BouncedAddressAction.objects.filter(action="rebuild").count(), 1)

    def test_rows_that_add_up_leave_the_cursor_alone(self):
        make_bounce(recipient="ok@example.org")
        make_ses_log(make_campaign(), "ses-only@example.org", bounce_type="Transient")
        count_now()
        cursor = BounceAggregationState.objects.get(source="graph").cursor_at

        aggregate.refresh_all()

        self.assertEqual(BounceAggregationState.objects.get(source="graph").cursor_at, cursor)

    def test_parking_creates_the_counting_state_when_there_is_none(self):
        aggregate.park_graph()

        self.assertEqual(BounceAggregationState.objects.get(source="graph").cursor_at, aggregate.PARKED)


class RebuildTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_rebuild_classifies_the_stored_reports_again_then_counts_them(self):
        bounce = make_bounce(recipient="r@example.org", status_code="5.0.0", diagnostic_code=TIMEOUT)
        count_now()
        self.assertEqual(row_for("r@example.org").category_counts, {"hard": 1})
        park_graph_cursor()

        reclassified = aggregate.rebuild()
        self.assertIsNone(BounceAggregationState.objects.get(source="graph").cursor_at)
        count_now()

        bounce.refresh_from_db()
        row = row_for("r@example.org")
        self.assertEqual(reclassified, 1)
        self.assertEqual(bounce.category, Category.TRANSIENT)
        self.assertEqual((row.category_counts, row.hard_count, row.soft_count), ({"transient": 1}, 0, 1))
        self.assertFalse(BouncedAddressAction.objects.filter(action="rebuild").exists())  # the view records it


class ListingTests(TestCase):
    def setUp(self):
        cache.clear()
        make_row("hard@example.org")
        make_row("timeout@example.org", hard_count=0, soft_count=2, last_category="transient")
        make_row(
            "relay@example.org",
            hard_count=0,
            rejected_count=1,
            category_counts={"relay_denied": 1},
            last_category="relay_denied",
        )
        make_row("ses@example.org", hard_count=0, ses_transient_count=1, last_category="")

    def addresses(self, **params):
        current = listing.parse_listing({"status": "all", **params})
        return [row.address for row in listing.rows_for(current)]

    def test_the_category_filter_reads_graph_categories_and_the_ses_type_that_means_the_same(self):
        self.assertEqual(self.addresses(category="relay_denied"), ["relay@example.org"])
        self.assertEqual(sorted(self.addresses(category="transient")), ["ses@example.org", "timeout@example.org"])
        self.assertEqual(self.addresses(category="hard"), ["hard@example.org"])
        self.assertEqual(self.addresses(category="mailbox_disabled"), [])
        self.assertEqual(len(self.addresses(category="bogus")), 4)
        labels = {key: label for key, (label, _q) in listing.CATEGORIES.items()}
        self.assertEqual(labels["transient"], "Temporary failure (or SES transient)")
        self.assertEqual(labels["relay_denied"], "Relay denied")

    def test_rows_sort_by_their_last_category(self):
        self.assertEqual(
            self.addresses(sort="category", dir="asc"),
            ["ses@example.org", "hard@example.org", "relay@example.org", "timeout@example.org"],
        )
